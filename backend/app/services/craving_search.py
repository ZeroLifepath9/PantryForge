"""Search mains + pairings from a parsed craving."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services import mock_data
from app.services.craving_parser import apply_protein_filter, parse_craving
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
    protein_filter: str | None = None,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    parsed, parse_mock = await parse_craving(what_sounds_good)
    if protein_filter is not None:
        parsed = apply_protein_filter(parsed, protein_filter or None)
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []

    use_live = bool(settings.spoonacular_key) and not settings.mock_mode

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
            what_sounds_good=what_sounds_good,
            diets=diets,
            intolerances=intolerances,
            health_conditions=health_conditions,
        )
        raw_mains = result["mains"]
        raw_pairings = result["pairings"]
        message = result.get("message")

    candidates = _merge_candidates(raw_mains, raw_pairings)
    recipes, curator_mock = await curate_recipes(what_sounds_good, parsed, candidates)

    live = use_live and not search_mock
    protein = parsed.get("protein")
    search_mode = parsed.get("search_mode")
    dish_anchor = parsed.get("dish_anchor")
    if recipes:
        if search_mode == "dish" and dish_anchor:
            family = dish_anchor.replace("_", " ")
            if protein:
                message = (
                    f"{len(recipes)} {family} dishes with {protein} — "
                    "tacos, burritos, fajitas & more."
                    if dish_anchor == "taco"
                    else f"{len(recipes)} {family} dishes with {protein}."
                )
            elif parsed.get("needs_protein_prompt"):
                message = message or (
                    f"{len(recipes)} {family} recipes — pick a protein to narrow down."
                )
        elif protein:
            message = (
                f"{len(recipes)} dishes featuring {protein} — mains, sides, and more "
                "to scratch that craving."
            )
        elif live:
            message = f"Found {len(recipes)} recipes matching your craving."
        else:
            message = (
                f"Demo: {len(recipes)} recipes matched your craving. "
                "Set SPOONACULAR_API_KEY and XAI_API_KEY on Render for live results."
            )
    elif not live:
        message = (
            "No demo recipes matched — try chicken, salmon, pasta, or eggs. "
            "Add API keys on Render for real recipe search."
        )

    return {
        "what_sounds_good": what_sounds_good,
        "parsed": parsed,
        "recipes": recipes,
        "message": message,
        "live": live,
    }, search_mock and parse_mock and curator_mock