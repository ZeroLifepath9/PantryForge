"""Search recipes from 'what sounds good' — broad Spoonacular fetch + chef insight."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.services import mock_data
from app.services.chef_insight import enrich_with_chef_insight
from app.services.craving_parser import apply_protein_filter, parse_craving
from app.services.craving_ranker import PAGE_SIZE, POPULAR_TOP, rank_craving_results

logger = logging.getLogger(__name__)


def _build_message(
    parsed: dict[str, Any],
    count: int,
    *,
    live: bool,
    candidate_count: int = 0,
) -> str:
    if count == 0:
        if live:
            return "No matches — loosen diet filters or try a broader craving (tacos, chili, spicy ground beef)."
        return (
            "No demo matches — Spoonacular API key not detected on server. "
            "In Render → Environment, set SPOONACULAR_API_KEY and XAI_API_KEY exactly."
        )

    dish_anchor = parsed.get("dish_anchor")
    protein = parsed.get("protein")
    base = f"{count} recipes"
    if candidate_count > count:
        base = f"{count} top picks from {candidate_count} matches"

    if dish_anchor:
        family = dish_anchor.replace("_", " ")
        if protein:
            return f"{base} — {family} with {protein}. Top {POPULAR_TOP} most popular. Filter protein to refresh."
        return (
            f"{base} — different {family} preparations & styles. "
            f"Top {POPULAR_TOP} most popular. Filter by protein to narrow."
        )
    if protein:
        return f"{base} featuring {protein}. Top {POPULAR_TOP} most popular."
    return f"{base} for your craving. Top {POPULAR_TOP} most popular — filter by protein to refresh."


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
    fetch_error: str | None = None

    if use_live:
        from app.services import spoonacular

        try:
            result = await spoonacular.search_by_craving(
                parsed,
                diets=diets,
                intolerances=intolerances,
                what_sounds_good=what_sounds_good,
            )
            candidates = result.get("candidates") or []
            search_mock = False
            logger.info("live fetch: %d candidates for %r", len(candidates), what_sounds_good)
        except Exception as exc:
            fetch_error = str(exc)
            logger.exception("Spoonacular fetch failed: %s", exc)

    if search_mock:
        candidates = mock_data.mock_craving_candidates(
            parsed,
            what_sounds_good=what_sounds_good,
            diets=diets,
            intolerances=intolerances,
            health_conditions=health_conditions,
        )

    candidate_count = len(candidates)
    recipes = rank_craving_results(parsed, candidates)

    chef_headline, chef_intro, recipes, chef_mock = await enrich_with_chef_insight(
        what_sounds_good, parsed, recipes
    )

    live = use_live and not search_mock
    message = _build_message(parsed, len(recipes), live=live, candidate_count=candidate_count)

    if not live:
        if not settings.spoonacular_key:
            message = (
                f"Demo mode ({len(recipes)} recipes) — server does not see SPOONACULAR_API_KEY. "
                "Add the key in Render → Environment → SPOONACULAR_API_KEY, set USE_MOCK_DATA=false, redeploy."
            )
        elif fetch_error:
            message = f"Spoonacular error — showing demo. ({fetch_error[:120]})"

    return {
        "what_sounds_good": what_sounds_good,
        "parsed": parsed,
        "recipes": recipes,
        "chef_headline": chef_headline,
        "chef_intro": chef_intro,
        "page_size": PAGE_SIZE,
        "popular_top": POPULAR_TOP,
        "candidate_count": candidate_count,
        "message": message,
        "live": live,
    }, search_mock and parse_mock and chef_mock