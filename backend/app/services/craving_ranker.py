"""Rank craving search candidates: top 5 popular, up to 25 per page."""

from __future__ import annotations

import re
from typing import Any

from app.services.dish_families import (
    FLAVOR_WORDS,
    dish_keywords,
    matches_dish_family,
    matches_source_query,
    mentions_protein,
)

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


def _real_ingredients(parsed: dict[str, Any]) -> list[str]:
    dish_words = {q.lower() for q in (parsed.get("dish_queries") or [])}
    anchor = parsed.get("dish_anchor")
    if anchor:
        dish_words.add(anchor.replace("_", " "))
    return [
        i.lower() for i in (parsed.get("ingredients") or [])
        if i and i.lower() not in FLAVOR_WORDS and i.lower() not in dish_words
    ]


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
        short = stem.rstrip("es").rstrip("s")
        if short and short in blob:
            hits += 1
    return hits


def _flavor_hits(card: dict[str, Any], flavors: list[str]) -> int:
    if not flavors:
        return 0
    blob = _blob(card)
    spicy_words = ("spicy", "hot", "chili", "chile", "jalapeño", "jalapeno", "cayenne", "habanero")
    hits = 0
    for flavor in flavors:
        f = flavor.lower()
        if f in blob:
            hits += 1
        elif f == "spicy" and any(w in blob for w in spicy_words):
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
    dish_queries = [q.lower() for q in (parsed.get("dish_queries") or [])]
    protein = (parsed.get("protein") or "").lower()
    ingredients = _real_ingredients(parsed)
    flavors = [f.lower() for f in (parsed.get("flavors") or [])]

    if dish_anchor and matches_dish_family(card, dish_anchor):
        score += 35.0
    if dish_queries and matches_source_query(card, dish_queries):
        score += 40.0
    for kw in dish_keywords(dish_anchor):
        if kw in blob:
            score += 5.0
    for dq in dish_queries:
        if dq in blob:
            score += 6.0

    if protein and mentions_protein(card, protein):
        score += 22.0

    score += _ingredient_hits(card, ingredients) * 10.0
    score += _flavor_hits(card, flavors) * 6.0

    for term in parsed.get("search_terms") or []:
        if term and term.lower() not in FLAVOR_WORDS and term in blob:
            score += 3.0

    score += min(_popularity(card) / 50.0, 15.0)
    return score


def _passes_inclusion(card: dict[str, Any], parsed: dict[str, Any], *, strict: bool) -> bool:
    dish_anchor = parsed.get("dish_anchor")
    dish_queries = [q.lower() for q in (parsed.get("dish_queries") or [])]
    protein = (parsed.get("protein") or "").lower()
    ingredients = _real_ingredients(parsed)

    if parsed.get("vegetarian_filter") and not _is_vegetarian_card(card):
        return False

    if not strict:
        return _relevance(card, parsed) >= 1.0

    dish_match = bool(dish_anchor and matches_dish_family(card, dish_anchor))
    from_query = bool(dish_queries and matches_source_query(card, dish_queries))
    protein_match = bool(protein and mentions_protein(card, protein))
    ing_hits = _ingredient_hits(card, ingredients)

    # Dish cravings: keep the whole family from Spoonacular queries, not random protein hits
    if dish_anchor:
        if dish_match or from_query:
            if protein and not protein_match:
                return False
            return True
        return False

    if protein and ingredients:
        return protein_match and ing_hits >= 1

    if protein:
        return protein_match

    if ingredients:
        return ing_hits >= 1

    return _relevance(card, parsed) >= 2.0


def _fit_note(card: dict[str, Any], parsed: dict[str, Any], *, popular: bool) -> str:
    dish_anchor = parsed.get("dish_anchor")
    protein = parsed.get("protein")
    ingredients = _real_ingredients(parsed)
    ing_hits = _ingredient_hits(card, ingredients)
    prefix = "Popular — " if popular else ""

    if dish_anchor and (matches_dish_family(card, dish_anchor) or matches_source_query(
        card, parsed.get("dish_queries") or []
    )):
        family = dish_anchor.replace("_", " ")
        if protein:
            return f"{prefix}{family.title()} with {protein}."
        return f"{prefix}Hits your {family} craving."

    if protein and ing_hits:
        return f"{prefix}{protein.title()} + {ing_hits} ingredient match."
    if protein:
        return f"{prefix}{protein.title()} forward."
    if ing_hits:
        return f"{prefix}Uses ingredients you mentioned."
    return f"{prefix}Matches what sounds good."


def rank_craving_results(
    parsed: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    eligible: list[dict[str, Any]] = []
    for card in candidates:
        if not _passes_inclusion(card, parsed, strict=True):
            continue
        enriched = dict(card)
        enriched["_relevance"] = _relevance(card, parsed)
        enriched["_popularity"] = _popularity(card)
        eligible.append(enriched)

    # If filters were too tight, relax and fill the page
    if len(eligible) < PAGE_SIZE:
        seen = {c["id"] for c in eligible}
        relaxed = []
        for card in candidates:
            if card["id"] in seen:
                continue
            if not _passes_inclusion(card, parsed, strict=False):
                continue
            enriched = dict(card)
            enriched["_relevance"] = _relevance(card, parsed)
            enriched["_popularity"] = _popularity(card)
            relaxed.append(enriched)
        relaxed.sort(key=lambda c: (c["_relevance"], c["_popularity"]), reverse=True)
        eligible.extend(relaxed[: PAGE_SIZE - len(eligible)])

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