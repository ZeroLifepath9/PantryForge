"""Recipe search facade — Spoonacular when API key is set, mock otherwise."""

from __future__ import annotations

from app.config import settings
from app.services import mock_data


async def search_recipes(
    ingredients: list[str],
    *,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
    include_pantry_staples: bool = True,
    pantry_staples: list[str] | None = None,
) -> tuple[dict, bool]:
    if settings.mock_mode or not settings.spoonacular_api_key:
        payload = mock_data.mock_search_recipes(
            ingredients,
            diets=diets,
            intolerances=intolerances,
            health_conditions=health_conditions,
            include_pantry_staples=include_pantry_staples,
            pantry_staples=pantry_staples or settings.pantry_staple_list(),
        )
        return payload, True

    from app.services import spoonacular

    payload = await spoonacular.search_recipes(
        ingredients,
        diets=diets,
        intolerances=intolerances,
        health_conditions=health_conditions,
        include_pantry_staples=include_pantry_staples,
        pantry_staples=pantry_staples or settings.pantry_staple_list(),
    )
    return payload, False


async def get_recipe_detail(recipe_id: int) -> tuple[dict | None, bool]:
    if settings.mock_mode or not settings.spoonacular_api_key:
        return mock_data.mock_recipe_detail(recipe_id), True

    from app.services import spoonacular

    detail = await spoonacular.get_recipe_detail(recipe_id)
    if detail:
        return detail, False
    # Spoonacular miss — fall back to mock ids for dev continuity
    mock = mock_data.mock_recipe_detail(recipe_id)
    return mock, mock is not None