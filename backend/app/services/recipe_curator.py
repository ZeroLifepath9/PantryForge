"""Grok curates which recipes fit the craving and presents them as one list."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.dish_families import dish_keywords, matches_dish_family
from app.services.xai_client import chat_completion

CURATOR_SYSTEM = """You curate recipes for AlchemyPantry.

Search mode guides what to pick:
- DISH mode (search_mode=dish): Keep taco-style / pasta / pizza family dishes AND adjacent types
  (e.g. tacos + burritos + fajitas + quesadillas). Do NOT drop adjacents just because the title
  says burrito instead of taco. If a protein filter is set, every pick must feature that protein.
- PROTEIN mode: Candidates feature a protein — pick mains first, then complementary sides.
- GENERAL: Best match to the craving text.

Mood, starches, and cuisine guide ordering and fit notes — not whether a dish belongs.

Output ONLY valid JSON:
{
  "recipes": [
    {
      "id": <recipe id from candidates only>,
      "fit_note": "one sentence: how this dish scratches the urge"
    }
  ]
}

Rules:
- Only use ids from the candidate list.
- DISH mode: include diverse adjacents from dish_queries; mains first.
- When protein is set, all picks must feature that protein.
- fit_note should hint at borrowing technique or flavor for a scratch creation.
"""

RECIPE_LIMIT = 25


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _candidate_index(candidates: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {c["id"]: c for c in candidates}


def mock_curate_recipes(
    what_sounds_good: str,
    parsed: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    protein = (parsed.get("protein") or "").lower()
    search_mode = (parsed.get("search_mode") or "general").lower()
    dish_anchor = parsed.get("dish_anchor")
    dish_queries = [q.lower() for q in (parsed.get("dish_queries") or [])]
    dish_kws = set(dish_keywords(dish_anchor))
    terms = set(parsed.get("search_terms") or [])
    if protein:
        terms.add(protein)
    for s in parsed.get("starches") or []:
        terms.add(s.lower())

    scored: list[tuple[int, dict[str, Any]]] = []
    for card in candidates:
        title = card.get("title", "").lower()
        summary = (card.get("summary") or "").lower()
        blob = f"{title} {summary}"
        score = 0
        if card.get("category") == "main":
            score += 2
        if search_mode == "dish" and dish_anchor:
            if matches_dish_family(card, dish_anchor):
                score += 12
            for dq in dish_queries:
                if dq in blob:
                    score += 6
            for kw in dish_kws:
                if kw in blob:
                    score += 4
            if protein and protein not in blob:
                score -= 20
        if protein and protein in blob:
            score += 8
        for t in terms:
            if t and t in blob:
                score += 3
        if parsed.get("mood") == "light" and any(w in blob for w in ("salad", "fresh", "light")):
            score += 2
        if parsed.get("mood") == "comfort" and any(w in blob for w in ("pasta", "cheese", "stew", "creamy")):
            score += 2
        if search_mode == "dish" and dish_anchor and matches_dish_family(card, dish_anchor):
            fit = f"{dish_anchor.replace('_', ' ').title()} vibe — borrow this approach for your plate."
        elif protein and protein in blob:
            if card.get("category") == "main":
                fit = f"{protein.title()} main — scratch the urge with this approach."
            else:
                fit = f"{protein.title()} {card.get('category', 'side')} — borrow flavors for your own plate."
        elif card.get("category") in ("salad", "side", "dip"):
            fit = "Side idea to mix into an inspired meal."
        else:
            fit = "Fits what sounds good."
        enriched = dict(card)
        enriched["fit_note"] = fit
        scored.append((score, enriched))

    scored.sort(key=lambda x: x[0], reverse=True)
    max_score = scored[0][0] if scored else 0
    if search_mode == "dish":
        min_score = 6 if dish_anchor else 1
    else:
        min_score = 4 if protein else 1
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for score, card in scored:
        if score < min_score and max_score > min_score:
            continue
        if card["id"] in seen:
            continue
        result.append(card)
        seen.add(card["id"])
        if len(result) >= RECIPE_LIMIT:
            break
    return result


async def curate_recipes(
    what_sounds_good: str,
    parsed: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    if not candidates:
        return [], not bool(settings.xai_key)

    if not settings.xai_key:
        return mock_curate_recipes(what_sounds_good, parsed, candidates), True

    slim = [
        {
            "id": c["id"],
            "title": c.get("title"),
            "category": c.get("category"),
            "summary": (c.get("summary") or "")[:200],
        }
        for c in candidates
    ]
    payload = {
        "what_sounds_good": what_sounds_good,
        "parsed": parsed,
        "candidates": slim,
    }
    try:
        text = await chat_completion(
            system=CURATOR_SYSTEM,
            user_content=json.dumps(payload, ensure_ascii=False),
            temperature=0.35,
        )
        raw = _extract_json(text)
        picks = raw.get("recipes") or []
        by_id = _candidate_index(candidates)
        curated: list[dict[str, Any]] = []
        seen: set[int] = set()
        for pick in picks:
            rid = pick.get("id")
            if rid is None or rid in seen or rid not in by_id:
                continue
            card = dict(by_id[rid])
            card["fit_note"] = str(pick.get("fit_note") or "Matches what sounds good.")
            curated.append(card)
            seen.add(rid)
            if len(curated) >= RECIPE_LIMIT:
                break
        if curated:
            return curated, False
    except Exception:
        pass

    return mock_curate_recipes(what_sounds_good, parsed, candidates), True