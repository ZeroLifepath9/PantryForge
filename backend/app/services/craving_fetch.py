"""Fetch a large candidate pool — one Spoonacular query per key term."""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.search_terms import collect_search_terms
from app.services.spoonacular import complex_search

POOL_TARGET = 150
PER_TERM = 12


async def _fetch_term(
    query: str,
    *,
    diets: list[str],
    intolerances: list[str],
    number: int = PER_TERM,
) -> list[dict[str, Any]]:
    try:
        batch = await complex_search(
            query=query,
            number=number,
            diets=diets,
            intolerances=intolerances,
            sort="popularity",
            sort_direction="desc",
        )
        tag = query.lower()
        out = []
        for card in batch:
            c = dict(card)
            c["category"] = c.get("category") or "main"
            c["source_queries"] = [tag]
            out.append(c)
        return out
    except Exception:
        return []


async def fetch_live_candidates(
    parsed: dict[str, Any],
    *,
    diets: list[str],
    intolerances: list[str],
    what_sounds_good: str = "",
) -> list[dict[str, Any]]:
    terms = collect_search_terms(parsed, what_sounds_good)
    if not terms:
        terms = [what_sounds_good or "dinner"]

    # Parallel fetches — many terms, many preparations
    batches = await asyncio.gather(
        *[
            _fetch_term(q, diets=diets, intolerances=intolerances, number=PER_TERM)
            for q in terms
        ]
    )

    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    for batch in batches:
        for card in batch:
            rid = card["id"]
            if rid in seen:
                for existing in candidates:
                    if existing["id"] == rid:
                        for sq in card.get("source_queries") or []:
                            if sq not in existing.setdefault("source_queries", []):
                                existing["source_queries"].append(sq)
                        break
                continue
            seen.add(rid)
            candidates.append(card)

    return candidates[:POOL_TARGET]