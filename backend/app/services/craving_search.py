"""Search recipes from 'what sounds good' — dish match OR protein+ingredients, 25 per page."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services import mock_data
from app.services.craving_parser import apply_protein_filter, parse_craving
from app.services.craving_ranker import PAGE_SIZE, POPULAR_TOP, rank_craving_results


def _build_message(parsed: dict[str, Any], count: int, *, live: bool) -> str:
    dish_anchor = parsed.get("dish_anchor")
    protein = parsed.get("protein")
    ingredients = parsed.get("ingredients") or []

    if count == 0:
        if live:
            return "No matches — try tacos, chicken with garlic, or loosen diet filters."
        return "No demo matches — add API keys on Render for live recipe search."

    if dish_anchor:
        family = dish_anchor.replace("_", " ")
        if protein:
            return (
                f"{count} {family} recipes with {protein} — top {POPULAR_TOP} are the most popular. "
                "Change protein below to refresh."
            )
        return (
            f"{count} {family} recipes (tacos, burritos, fajitas & more). "
            f"Top {POPULAR_TOP} are the most popular — filter by protein to narrow."
        )

    if protein and ingredients:
        return (
            f"{count} recipes with {protein} and your ingredients. "
            f"Top {POPULAR_TOP} are the most popular."
        )
    if protein:
        return f"{count} recipes featuring {protein}. Top {POPULAR_TOP} are the most popular."

    return (
        f"{count} recipes matching your craving. "
        f"Top {POPULAR_TOP} are the most popular — filter by protein to refresh."
    )


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
    elif parsed.get("protein"):
        parsed["needs_protein_prompt"] = False

    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []

    use_live = bool(settings.spoonacular_key) and not settings.mock_mode
    candidates: list[dict[str, Any]] = []
    search_mock = True

    if use_live:
        from app.services import spoonacular

        try:
            result = await spoonacular.search_by_craving(
                parsed, diets=diets, intolerances=intolerances
            )
            candidates = result.get("candidates") or []
            search_mock = False
        except Exception:
            pass

    if search_mock:
        candidates = mock_data.mock_craving_candidates(
            parsed,
            what_sounds_good=what_sounds_good,
            diets=diets,
            intolerances=intolerances,
            health_conditions=health_conditions,
        )

    recipes = rank_craving_results(parsed, candidates)
    live = use_live and not search_mock
    message = _build_message(parsed, len(recipes), live=live)

    if not live and recipes:
        message = f"Demo: {message} Set API keys on Render for live Spoonacular results."

    return {
        "what_sounds_good": what_sounds_good,
        "parsed": parsed,
        "recipes": recipes,
        "page_size": PAGE_SIZE,
        "popular_top": POPULAR_TOP,
        "message": message,
        "live": live,
    }, search_mock and parse_mock