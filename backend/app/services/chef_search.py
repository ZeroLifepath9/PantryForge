"""Grok chef → Spoonacular fetch → 12 main-course lineup."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import settings
from app.services import mock_data
from app.services.chef_agent import analyze_craving, curate_lineup
from app.services.chef_relevance import enrich_search_plan, rank_and_filter_candidates
from app.services.dish_families import cuisine_for_anchor, family_adjacent_queries
from app.services.spoonacular import complex_search

logger = logging.getLogger(__name__)

PAGE_SIZE = 12
MAIN_TARGET = 12


def _protein_query(term: str, protein: str | None) -> str:
    if not protein or protein == "vegetarian":
        return term
    return f"{protein} {term}".strip()


def _resolve_cuisines(plan: dict[str, Any], cuisine_filters: list[str]) -> list[str | None]:
    user = [c.strip().lower() for c in (cuisine_filters or []) if c and c.strip()]
    if user:
        return user
    anchor_cuisine = cuisine_for_anchor(plan.get("dish_anchor"))
    if anchor_cuisine:
        return [anchor_cuisine]
    plan_cuisine = (plan.get("cuisine") or "").strip().lower()
    if plan_cuisine:
        return [plan_cuisine]
    return [None]


def _apply_user_filters(
    plan: dict[str, Any],
    *,
    protein_filter: str | None,
    protein_filters: list[str],
    side_filters: list[str],
    cuisine_filters: list[str],
) -> dict[str, Any]:
    plan = dict(plan)
    proteins = [p for p in (protein_filters or []) if p]
    if protein_filter and protein_filter not in proteins:
        proteins.insert(0, protein_filter)
    if proteins:
        plan["protein"] = proteins[0]
        plan["protein_filter"] = proteins[0]
    if cuisine_filters:
        plan["cuisine_filters"] = [c.strip().lower() for c in cuisine_filters if c]
        if plan["cuisine_filters"]:
            plan["cuisine"] = plan["cuisine_filters"][0]
    side_terms = list(plan.get("pairing_side_terms") or [])
    for term in side_filters or []:
        if term and term not in side_terms:
            side_terms.insert(0, term)
    if side_terms:
        plan["pairing_side_terms"] = side_terms[:12]
    return plan


def _is_main_candidate(card: dict[str, Any]) -> bool:
    return card.get("category") not in ("side", "salad", "dip")


async def _search_with_cuisine(
    query: str,
    *,
    diets: list[str],
    intolerances: list[str],
    number: int,
    dish_type: str | None,
    tag: str,
    cuisine: str | None,
) -> list[dict[str, Any]]:
    try:
        batch = await complex_search(
            query=query,
            number=number,
            diets=diets,
            intolerances=intolerances,
            dish_type=dish_type,
            cuisine=cuisine,
            sort="popularity",
            sort_direction="desc",
        )
        out = []
        for card in batch:
            if not _is_main_candidate(card):
                continue
            c = dict(card)
            c["source_tag"] = tag
            c["source_queries"] = c.get("source_queries") or [query]
            if cuisine:
                c["source_cuisine"] = cuisine
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
    cuisine_filters: list[str] | None = None,
    what_sounds_good: str = "",
) -> list[dict[str, Any]]:
    protein = plan.get("protein")
    cuisines = _resolve_cuisines(plan, cuisine_filters or [])
    tasks: list[Any] = []

    def queue_search(
        query: str,
        *,
        number: int,
        dish_type: str | None,
        tag: str,
    ) -> None:
        q = _protein_query(query, protein)
        for cuisine in cuisines:
            tasks.append(_search_with_cuisine(
                q,
                diets=diets,
                intolerances=intolerances,
                number=number,
                dish_type=dish_type,
                tag=tag,
                cuisine=cuisine,
            ))

    craving_q = (what_sounds_good or plan.get("what_sounds_good") or "").strip()[:80]
    if craving_q:
        queue_search(craving_q, number=10, dish_type="main course", tag="Your craving")

    anchor = plan.get("dish_anchor")
    for term in family_adjacent_queries(anchor)[:14]:
        queue_search(str(term), number=6, dish_type="main course", tag="Dish family")

    for term in (plan.get("street_food_terms") or [])[:8]:
        queue_search(str(term), number=6, dish_type=None, tag="Street food")

    for thread in plan.get("craving_threads") or []:
        label = thread.get("label", "thread")
        for i, term in enumerate((thread.get("search_terms") or [])[:10]):
            dish_type = "main course" if i % 2 == 0 else None
            queue_search(str(term), number=5, dish_type=dish_type, tag=label)

    bridge = plan.get("shared_bridge") or {}
    for term in (bridge.get("search_terms") or [])[:4]:
        queue_search(str(term), number=5, dish_type="main course", tag=bridge.get("label", "bridge"))

    if not tasks:
        queue_search("dinner", number=15, dish_type="main course", tag="general")

    results = await asyncio.gather(*tasks)
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    for batch in results:
        for card in batch:
            if card["id"] in seen:
                continue
            if not _is_main_candidate(card):
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
        "dish_anchor": plan.get("dish_anchor"),
        "protein": plan.get("protein"),
        "search_terms": [
            *(plan.get("street_food_terms") or []),
            *[t for th in (plan.get("craving_threads") or []) for t in (th.get("search_terms") or [])],
            *family_adjacent_queries(plan.get("dish_anchor")),
        ],
        "main_query": what_sounds_good,
        "search_mode": "dish" if plan.get("dish_anchor") else "chef",
        "cuisine_filters": plan.get("cuisine_filters") or [],
    }

    cards = mock_data.mock_craving_candidates(
        parsed,
        what_sounds_good=what_sounds_good,
        diets=diets,
        intolerances=intolerances,
        health_conditions=health_conditions,
    )
    return [c for c in cards if _is_main_candidate(c)]


def _plan_to_parsed(plan: dict[str, Any]) -> dict[str, Any]:
    threads = plan.get("craving_threads") or []
    all_terms = [t for th in threads for t in (th.get("search_terms") or [])]
    bridge = plan.get("shared_bridge")
    anchor = plan.get("dish_anchor")
    return {
        "search_mode": "chef",
        "craving_threads": threads,
        "shared_bridge": bridge if isinstance(bridge, dict) else None,
        "dish_anchor": anchor,
        "dish_queries": all_terms + family_adjacent_queries(anchor),
        "protein": plan.get("protein"),
        "protein_query": plan.get("protein"),
        "ingredients": [],
        "starches": [],
        "flavors": [],
        "cuisine": plan.get("cuisine"),
        "mood": None,
        "main_query": threads[0]["label"] if threads else "",
        "pairing_queries": plan.get("pairing_side_terms") or [],
        "street_food_terms": plan.get("street_food_terms") or [],
        "search_terms": all_terms,
        "needs_protein_prompt": not plan.get("protein"),
        "protein_options": plan.get("protein_options") or [],
    }


async def chef_search(
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
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []
    protein_filters = protein_filters or []
    side_filters = side_filters or []
    cuisine_filters = cuisine_filters or []
    selected_recipe_ids = (selected_recipe_ids or [])[:5]

    plan, analyze_mock = await analyze_craving(what_sounds_good, protein_filter=protein_filter)
    plan = _apply_user_filters(
        plan,
        protein_filter=protein_filter,
        protein_filters=protein_filters,
        side_filters=side_filters,
        cuisine_filters=cuisine_filters,
    )
    plan = enrich_search_plan(
        plan,
        what_sounds_good,
        side_filters=side_filters,
        cuisine_filters=cuisine_filters,
    )

    use_live = bool(settings.spoonacular_key) and not settings.mock_mode
    candidates: list[dict[str, Any]] = []
    fetch_mock = True

    if use_live:
        try:
            candidates = await fetch_candidates(
                plan,
                diets=diets,
                intolerances=intolerances,
                cuisine_filters=cuisine_filters,
                what_sounds_good=what_sounds_good,
            )
            if candidates:
                fetch_mock = False
                logger.info("chef fetch: %d main candidates", len(candidates))
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

    candidates = rank_and_filter_candidates(
        candidates,
        plan,
        what_sounds_good=what_sounds_good,
        max_pool=60,
        min_score=8.0,
        mains_only=True,
    )

    recipes, curate_mock = await curate_lineup(
        plan,
        candidates,
        selected_ids=selected_recipe_ids,
        limit=PAGE_SIZE,
        mains_only=True,
    )

    recipes = [r for r in recipes if _is_main_candidate(r)][:PAGE_SIZE]

    if len(recipes) < PAGE_SIZE and fetch_mock:
        from app.services import mock_data as md

        seen = {r["id"] for r in recipes}
        for recipe in md.MOCK_RECIPES:
            if len(recipes) >= PAGE_SIZE:
                break
            if recipe["id"] in seen:
                continue
            cat = md._mock_recipe_category(recipe)
            if cat in ("side", "salad", "dip"):
                continue
            c = md._mock_card(recipe, "main")
            c["fit_note"] = "Another main worth comparing."
            c["thread_label"] = "Chef's picks"
            recipes.append(c)
            seen.add(recipe["id"])

    live = use_live and not fetch_mock

    message = (
        f"Chef's lineup: {len(recipes)} main courses inspired by what sounds good."
        if recipes
        else "No main courses found — try a broader craving, cuisine, or loosen diet filters."
    )
    if not live and recipes:
        message = (
            f"Demo lineup ({len(recipes)} mains). "
            "Set SPOONACULAR_API_KEY + XAI_API_KEY on Render for live search."
        )

    return {
        "what_sounds_good": what_sounds_good,
        "parsed": _plan_to_parsed(plan),
        "recipes": recipes,
        "chef_headline": plan.get("chef_headline"),
        "chef_intro": plan.get("chef_intro"),
        "craving_threads": plan.get("craving_threads") or [],
        "shared_bridge": plan.get("shared_bridge"),
        "page_size": PAGE_SIZE,
        "popular_top": 3,
        "candidate_count": len(candidates),
        "message": message,
        "live": live,
        "refined": bool(selected_recipe_ids),
    }, analyze_mock and curate_mock and fetch_mock