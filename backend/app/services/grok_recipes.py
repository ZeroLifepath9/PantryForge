"""XAI Grok + AllRecipes: reality-show chef lineup from real recipes."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.services.allrecipes_scraper import (
    fetch_recipe_page,
    fetch_recipes_parallel,
    gather_search_hits,
    url_to_recipe_id,
)
from app.services.chef_agent import analyze_craving
from app.services.chef_relevance import collect_match_terms, is_relevant_main
from app.services.dish_families import detect_dish_anchor
from app.services.grok_recipe_store import put_many
from app.services.xai_client import chat_completion

logger = logging.getLogger(__name__)

PAGE_SIZE = 12

GROK_PICK = """You are the executive chef judge on a reality cooking competition (Top Chef / Iron Chef energy).

The home cook told you what sounds good. You receive REAL recipes scraped from AllRecipes.com — titles and URLs only.
Your job: pick up to 12 MAIN COURSES that nail their exact craving and respect every filter.

Output ONLY valid JSON:
{
  "chef_headline": "one punchy judge line tied to their exact words",
  "chef_intro": "2-3 sentences — why this lineup matches what they actually said",
  "picks": [
    {
      "url": "must be an exact URL from the list",
      "fit_note": "judge commentary citing their craving words — why THIS dish fits",
      "thread_label": "short style tag from the recipe title e.g. Roast chicken | Lemon pasta"
    }
  ]
}

