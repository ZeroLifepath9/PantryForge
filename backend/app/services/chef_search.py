"""Grok chef → Spoonacular fetch → 25 mains + pairing sides."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.services import mock_data
from app.services.chef_agent import analyze_craving, curate_lineup
from app.services.spoonacular import complex_search

logger = logging.getLogger(__name__)

PAGE_SIZE = 25
MAIN_TARGET = 18
SIDE_TARGET = 7


def _protein_query(term: str, protein: str | None) -> str:
    if not protein or protein == "vegetarian":
        return term
    return f"{protein} {term}".strip()


async def _search_term(
    query: str,
    *,
    diets: list[str],
    intolerances: list[str],
    number: int,
    dish_type: str | None,
    tag: str,
) -> list[dict[str, Any]]:
    try:
        batch = await complex_search(
            query=query,
            number=number,
            diets=diets,
            intolerances=intolerances,
            dish_type=dish_type,
            sort="popularity",
            sort_direction="desc",
        )
        out = []
        for card in batch:
            c = dict(card)
            c["source_tag"] = tag
            if dish_type == "main course":
                c["category"] = "main"
            out.append(c)
        return out
    except Exception as exc:
        logger.warning("Spoonacular query %r failed: %s", query, exc)
        return []


async def fetch_candidates(
    plan: dict[str, Any],
    *,
    diets: list[str],
    intolerances: list[str],
) -> list[dict[str, Any]]:
    protein = plan.get("protein")
    tasks: list[tuple[str, Any]] = []

    for thread in plan.get("craving_threads") or []:
        label = thread.get("label", "thread")
        for term in (thread.get("search_terms") or [])[:5]:
            q = _protein_query(str(term), protein)
            tasks.append(("main", _search_term(
                q, diets=diets, intolerances=intolerances,
                number=8, dish_type="main course", tag=label,
            )))

    bridge = plan.get("shared_bridge") or {}
    for term in (bridge.get("search_terms") or [])[:4]:
        tasks.append(("bridge", _search_term(
            _protein_query(str(term), protein),
            diets=diets, intolerances=intolerances,
            number=6, dish_type=None, tag=bridge.get("label", "bridge"),
        )))

    for term in (plan.get("pairing_side_terms") or [])[:8]:
        tasks.append(("side", _search_term(
            str(term),
            diets=diets, intolerances=intolerances,
            number=5, dish_type=None, tag="pairing",
        )))

    if not tasks:
        tasks.append(("main", _search_term(
            "dinner", diets=diets, intolerances=intolerances,
            number=25, dish_type=None, tag="general",
        )))

    results = await asyncio.gather(*[t[1] for t in tasks])
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    for batch in results:
        for card in batch:
            if card["id"] in seen:
                continue
            if protein == "vegetarian":
                diets_set = {d.lower() for d in (card.get("diets") or [])}
                if "vegetarian" not in diets_set and "vegan" not in diets_set:
                    continue
            seen.add(card["id"])
            candidates.append(card)

    return candidates


def _mock_candidates_from_plan(
    plan: dict[str, Any],
    *,
    what_sounds_good: str,
    diets: list[str],
    intolerances: list[str],
    health_conditions: list[str],
) -> list[dict[str, Any]]:
    parsed = {
        "craving_threads": plan.get("craving_threads"),
        "dish_queries": [
            t for th in (plan.get("craving_threads") or [])
            for t in (th.get("search_terms") or [])
        ],
        "dish_anchor": None,
        "protein": plan.get("protein"),
        "search_terms": [
            t for th in (plan.get("craving_threads") or [])
            for t in (th.get("search_terms") or [])
        ],
        "main_query": what_sounds_good,
    }
    if plan.get("craving_threads"):
        label = (plan["craving_threads"][0].get("label") or "").lower()
        if "taco" in label:
            parsed["dish_anchor"] = "taco"
        elif "chili" in label:
            parsed["dish_anchor"] = "chili"

    cards = mock_data.mock_craving_candidates(
        parsed,
        what_sounds_good=what_sounds_good,
        diets=diets,
        intolerances=intolerances,
        health_conditions=health_conditions,
    )
    # Pad with sides from mock pool
    for recipe in mock_data.MOCK_RECIPES:
        if len(cards) >= 40:
            break
        if recipe["id"] in {c["id"] for c in cards}:
            continue
        cat = mock_data._mock_recipe_category(recipe)
        if cat in ("side", "salad", "dip"):
            cards.append(mock_data._mock_card(recipe, cat))
    return cards


def _plan_to_parsed(plan: dict[str, Any]) -> dict[str, Any]:
    threads = plan.get("craving_threads") or []
    all_terms = [t for th in threads for t in (th.get("search_terms") or [])]
    bridge = plan.get("shared_bridge")
    return {
        "search_mode": "chef",
        "craving_threads": threads,
        "shared_bridge": bridge if isinstance(bridge, dict) else None,
        "dish_anchor": None,
        "dish_queries": all_terms,
        "protein": plan.get("protein"),
        "protein_query": plan.get("protein"),
        "ingredients": [],
        "starches": [],
        "flavors": [],
        "cuisine": None,
        "mood": None,
        "main_query": threads[0]["label"] if threads else "",
        "pairing_queries": plan.get("pairing_side_terms") or [],
        "search_terms": all_terms,
        "needs_protein_prompt": not plan.get("protein"),
        "protein_options": plan.get("protein_options") or [],
    }


async def chef_search(
    what_sounds_good: str,
    *,
    protein_filter: str | None = None,
    selected_recipe_ids: list[int] | None = None,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []
    selected_recipe_ids = (selected_recipe_ids or [])[:5]

    plan, analyze_mock = await analyze_craving(what_sounds_good, protein_filter=protein_filter)

    use_live = bool(settings.spoonacular_key) and not settings.mock_mode
    candidates: list[dict[str, Any]] = []
    fetch_mock = True

    if use_live:
        try:
            candidates = await fetch_candidates(plan, diets=diets, intolerances=intolerances)
            if candidates:
                fetch_mock = False
                logger.info("chef fetch: %d candidates", len(candidates))
        except Exception:
            logger.exception("chef Spoonacular fetch failed")

    if fetch_mock:
        candidates = _mock_candidates_from_plan(
            plan,
            what_sounds_good=what_sounds_good,
            diets=diets,
            intolerances=intolerances,
            health_conditions=health_conditions,
        )

    recipes, curate_mock = await curate_lineup(
        plan,
        candidates,
        selected_ids=selected_recipe_ids,
        limit=PAGE_SIZE,
    )

    if len(recipes) < PAGE_SIZE and fetch_mock:
        from app.services import mock_data as md

        seen = {r["id"] for r in recipes}
        for recipe in md.MOCK_RECIPES:
            if len(recipes) >= PAGE_SIZE:
                break
            if recipe["id"] in seen:
                continue
            cat = md._mock_recipe_category(recipe)
            c = md._mock_card(recipe, cat)
            c["fit_note"] = "Another option worth comparing."
            c["thread_label"] = "Chef's picks"
            recipes.append(c)
            seen.add(recipe["id"])

    live = use_live and not fetch_mock
    mains = sum(1 for r in recipes if r.get("category") == "main")
    sides = len(recipes) - mains

    message = (
        f"Chef's lineup: {len(recipes)} recipes ({mains} mains, {sides} sides & pairings)."
        if recipes
        else "No recipes found — try a broader craving or loosen diet filters."
    )
    if not live and recipes:
        message = f"Demo lineup ({len(recipes)}). Set SPOONACULAR_API_KEY + XAI_API_KEY on Render for live search."

    return {
        "what_sounds_good": what_sounds_good,
        "parsed": _plan_to_parsed(plan),
        "recipes": recipes,
        "chef_headline": plan.get("chef_headline"),
        "chef_intro": plan.get("chef_intro"),
        "craving_threads": plan.get("craving_threads") or [],
        "shared_bridge": plan.get("shared_bridge"),
        "page_size": PAGE_SIZE,
        "popular_top": 5,
        "candidate_count": len(candidates),
        "message": message,
        "live": live,
        "refined": bool(selected_recipe_ids),
    }, analyze_mock and curate_mock and fetch_mock