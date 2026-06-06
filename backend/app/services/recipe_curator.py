"""Grok curates which recipes fit the craving and presents them as one list."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.xai_client import chat_completion

CURATOR_SYSTEM = """You curate recipes for AlchemyPantry based on what sounds good to the cook.
You receive their craving text and a candidate recipe list from Spoonacular.

Pick up to 25 recipes that best fit the craving. Include mains with named proteins when relevant,
plus sides, salads, and dips when the craving implies a full meal or those words appear.

Output ONLY valid JSON, no markdown:
{
  "recipes": [
    {
      "id": <recipe id from candidates only>,
      "fit_note": "one short sentence why this matches the craving"
    }
  ]
}

Rules:
- Only use ids from the candidate list.
- Order best match first.
- Do not duplicate ids.
- If protein is named, prioritize mains containing that protein in the first 5 slots when possible.
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
        if protein and protein in blob:
            score += 8
        for t in terms:
            if t and t in blob:
                score += 3
        if parsed.get("mood") == "light" and any(w in blob for w in ("salad", "fresh", "light")):
            score += 2
        if parsed.get("mood") == "comfort" and any(w in blob for w in ("pasta", "cheese", "stew", "creamy")):
            score += 2
        fit = "Fits your craving."
        if protein and protein in blob:
            fit = f"Matches your {protein} craving."
        elif card.get("category") in ("salad", "side", "dip"):
            fit = "Pairs well with your meal idea."
        enriched = dict(card)
        enriched["fit_note"] = fit
        scored.append((score, enriched))

    scored.sort(key=lambda x: x[0], reverse=True)
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for _, card in scored:
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
        return [], not bool(settings.xai_api_key)

    if not settings.xai_api_key:
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