RULES:
- Up to 12 picks. URLs must come from the provided list — do not invent recipes.
- Reject sauces-only, dips, news articles, grocery promos, unrelated dishes.
- Every pick must clearly match what_sounds_good — if you cannot tie it to their words, skip it.
- Prefer popular home-cook hits (higher rating_count when available).
- NEVER mention tacos, street food, or Mexican dishes unless what_sounds_good contains those concepts.
- Do not pad with unrelated recipes to reach 12 — fewer strong picks beats filler."""

_STOP = frozenset({
    "something", "with", "and", "the", "for", "that", "good", "sounds", "like",
    "want", "some", "have", "what", "your", "side", "fresh", "food", "meal",
})


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _search_queries(what_sounds_good: str, plan: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = q.strip()
        if len(q) >= 3 and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)

    add(what_sounds_good[:80])
    for term in plan.get("search_terms") or []:
        add(str(term))
    for thread in plan.get("craving_threads") or []:
        for term in (thread.get("search_terms") or [])[:6]:
            add(str(term))
    protein = plan.get("protein")
    if protein and protein != "vegetarian":
        add(f"{protein} {what_sounds_good[:40]}")
    return queries[:6]


def _title_matches_craving(title: str, what_sounds_good: str, plan: dict[str, Any]) -> bool:
    lower = title.lower()
    terms = collect_match_terms(plan, what_sounds_good)
    for term in terms:
        if term in lower:
            return True
    for w in re.findall(r"[a-z]{4,}", what_sounds_good.lower()):
        if w not in _STOP and w in lower:
            return True
    return False


def _is_main_title(title: str) -> bool:
    lower = title.lower()
    if any(x in lower for x in (" sauce", " dip", " dressing", " marinade only")):
        return False
    if lower.endswith(" sauce") or lower.endswith(" dip"):
        return False
    return True


def _filter_hits(hits: list[dict[str, Any]], plan: dict[str, Any], what_sounds_good: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hit in hits:
        title = hit.get("title") or ""
        if not _is_main_title(title):
            continue
        if not _title_matches_craving(title, what_sounds_good, plan):
            continue
        out.append(hit)
    return out


async def _grok_pick_lineup(
    hits: list[dict[str, Any]],
    *,
    what_sounds_good: str,
    plan: dict[str, Any],
    diets: list[str],
    intolerances: list[str],
    health_conditions: list[str],
    cuisine_filters: list[str],
    protein_filters: list[str],
    limit: int = PAGE_SIZE,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    slim = [{"title": h["title"], "url": h["url"], "search_query": h.get("search_query")} for h in hits[:50]]
    payload = {
        "what_sounds_good": what_sounds_good,
        "diets": diets,
        "intolerances": intolerances,
        "health_conditions": health_conditions,
        "cuisine_filters": cuisine_filters,
        "protein_filters": protein_filters,
        "dish_anchor": plan.get("dish_anchor"),
        "candidates": slim,
        "target_count": limit,
    }
    raw = await chat_completion(
        system=GROK_PICK,
        user_content=json.dumps(payload, ensure_ascii=False),
        temperature=0.35,
    )
    data = _extract_json(raw)
    by_url = {h["url"]: h for h in hits}
    picks: list[dict[str, Any]] = []
    for pick in data.get("picks") or []:
        url = (pick.get("url") or "").split("?")[0]
        if url not in by_url:
            continue
        row = dict(by_url[url])
        row["fit_note"] = str(pick.get("fit_note") or "Chef pick from AllRecipes.")
        row["thread_label"] = pick.get("thread_label") or "AllRecipes"
        picks.append(row)
        if len(picks) >= limit:
            break
    return data, picks


def _fallback_pick(hits: list[dict[str, Any]], limit: int = PAGE_SIZE) -> list[dict[str, Any]]:
    picks: list[dict[str, Any]] = []
    for hit in hits:
        row = dict(hit)
        row["fit_note"] = f"From AllRecipes — matches «{hit.get('search_query', 'your search')}»."
        row["thread_label"] = "AllRecipes"
        picks.append(row)
        if len(picks) >= limit:
            break
    return picks


async def search_craving_lineup(
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
    if protein_filter and protein_filter not in protein_filters:
        protein_filters = [protein_filter, *protein_filters]
    cuisine_filters = cuisine_filters or []
    selected_recipe_ids = (selected_recipe_ids or [])[:5]

    plan, _ = await analyze_craving(what_sounds_good, protein_filter=protein_filter)
    anchor, _ = detect_dish_anchor(what_sounds_good)
    plan["user_dish_anchor"] = bool(anchor)
    plan["dish_anchor"] = anchor
    if protein_filters:
        plan["protein"] = protein_filters[0]
    if cuisine_filters:
        plan["cuisine_filters"] = [c.lower() for c in cuisine_filters]
    plan["what_sounds_good"] = what_sounds_good
    plan["diets"] = diets
    plan["intolerances"] = intolerances
    plan["health_conditions"] = health_conditions

    queries = _search_queries(what_sounds_good, plan)
    hits = await gather_search_hits(queries, per_query=14)
    hits = _filter_hits(hits, plan, what_sounds_good)
    hits.sort(
        key=lambda h: (
            -(h.get("rating_count") or 0),
            -(h.get("rating") or 0),
        ),
    )

    grok_data: dict[str, Any] = {}
    picks: list[dict[str, Any]] = []
    used_grok = False

    if settings.xai_key and hits:
        try:
            grok_data, picks = await _grok_pick_lineup(
                hits,
                what_sounds_good=what_sounds_good,
                plan=plan,
                diets=diets,
                intolerances=intolerances,
                health_conditions=health_conditions,
                cuisine_filters=cuisine_filters,
                protein_filters=protein_filters,
            )
            used_grok = bool(picks)
        except Exception:
            logger.exception("Grok lineup pick failed")

    if not picks:
        picks = _fallback_pick(hits, limit=PAGE_SIZE)

    # Fetch full recipe pages from AllRecipes
    urls = [p["url"] for p in picks if p.get("url")]
    cards = await fetch_recipes_parallel(urls[:PAGE_SIZE + 4])

    # Merge judge notes onto cards
    meta_by_url = {p["url"]: p for p in picks}
    lineup: list[dict[str, Any]] = []
    for card in cards:
        url = card.get("source_url") or ""
        meta = meta_by_url.get(url, {})
        card["fit_note"] = meta.get("fit_note") or card.get("fit_note")
        card["thread_label"] = meta.get("thread_label") or "AllRecipes"
        card["is_popular"] = (card.get("rating_count") or 0) >= 50
        title = card.get("title") or ""
        if not _is_main_title(title):
            continue
        if is_relevant_main(card, plan, what_sounds_good=what_sounds_good)[0]:
            lineup.append(card)
        elif _title_matches_craving(title, what_sounds_good, plan):
            lineup.append(card)

    # Preserve user selections on refine
    if selected_recipe_ids:
        from app.services.grok_recipe_store import get

        for sid in selected_recipe_ids:
            if sid not in {c["id"] for c in lineup}:
                stored = get(sid)
                if stored:
                    lineup.insert(0, stored)

    lineup = lineup[:PAGE_SIZE]
    put_many(lineup)

    threads = plan.get("craving_threads") or []
    parsed = {
        "search_mode": "grok_allrecipes",
        "craving_threads": threads,
        "dish_anchor": anchor if plan.get("user_dish_anchor") else None,
        "dish_queries": queries,
        "protein": plan.get("protein"),
        "cuisine": plan.get("cuisine"),
        "flavor_notes": plan.get("flavor_notes") or [],
        "main_query": what_sounds_good,
        "search_terms": plan.get("search_terms") or queries,
        "needs_protein_prompt": not plan.get("protein"),
        "protein_options": plan.get("protein_options") or [],
    }

    live = bool(settings.xai_key) and used_grok and bool(lineup)
    if not lineup:
        message = "No AllRecipes matches for that search — try different keywords or loosen filters."
    elif not settings.xai_key:
        message = f"{len(lineup)} real recipes from AllRecipes. Set XAI_API_KEY for chef-judge curation."
    elif live:
        message = f"{len(lineup)} real AllRecipes mains — curated by your chef judge."
    else:
        message = f"{len(lineup)} real recipes from AllRecipes matching your search."

    return {
        "what_sounds_good": what_sounds_good,
        "parsed": parsed,
        "recipes": lineup,
        "chef_headline": grok_data.get("chef_headline") or plan.get("chef_headline"),
        "chef_intro": grok_data.get("chef_intro") or plan.get("chef_intro"),
        "craving_threads": threads,
        "page_size": PAGE_SIZE,
        "popular_top": 3,
        "candidate_count": len(hits),
        "message": message,
        "live": live,
        "refined": bool(selected_recipe_ids),
    }, not live