"""Search mains + pairings from a parsed craving."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services import mock_data
from app.services.craving_parser import parse_craving
from app.services.recipe_curator import curate_recipes


def _merge_candidates(mains: list, pairings: list) -> list:
    seen: set[int] = set()
    merged: list = []
    for card in mains + pairings:
        if card["id"] in seen:
            continue
        merged.append(card)
        seen.add(card["id"])
    return merged


async def search_by_craving(
    what_sounds_good: str,
    *,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    parsed, parse_mock = await parse_craving(what_sounds_good)
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []

    use_live = bool(settings.spoonacular_api_key) and not settings.mock_mode

    raw_mains: list = []
    raw_pairings: list = []
    message: str | None = None
    search_mock = True

    if use_live:
        from app.services import spoonacular

        try:
            result = await spoonacular.search_by_craving(
                parsed, diets=diets, intolerances=intolerances
            )
            raw_mains = result["mains"]
            raw_pairings = result["pairings"]
            message = result.get("message")
            search_mock = False
        except Exception:
            pass

    if search_mock:
        result = mock_data.mock_craving_search(
            parsed,
            diets=diets,
            intolerances=intolerances,
            health_conditions=health_conditions,
        )
        raw_mains = result["mains"]
        raw_pairings = result["pairings"]
        message = result.get("message")

    candidates = _merge_candidates(raw_mains, raw_pairings)
    recipes, curator_mock = await curate_recipes(what_sounds_good, parsed, candidates)

    if recipes:
        message = f"Grok picked {len(recipes)} recipes that fit what sounds good."

    return {
        "what_sounds_good": what_sounds_good,
        "parsed": parsed,
        "recipes": recipes,
        "message": message,
    }, search_mock and parse_mock and curator_mock