from datetime import datetime
import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_optional_user
from app.models import User, UserPreferences
from app.schemas import (
    CravingParsed,
    CravingSearchRequest,
    CravingSearchResponse,
    CravingThread,
    DietOption,
    MealRecipeCard,
    MetaResponse,
    ParseIngredientsRequest,
    ParseIngredientsResponse,
    RecipeSearchResult,
    SearchRecipesRequest,
    SearchRecipesResponse,
    SharedBridge,
)
from app.services import mock_data
from app.services.cooking_ai import parse_ingredients
from app.services.craving_search import search_by_craving
from app.services.recipe_search import search_recipes

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/meta", response_model=MetaResponse)
async def search_meta():
    from app.services.filter_options import CUISINE_OPTIONS, PROTEIN_OPTIONS, SIDE_OPTIONS

    return MetaResponse(
        mock_mode=settings.mock_mode,
        xai_configured=bool(settings.xai_key),
        spoonacular_configured=False,
        diets=[DietOption(**d) for d in mock_data.DIET_OPTIONS],
        intolerances=[DietOption(**d) for d in mock_data.INTOLERANCE_OPTIONS],
        health_conditions=[DietOption(**d) for d in mock_data.HEALTH_CONDITION_OPTIONS],
        protein_options=[DietOption(**d) for d in PROTEIN_OPTIONS],
        side_options=[DietOption(**d) for d in SIDE_OPTIONS],
        cuisine_options=[DietOption(**d) for d in CUISINE_OPTIONS],
    )


@router.post("/parse-ingredients", response_model=ParseIngredientsResponse)
async def parse_ingredients_endpoint(body: ParseIngredientsRequest):
    ingredients, is_mock = await parse_ingredients(body.text)
    return ParseIngredientsResponse(ingredients=ingredients, mock=is_mock)


@router.post("/craving", response_model=CravingSearchResponse)
async def search_craving_endpoint(
    body: CravingSearchRequest,
    current_user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    protein_filter = body.protein_filter
    protein_filters = body.protein_filters or []
    if protein_filter and protein_filter not in protein_filters:
        protein_filters = [protein_filter, *protein_filters]
    elif not protein_filter and protein_filters:
        protein_filter = protein_filters[0]

    # Load user's background flavor profile + history for blending with current input
    user_flavor_profile = {}
    craving_history = []
    if current_user:
        from app.api.preferences import _get_or_create_prefs
        prefs = await _get_or_create_prefs(current_user.id, db)
        user_flavor_profile = prefs.flavor_profile()
        craving_history = prefs.craving_history()[-5:]  # recent past inputs

    payload, is_mock = await search_by_craving(
        body.what_sounds_good,
        protein_filter=protein_filter,
        protein_filters=protein_filters,
        side_filters=body.side_filters,
        cuisine_filters=body.cuisine_filters,
        selected_recipe_ids=body.selected_recipe_ids,
        diets=body.diets,
        intolerances=body.intolerances,
        health_conditions=body.health_conditions,
        user_flavor_profile=user_flavor_profile,
        craving_history=craving_history,
    )
    parsed_raw = payload["parsed"]
    bridge = parsed_raw.get("shared_bridge") or payload.get("shared_bridge")
    threads = payload.get("craving_threads") or parsed_raw.get("craving_threads") or []

    # Background: start/update user flavor profile with current input + derived (if user exists)
    if current_user:
        from app.api.preferences import _get_or_create_prefs
        prefs = await _get_or_create_prefs(current_user.id, db)
        current_fp = parsed_raw.get("flavor_profile") or {}
        if isinstance(current_fp, str):
            current_fp = {"description": current_fp}
        derived = parsed_raw.get("derived_flavor_profile") or current_fp
        if isinstance(derived, str):
            derived = {"description": derived}

        new_history = (craving_history or []) + [{
            "what_sounds_good": body.what_sounds_good,
            "flavor_profile": current_fp,
            "derived_flavor_profile": derived,
            "timestamp": datetime.utcnow().isoformat(),
        }]
        new_history = new_history[-5:]

        prefs.flavor_profile_json = json.dumps(derived)
        prefs.craving_history_json = json.dumps(new_history)
        await db.commit()

    return CravingSearchResponse(
        what_sounds_good=payload["what_sounds_good"],
        parsed=CravingParsed(**parsed_raw),
        recipes=[MealRecipeCard(**m) for m in payload["recipes"]],
        chef_headline=payload.get("chef_headline"),
        chef_intro=payload.get("chef_intro"),
        craving_threads=[CravingThread(**t) for t in threads],
        shared_bridge=SharedBridge(**bridge) if bridge else None,
        page_size=payload.get("page_size", 12),
        popular_top=payload.get("popular_top", 3),
        candidate_count=payload.get("candidate_count", 0),
        refined=bool(payload.get("refined")),
        mock=is_mock,
        live=bool(payload.get("live")),
        message=payload.get("message"),
    )


@router.post("/recipes", response_model=SearchRecipesResponse)
async def search_recipes_endpoint(
    body: SearchRecipesRequest,
    current_user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    diets = body.diets
    intolerances = body.intolerances
    include_pantry = body.include_pantry_staples
    pantry_staples = body.pantry_staples

    if current_user and not body.pantry_staples:
        from app.api.preferences import _get_or_create_prefs

        prefs = await _get_or_create_prefs(current_user.id, db)
        pantry_staples = prefs.pantry_staples() or settings.pantry_staple_list()

    payload, is_mock = await search_recipes(
        body.ingredients,
        diets=diets,
        intolerances=intolerances,
        health_conditions=body.health_conditions,
        include_pantry_staples=include_pantry,
        pantry_staples=pantry_staples,
    )
    return SearchRecipesResponse(
        query_ingredients=payload["query_ingredients"],
        effective_ingredients=payload["effective_ingredients"],
        results=[RecipeSearchResult(**r) for r in payload["results"]],
        mock=is_mock,
        message=payload.get("message"),
    )