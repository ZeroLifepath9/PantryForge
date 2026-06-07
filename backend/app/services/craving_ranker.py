"""Rank candidates: keep breadth, top 5 popular, up to 25 on the page."""

from __future__ import annotations

import re
from typing import Any

from app.services.dish_families import mentions_protein

PAGE_SIZE = 25
POPULAR_TOP = 5


def _blob(card: dict[str, Any]) -> str:
    parts = [
        card.get("title") or "",
        card.get("summary") or "",
        " ".join(card.get("ingredient_names") or []),
        " ".join(card.get("source_queries") or []),
    ]
    return re.sub(r"[^a-z0-9]+", " ", " ".join(parts).lower()).strip()


def _is_vegetarian_card(card: dict[str, Any]) -> bool:
    diets = {d.lower() for d in (card.get("diets") or [])}
    return "vegetarian" in diets or "vegan" in diets


def _popularity(card: dict[str, Any]) -> float:
    for key in ("popularity", "aggregate_likes", "spoonacular_score"):
        val = card.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return 0.0


def _relevance(card: dict[str, Any], parsed: dict[str, Any]) -> float:
    blob = _blob(card)
    score = 10.0
    for term in parsed.get("search_terms") or []:
        if term and str(term).lower() in blob:
            score += 4.0
    for dq in parsed.get("dish_queries") or []:
        if dq.lower() in blob:
            score += 6.0
    protein = (parsed.get("protein") or "").lower()
    if protein and mentions_protein(card, protein):
        score += 15.0
    score += min(_popularity(card) / 40.0, 20.0)
    return score


def _apply_filters(candidates: list[dict[str, Any]], parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Only filter what the user explicitly asked for — never collapse broad searches."""
    protein = (parsed.get("protein") or "").lower()
    vegetarian = bool(parsed.get("vegetarian_filter"))

    pool = list(candidates)
    if vegetarian:
        pool = [c for c in pool if _is_vegetarian_card(c)]
    if protein:
        narrowed = [c for c in pool if mentions_protein(c, protein)]
        if narrowed:
            pool = narrowed
    return pool


def rank_craving_results(
    parsed: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    pool = _apply_filters(candidates, parsed)
    if not pool:
        pool = list(candidates)

    scored: list[dict[str, Any]] = []
    for card in pool:
        enriched = dict(card)
        enriched["_relevance"] = _relevance(card, parsed)
        enriched["_popularity"] = _popularity(card)
        scored.append(enriched)

    by_popularity = sorted(scored, key=lambda c: c["_popularity"], reverse=True)
    popular_picks = by_popularity[:POPULAR_TOP]
    popular_ids = {c["id"] for c in popular_picks}

    remainder = [c for c in scored if c["id"] not in popular_ids]
    remainder.sort(key=lambda c: (c["_relevance"], c["_popularity"]), reverse=True)

    ordered = popular_picks + remainder
    result: list[dict[str, Any]] = []
    for idx, card in enumerate(ordered[:PAGE_SIZE]):
        out = {k: v for k, v in card.items() if not k.startswith("_")}
        out["is_popular"] = idx < POPULAR_TOP and card["id"] in popular_ids
        result.append(out)
    return result