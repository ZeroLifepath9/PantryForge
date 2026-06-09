"""XAI Grok + AllRecipes: reality-show chef lineup from real recipes."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import settings
from app.services.allrecipes_scraper import fetch_recipes_parallel
from app.services.chef_relevance import collect_match_terms, is_relevant_main
from app.services.craving_translator import translate_craving
from app.services.recipe_discovery import discover_recipe_hits
from app.services.grok_recipe_store import put_many
from app.services.xai_client import chat_completion

logger = logging.getLogger(__name__)

PAGE_SIZE = 25

GROK_PICK = """You are the executive chef judge on a reality cooking competition (Top Chef / Iron Chef energy).

The home cook described a *flavor profile* using the current input + their past inputs/history (see derived_flavor_profile, user_past_flavor_profile, past_cravings_summary). You receive REAL recipes scraped from AllRecipes.com — titles and URLs only.

Current input example flavor: tacos or chili or gumbo, something spicy or Mexican like. What they have in common: bold spicy heat, savory depth, Mexican/Tex-Mex/Cajun vibes (cumin, chili powder, peppers, onions, garlic, tomatoes, hearty, often with meat/beans/rice, tangy/acidic finishes). The profile is spicy, bold, comforting, flavorful stew-like or spiced meat dishes.

Your job: curate a rich, expanded *array of up to 25 options* (mains + accents) **inspired by the common derived flavor profile** (spicy Mexican-like with chili/gumbo/taco elements). Explicitly include recipes inspired by tacos (spiced taco meat, fillings, bowls), chili (hearty stews), gumbo (spicy roux-like stews), and similar (fajitas, enchiladas, jambalaya, spicy beans, etc.). Also include side dishes, dips, appetizers, accents that perfectly match and enhance the flavor profile (e.g. cornbread, slaw, rice, guac, salsa, remoulade, beans, etc.).

The array must cover all mentioned (tacos, chili, gumbo) plus the common profile - NOT just chili. Aim for 25 to fill the 5x5 grid with variety in preps of the profile; if fewer perfect matches, include strong accents/sides that share the flavor.

Priorities (in order):
1. Protein-forward where applicable: mains feature the protein as star.
2. Common flavor profile first: All 25 must deliver the spicy, bold, Mexican/Cajun hearty savory heat profile. Use examples as inspiration for variety in form, not limits. Include cross if flavor matches (e.g. spicy stew from other cuisines).
3. Keyword & profile match: Tie to input text, parsed, flavors (spicy), profile.
4. Home versions mirroring restaurant: Strong fit_notes explaining the flavor bridge.
5. Exactly 25 for 5x5 grid: Mix mains inspired by each mentioned + profile-matching accents/sides/dips/appetizers to fill to 25.

Output ONLY valid JSON:
{
  "chef_headline": "one punchy judge line tied to the common spicy Mexican/gumbo/chili/taco flavor profile",
  "chef_intro": "2-3 sentences — why this 25-item array covers tacos, chili, gumbo and the shared profile with variety and accents",
  "picks": [
    {
      "url": "must be an exact URL from the list",
      "fit_note": "how this reflects the common flavor profile (spicy bold Mexican-like) and which element (taco/chili/gumbo/side) it draws from",
      "thread_label": "short style tag e.g. Spiced Taco Skillet | Hearty Chili Stew | Gumbo-Style Bowl | Chili-Lime Slaw"
    }
  ]
}

