"""Rank craving search candidates: top 5 popular, 25 per page."""

from __future__ import annotations

import re
from typing import Any

from app.services.dish_families import dish_keywords, matches_dish_family

PAGE_SIZE = 25
POPULAR_TOP = 5


def _blob(card: dict[str, Any]) -> str:
    parts = [
        card.get("title") or "",
        card.get("summary") or "",
        " ".join(card.get("ingredient_names") or []),
    ]
    return re.sub(r"[^a-z0-9]+", " ", " ".join(parts).lower()).strip()


def _mentions_protein(card: dict[str, Any], protein: str) -> bool:
    return protein in _blob(card)


def _is_vegetarian_card(card: dict[str, Any]) -> bool:
    diets = {d.lower() for d in (card.get("diets") or [])}
    return "vegetarian" in diets or "vegan" in diets


def _ingredient_hits(card: dict[str, Any], ingredients: list[str]) -> int:
    if not ingredients:
        return 0
    blob = _blob(card)
    hits = 0
    for ing in ingredients:
        stem = ing.lower().strip()
        if not stem:
            continue
        if stem in blob:
            hits += 1
            continue
        # tolerate simple stems (tomatoes → tomato)
        if stem.rstrip("es").rstrip("s") in blob:
            hits += 1
    return hits


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
    score = 0.0
    blob = _blob(card)
    dish_anchor = parsed.get("dish_anchor")
    protein = (parsed.get("protein") or "").lower()
    ingredients = [i.lower() for i in (parsed.get("ingredients") or [])]

    if dish_anchor and matches_dish_family(card, dish_anchor):
        score += 30.0
        for kw in dish_keywords(dish_anchor):
            if kw in blob:
                score += 4.0

    if protein and _mentions_protein(card, protein):
        score += 20.0

    ing_hits = _ingredient_hits(card, ingredients)
    score += ing_hits * 8.0

    for term in parsed.get("search_terms") or []:
        if term and term in blob:
            score += 3.0

    if parsed.get("mood") == "light" and any(w in blob for w in ("salad", "fresh", "light")):
        score += 4.0
    if parsed.get("mood") == "comfort" and any(w in blob for w in ("cheese", "creamy", "stew")):
        score += 4.0

    score += min(_popularity(card) / 100.0, 10.0)
    return score


def _passes_inclusion(card: dict[str, Any], parsed: dict[str, Any]) -> bool:
    dish_anchor = parsed.get("dish_anchor")
    protein = (parsed.get("protein") or "").lower()
    ingredients = [i.lower() for i in (parsed.get("ingredients") or []) if i]

    if parsed.get("vegetarian_filter") and not _is_vegetarian_card(card):
        return False

    dish_match = bool(dish_anchor and matches_dish_family(card, dish_anchor))
    protein_match = bool(protein and _mentions_protein(card, protein))
    ing_hits = _ingredient_hits(card, ingredients)

    # Dish path: all relevant taco-style (etc.) recipes
    if dish_match:
        if protein and not protein_match:
            return False
        return True

    # Protein + some ingredients path
    if protein and ingredients:
        return protein_match and ing_hits >= 1

    if protein and not dish_anchor:
        return protein_match

    if ingredients and not dish_anchor:
        return ing_hits >= 1

    if dish_anchor:
        return False

    return _relevance(card, parsed) >= 3.0


def _fit_note(card: dict[str, Any], parsed: dict[str, Any], *, popular: bool) -> str:
    dish_anchor = parsed.get("dish_anchor")
    protein = parsed.get("protein")
    ingredients = parsed.get("ingredients") or []
    ing_hits = _ingredient_hits(card, ingredients)

    prefix = "Popular pick — " if popular else ""
    if dish_anchor and matches_dish_family(card, dish_anchor):
        family = dish_anchor.replace("_", " ")
        if protein:
            return f"{prefix}{family.title()} dish with {protein}."
        return f"{prefix}Fits your {family} craving."

    if protein and ing_hits:
        return f"{prefix}{protein.title()} with {ing_hits} of your ingredients."
    if protein:
        return f"{prefix}Features {protein}."
    if ing_hits:
        return f"{prefix}Uses {ing_hits} ingredient{'s' if ing_hits != 1 else ''} you mentioned."
    return f"{prefix}Matches what sounds good."


def rank_craving_results(
    parsed: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return up to 25 recipes; top 5 slots reserved for most popular matches."""
    eligible: list[dict[str, Any]] = []
    for card in candidates:
        if not _passes_inclusion(card, parsed):
            continue
        enriched = dict(card)
        enriched["_relevance"] = _relevance(card, parsed)
        enriched["_popularity"] = _popularity(card)
        eligible.append(enriched)

    if not eligible:
        return []

    by_popularity = sorted(eligible, key=lambda c: c["_popularity"], reverse=True)
    popular_picks = by_popularity[:POPULAR_TOP]
    popular_ids = {c["id"] for c in popular_picks}

    remainder = [c for c in eligible if c["id"] not in popular_ids]
    remainder.sort(key=lambda c: (c["_relevance"], c["_popularity"]), reverse=True)

    ordered = popular_picks + remainder
    result: list[dict[str, Any]] = []
    for idx, card in enumerate(ordered[:PAGE_SIZE]):
        out = {k: v for k, v in card.items() if not k.startswith("_")}
        is_popular = idx < POPULAR_TOP and card["id"] in popular_ids
        out["is_popular"] = is_popular
        out["fit_note"] = _fit_note(card, parsed, popular=is_popular)
        result.append(out)
    return result