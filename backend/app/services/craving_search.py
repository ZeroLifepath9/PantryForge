"""What sounds good — Grok chef agent drives search and lineup."""

from __future__ import annotations

from typing import Any

from app.services.chef_search import chef_search as run_chef_search


async def search_by_craving(
    what_sounds_good: str,
    *,
    protein_filter: str | None = None,
    protein_filters: list[str] | None = None,
    side_filters: list[str] | None = None,
    cuisine_filters: list[str] | None = None,
    selected_recipe_ids: list[int] | None = None,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    return await run_chef_search(
        what_sounds_good,
        protein_filter=protein_filter,
        protein_filters=protein_filters,
        side_filters=side_filters,
        cuisine_filters=cuisine_filters,
        selected_recipe_ids=selected_recipe_ids,
        diets=diets,
        intolerances=intolerances,
        health_conditions=health_conditions,
    )