RULES:
- Up to 25 picks for 5-wide x 5-deep grid. Must include distinct options inspired by tacos, by chili, by gumbo, plus the common profile. Fill with accent sides/dips/appetizers that accent the exact flavor (not random).
- URLs from list only.
- Reject unrelated. Every must match the spicy/Mexican-like profile from the input.
- Do not over-represent only chili. Balanced coverage of all.
- Prefer popular home-cook. Expand to 25 generously from good candidates."""

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


def _search_queries(plan: dict[str, Any]) -> list[str]:
    """Use translator-built queries only — never the raw sentence."""
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = q.strip()
        if len(q) >= 3 and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)

    for term in plan.get("search_queries") or plan.get("search_terms") or []:
        add(str(term))
    return queries[:15]  # more queries for compound inputs to pull diverse chili/taco/gumbo + fusion candidates


def _title_matches_craving(
    title: str,
    what_sounds_good: str,
    plan: dict[str, Any],
    *,
    search_query: str = "",
) -> bool:
    lower = title.lower()
    sq = (search_query or "").lower()
    if sq:
        for word in re.findall(r"[a-z]{3,}", sq):
            if word not in _STOP and word in lower:
                return True
    for kw in plan.get("match_keywords") or []:
        if kw in lower:
            return True
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
        if not _title_matches_craving(
            title, what_sounds_good, plan, search_query=hit.get("search_query") or ""
        ):
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
        "flavor_profile": plan.get("flavor_profile", ""),
        "derived_flavor_profile": plan.get("derived_flavor_profile", plan.get("flavor_profile", "")),
        "past_cravings_summary": plan.get("past_cravings_summary", ""),
        "user_past_flavor_profile": plan.get("user_past_flavor_profile", {}),
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
    user_flavor_profile: dict | None = None,
    craving_history: list[dict] | None = None,
) -> tuple[dict[str, Any], bool]:
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []
    protein_filters = protein_filters or []
    if protein_filter and protein_filter not in protein_filters:
        protein_filters = [protein_filter, *protein_filters]
    cuisine_filters = cuisine_filters or []
    selected_recipe_ids = (selected_recipe_ids or [])[:5]

    plan, _ = await translate_craving(what_sounds_good, protein_filter=protein_filter)
    anchor = plan.get("dish_anchor")
    if protein_filters:
        plan["protein"] = protein_filters[0]
    if cuisine_filters:
        plan["cuisine_filters"] = [c.lower() for c in cuisine_filters]
    plan["what_sounds_good"] = what_sounds_good
    plan["diets"] = diets
    plan["intolerances"] = intolerances
    plan["health_conditions"] = health_conditions

    # Blend current input with user's past flavor profile / history for "inspired by derived profile from past + current"
    past_summary = ""
    if craving_history:
        past_summary = "; ".join([h.get("what_sounds_good", "") for h in craving_history[-3:]])
    if user_flavor_profile:
        plan["user_past_flavor_profile"] = user_flavor_profile
        plan["past_cravings_summary"] = past_summary
        # Derive blended for this search
        current_fp = plan.get("flavor_profile", "")
        past_fp = user_flavor_profile.get("description", "") or user_flavor_profile.get("flavor_profile", "")
        if past_fp and current_fp:
            plan["derived_flavor_profile"] = f"User's evolving flavor profile: {past_fp}. Current craving adds: {current_fp}. Combined: spicy Mexican-inspired with taco, chili, and gumbo elements, hearty and bold."
        else:
            plan["derived_flavor_profile"] = current_fp or past_fp
    else:
        plan["derived_flavor_profile"] = plan.get("flavor_profile", "")

    queries = _search_queries(plan)
    if not queries:
        queries = [what_sounds_good.strip()[:40]] if what_sounds_good.strip() else ["dinner"]

    # Gather more candidates so Grok can curate a rich 15-25 protein + keyword + flavor-profile lineup
    hits, recipe_source = await discover_recipe_hits(
        queries,
        per_query=25,
        diets=diets,
        intolerances=intolerances,
    )
    if hits:
        filtered = _filter_hits(hits, plan, what_sounds_good)
        hits = filtered if filtered else hits
    if not hits:
        hits, recipe_source = await discover_recipe_hits(
            queries[:4],
            per_query=30,
            diets=diets,
            intolerances=intolerances,
        )
        if hits:
            filtered = _filter_hits(hits, plan, what_sounds_good)
            hits = filtered if filtered else hits
    hits.sort(
        key=lambda h: (
            -(h.get("rating_count") or 0),
            -(h.get("rating") or 0),
        ),
    )

    grok_data: dict[str, Any] = {}
    picks: list[dict[str, Any]] = []
    used_grok = False

    url_based = recipe_source in ("allrecipes", "allrecipes-ddg")
    if settings.xai_key and hits and url_based:
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

    full_picks = [p for p in picks if p.get("_full_card")]
    url_picks = [p for p in picks if p.get("url") and not p.get("_full_card")]
    cards: list[dict[str, Any]] = list(full_picks)
    if url_picks:
        urls = [p["url"] for p in url_picks]
        cards.extend(await fetch_recipes_parallel(urls[:PAGE_SIZE + 4]))

    if not cards and recipe_source not in ("themealdb", "spoonacular"):
        from app.services.themealdb import gather_themealdb_hits

        emergency = await gather_themealdb_hits(queries, per_query=14)
        if emergency:
            recipe_source = "themealdb"
            cards = emergency[:PAGE_SIZE]
            picks = emergency[:PAGE_SIZE]

    # Merge judge notes onto cards
    meta_by_url = {p["url"]: p for p in picks if p.get("url")}
    lineup: list[dict[str, Any]] = []
    for card in cards:
        url = card.get("source_url") or ""
        meta = meta_by_url.get(url, {})
        card["fit_note"] = meta.get("fit_note") or card.get("fit_note")
        card["thread_label"] = meta.get("thread_label") or "AllRecipes"
        if meta.get("search_query"):
            card["source_queries"] = [meta["search_query"]]
        card["is_popular"] = (card.get("rating_count") or 0) >= 50
        title = card.get("title") or ""
        if not _is_main_title(title):
            continue
        sq = meta.get("search_query") or ""
        if is_relevant_main(card, plan, what_sounds_good=what_sounds_good)[0]:
            lineup.append(card)
        elif _title_matches_craving(title, what_sounds_good, plan, search_query=sq):
            lineup.append(card)

    if not lineup and cards:
        for card in cards:
            title = card.get("title") or ""
            if not _is_main_title(title):
                continue
            lineup.append(card)
            if len(lineup) >= PAGE_SIZE:
                break

    # Preserve user selections on refine
    if selected_recipe_ids:
        from app.services.grok_recipe_store import get

        for sid in selected_recipe_ids:
            if sid not in {c["id"] for c in lineup}:
                stored = get(sid)
                if stored:
                    lineup.insert(0, stored)

    # Fill to 25 with profile-matching accents/sides/dips/appetizers if needed (for 5x5 grid)
    if len(lineup) < PAGE_SIZE:
        for card in cards:
            if len(lineup) >= PAGE_SIZE:
                break
            title = card.get("title") or ""
            if _is_main_title(title):
                continue
            lower_title = title.lower()
            profile_kws = ["salsa", "guac", "slaw", "cornbread", "rice", "beans", "dip", "appetizer", "side", "chili", "taco", "gumbo", "spicy", "mexican"]
            if any(kw in lower_title for kw in profile_kws):
                card["fit_note"] = card.get("fit_note") or "Accent/side that enhances the spicy Mexican/gumbo/chili/taco flavor profile"
                card["thread_label"] = card.get("thread_label") or "Flavor Accent"
                lineup.append(card)

    lineup = lineup[:PAGE_SIZE]

    # Safety net: if still very few (e.g. strict filtering), take top from hits to ensure results
    if len(lineup) < 5:
        for card in hits[:PAGE_SIZE]:
            if len(lineup) >= PAGE_SIZE:
                break
            if card not in lineup:  # rough dedup
                title = card.get("title") or ""
                if _is_main_title(title) or any(kw in (title or "").lower() for kw in ["chili","taco","gumbo","spicy","mexican"]):
                    card["fit_note"] = card.get("fit_note") or "Matches your spicy Mexican-like profile (tacos/chili/gumbo elements)"
                    card["thread_label"] = card.get("thread_label") or "Profile Match"
                    lineup.append(card)

    lineup = lineup[:PAGE_SIZE]
    put_many(lineup)

    threads = plan.get("craving_threads") or []
    parsed = {
        "search_mode": plan.get("search_mode") or "grok_allrecipes",
        "craving_threads": threads,
        "dish_anchor": anchor if plan.get("user_dish_anchor") else None,
        "dish_queries": plan.get("dish_queries") or [],
        "protein": plan.get("protein"),
        "protein_query": plan.get("protein_query"),
        "ingredients": plan.get("ingredients") or [],
        "starches": plan.get("starches") or [],
        "flavors": plan.get("flavors") or [],
        "cuisine": plan.get("cuisine"),
        "mood": plan.get("mood"),
        "main_query": plan.get("main_query") or what_sounds_good,
        "search_terms": plan.get("search_queries") or queries,
        "needs_protein_prompt": plan.get("needs_protein_prompt", not plan.get("protein")),
        "protein_options": plan.get("protein_options") or [],
    }

    source_labels = {
        "allrecipes": "AllRecipes",
        "allrecipes-ddg": "AllRecipes",
        "themealdb": "TheMealDB",
        "spoonacular": "Spoonacular",
    }
    src_label = source_labels.get(recipe_source, "recipe search")

    live = bool(settings.xai_key) and used_grok and bool(lineup)
    if not lineup:
        message = "No matches found — try a simpler craving like chicken, pasta, or cheesy comfort food."
    elif live:
        message = f"{len(lineup)} chef-curated mains (expanded 15-25 lineup) — protein-centric, keyword-driven, with cross-flavor-profile suggestions (e.g. Med or Asian mirrors for Mexican-style urges) that capture restaurant essence in homemade form."
    elif recipe_source == "themealdb":
        message = f"{len(lineup)} popular recipes matching your craving (TheMealDB)."
    else:
        message = f"{len(lineup)} recipes from {src_label} matching your search."

    return {
        "what_sounds_good": what_sounds_good,
        "parsed": parsed,
        "recipes": lineup,
        "chef_headline": grok_data.get("chef_headline") or plan.get("chef_headline") or "",
        "chef_intro": grok_data.get("chef_intro") or plan.get("chef_intro") or "",
        "translated_queries": queries,
        "craving_threads": threads,
        "page_size": PAGE_SIZE,
        "popular_top": 3,
        "candidate_count": len(hits),
        "recipe_source": recipe_source,
        "message": message,
        "live": live,
        "refined": bool(selected_recipe_ids),
    }, not live