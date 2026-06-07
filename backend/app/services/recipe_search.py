"""Recipe detail facade — Grok recipe store + AllRecipes (no Spoonacular)."""

from __future__ import annotations

from app.config import settings
from app.services import mock_data
from app.services.allrecipes_scraper import fetch_recipe_page
from app.services.grok_recipe_store import get_detail, put


async def search_recipes(
    ingredients: list[str],
    *,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
    include_pantry_staples: bool = True,
    pantry_staples: list[str] | None = None,
) -> tuple[dict, bool]:
    payload = mock_data.mock_search_recipes(
        ingredients,
        diets=diets,
        intolerances=intolerances,
        health_conditions=health_conditions,
        include_pantry_staples=include_pantry_staples,
        pantry_staples=pantry_staples or settings.pantry_staple_list(),
    )
    return payload, True


async def get_recipe_detail(recipe_id: int) -> tuple[dict | None, bool]:
    cached = get_detail(recipe_id)
    if cached:
        return cached, False

    # Legacy mock ids
    mock = mock_data.mock_recipe_detail(recipe_id)
    if mock:
        return mock, True

    return None, True