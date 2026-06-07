from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models import User
from app.schemas import (
    AccentSide,
    CompanionRecipe,
    CookKitRequest,
    CookKitResponse,
    ElevationInsight,
    IngredientMatch,
    RecipeDetailResponse,
    SimplifyRecipeRequest,
    SimplifyRecipeResponse,
    SimplifiedStep,
)
from app.services.cooking_ai import simplify_recipe
from app.services.recipe_elevation import build_cook_kit
from app.services.recipe_search import get_recipe_detail

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("/{recipe_id}", response_model=RecipeDetailResponse)
async def recipe_detail(recipe_id: int):
    detail, is_mock = await get_recipe_detail(recipe_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return RecipeDetailResponse(
        id=detail["id"],
        title=detail["title"],
        image=detail.get("image"),
        summary=detail.get("summary"),
        ready_in_minutes=detail.get("ready_in_minutes"),
        servings=detail.get("servings"),
        source_url=detail.get("source_url"),
        video_url=detail.get("video_url"),
        ingredients=[IngredientMatch(**i) for i in detail["ingredients"]],
        instructions=detail["instructions"],
        diets=detail.get("diets", []),
        mock=is_mock,
    )


@router.post("/{recipe_id}/simplify", response_model=SimplifyRecipeResponse)
async def simplify_recipe_endpoint(
    recipe_id: int,
    body: SimplifyRecipeRequest,
    current_user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    explain = body.explain_techniques if body.explain_techniques is not None else True
    skill = body.skill_level or "beginner"

    if current_user:
        from app.api.preferences import _get_or_create_prefs

        prefs = await _get_or_create_prefs(current_user.id, db)
        if body.explain_techniques is None:
            explain = prefs.explain_techniques
        if body.skill_level is None:
            skill = prefs.skill_level

    result, is_mock = await simplify_recipe(
        recipe_id,
        explain_techniques=explain,
        skill_level=skill,
        what_sounds_good=body.what_sounds_good,
        protein_filters=body.protein_filters,
        side_filters=body.side_filters,
        diets=body.diets,
        intolerances=body.intolerances,
        health_conditions=body.health_conditions,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return SimplifyRecipeResponse(
        recipe_id=result["recipe_id"],
        title=result["title"],
        mode=result["mode"],
        steps=[SimplifiedStep(**s) for s in result["steps"]],
        mock=is_mock,
    )


@router.post("/{recipe_id}/cook-kit", response_model=CookKitResponse)
async def cook_kit_endpoint(
    recipe_id: int,
    body: CookKitRequest,
    current_user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    explain = body.explain_techniques if body.explain_techniques is not None else True
    skill = body.skill_level or "beginner"

    if current_user:
        from app.api.preferences import _get_or_create_prefs

        prefs = await _get_or_create_prefs(current_user.id, db)
        if body.explain_techniques is None:
            explain = prefs.explain_techniques
        if body.skill_level is None:
            skill = prefs.skill_level

    result, is_mock = await build_cook_kit(
        recipe_id,
        explain_techniques=explain,
        skill_level=skill,
        what_sounds_good=body.what_sounds_good,
        dish_anchor=body.dish_anchor,
        protein_filters=body.protein_filters,
        side_filters=body.side_filters,
        diets=body.diets,
        intolerances=body.intolerances,
        health_conditions=body.health_conditions,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return CookKitResponse(
        recipe_id=result["recipe_id"],
        title=result["title"],
        mode=result["mode"],
        steps=[SimplifiedStep(**s) for s in result["steps"]],
        elevation_insights=[ElevationInsight(**i) for i in result.get("elevation_insights") or []],
        accent_side=AccentSide(**result["accent_side"]) if result.get("accent_side") else None,
        companions=[CompanionRecipe(**c) for c in result.get("companions") or []],
        dish_anchor=result.get("dish_anchor"),
        mock=is_mock,
    )