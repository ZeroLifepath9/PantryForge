from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_optional_user
from app.models import User
from app.schemas import (
    DietOption,
    MetaResponse,
    ParseIngredientsRequest,
    ParseIngredientsResponse,
    RecipeSearchResult,
    SearchRecipesRequest,
    SearchRecipesResponse,
)
from app.services import mock_data
from app.services.cooking_ai import parse_ingredients
from app.services.recipe_search import search_recipes

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/meta", response_model=MetaResponse)
async def search_meta():
    return MetaResponse(
        mock_mode=settings.mock_mode,
        diets=[DietOption(**d) for d in mock_data.DIET_OPTIONS],
        intolerances=[DietOption(**d) for d in mock_data.INTOLERANCE_OPTIONS],
        health_conditions=[DietOption(**d) for d in mock_data.HEALTH_CONDITION_OPTIONS],
    )


@router.post("/parse-ingredients", response_model=ParseIngredientsResponse)
async def parse_ingredients_endpoint(body: ParseIngredientsRequest):
    ingredients, is_mock = await parse_ingredients(body.text)
    return ParseIngredientsResponse(ingredients=ingredients, mock=is_mock)


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