"""Score and rank Spoonacular candidates against the chef plan and craving."""

from __future__ import annotations

import re
from typing import Any

from app.services.dish_families import (
    detect_dish_anchor,
    dish_keywords,
    matches_dish_family,
    mentions_protein,
)

_STOPWORDS = frozenset({
    "something", "with", "and", "the", "for", "that", "good", "sounds", "like",
    "want", "some", "have", "what", "your", "side", "fresh", "food", "meal",
    "easy", "popular", "recipe", "recipes",
})

STREET_FOOD_TERMS: dict[str, list[str]] = {
    "taco": [
        "street taco", "birria taco", "al pastor taco", "carnitas taco",
        "fish taco", "carne asada taco", "taco truck", "taqueria",
    ],
    "chili": ["bowl of chili", "texas chili", "chili dog", "chili bowl"],
    "burger": ["smash burger", "street burger", "slider burger", "food truck burger"],
    "pizza": ["street pizza", "flatbread", "margherita pizza"],
    "pasta": ["street pasta", "quick pasta", "one pan pasta"],
    "curry": ["street curry", "kathi roll", "curry bowl"],
    "stir_fry": ["street noodles", "pad thai", "dan dan noodles"],
}

PAIRING_ACCENTS: dict[str, list[tuple[str, str]]] = {
    "taco": [
        ("elote mexican street corn", "charred-sweet corn accents rich taco fillings"),
        ("pickled onions", "acid crunch cuts fat — classic taqueria pairing"),
        ("cilantro lime rice", "herb-citrus base rounds the plate"),
        ("easy black beans", "popular earthy side — balances spiced mains"),
        ("pico de gallo", "bright salsa lifts every bite"),
        ("guacamole", "creamy fat tames heat"),
        ("refried beans", "comfort side — scoop with tortillas"),
    ],
    "chili": [
        ("cornbread", "sweet crumb soaks chili — diner classic"),
        ("cheddar biscuits", "buttery side for hearty bowls"),
        ("simple green salad", "fresh crunch between spoonfuls"),
        ("tortilla chips", "scoop-and-crunch pairing"),
    ],
    "pasta": [
        ("garlic bread", "soaks sauce — crowd favorite"),
        ("simple arugula salad", "peppery greens cut richness"),
        ("caprese salad", "tomato-mozzarella brightness"),
    ],
    "burger": [
        ("coleslaw", "cool crunch against juicy patties"),
        ("sweet potato fries", "popular sweet-salty side"),
        ("onion rings", "classic diner pairing"),
    ],
    "pizza": [
        ("caesar salad", "crisp romaine balances cheese"),
        ("garlic knots", "easy shareable side"),
    ],
    "curry": [
        ("naan bread", "scoop vehicle — essential pairing"),
        ("basmati rice", "fluffy base for saucy curry"),
        ("raita", "cool yogurt cools spice"),
    ],
    "stir_fry": [
        ("cucumber salad", "cool crunch with hot wok flavors"),
        ("steamed rice", "neutral base for bold sauces"),
        ("egg drop soup", "light starter — popular pairing"),
    ],
    "soup": [
        ("crusty bread", "dunk-and-soak classic"),
        ("grilled cheese", "comfort pairing for tomato soups"),
    ],
    "salad": [
        ("garlic bread", "easy carb alongside greens"),
        ("soup cup", "warm contrast to cold salad"),
    ],
}

GENERIC_PAIRING_SIDES = [
    ("easy side salad", "light crunch accents any main"),
    ("roasted vegetables", "caramelized sweetness rounds the plate"),
    ("rice pilaf", "neutral popular base"),
    ("quick pickles", "acid accent chefs reach for"),
]


def _blob(card: dict[str, Any]) -> str:
    parts = [
        card.get("title") or "",
        card.get("summary") or "",
        " ".join(card.get("ingredient_names") or []),
        card.get("source_tag") or "",
        " ".join(card.get("source_queries") or []),
    ]
    return re.sub(r"[^a-z0-9]+", " ", " ".join(parts).lower()).strip()


def _query_words(text: str) -> list[str]:
    return [
        w for w in re.findall(r"[a-z]{3,}", text.lower())
        if w not in _STOPWORDS
    ]


def enrich_search_plan(
    plan: dict[str, Any],
    what_sounds_good: str,
    *,
    side_filters: list[str] | None = None,
) -> dict[str, Any]:
    """Add dish anchor, street-food queries, and accent pairing terms."""
    plan = dict(plan)
    anchor, family_queries = detect_dish_anchor(what_sounds_good)
    plan["dish_anchor"] = anchor
    plan["what_sounds_good"] = what_sounds_good

    for thread in plan.get("craving_threads") or []:
        terms = list(thread.get("search_terms") or [])
        if anchor and anchor in STREET_FOOD_TERMS:
            for st in STREET_FOOD_TERMS[anchor][:4]:
                if st not in terms:
                    terms.insert(0, st)
        if family_queries:
            for fq in family_queries[:6]:
                if fq not in terms:
                    terms.append(fq)
        thread["search_terms"] = terms[:10]

    street_terms: list[str] = []
    if anchor and anchor in STREET_FOOD_TERMS:
        street_terms = list(STREET_FOOD_TERMS[anchor])
    plan["street_food_terms"] = street_terms

    pairing_terms: list[str] = list(plan.get("pairing_side_terms") or [])
    pairing_cites: dict[str, str] = dict(plan.get("pairing_cites") or {})

    accent_pool = list(PAIRING_ACCENTS.get(anchor or "", [])) + list(GENERIC_PAIRING_SIDES)
    for term, cite in accent_pool:
        if term not in pairing_terms:
            pairing_terms.append(term)
        pairing_cites[term] = cite

    for sf in side_filters or []:
        if sf and sf not in pairing_terms:
            pairing_terms.insert(0, sf)
            pairing_cites[sf] = f"your chosen side — accents the main"

    plan["pairing_side_terms"] = pairing_terms[:14]
    plan["pairing_cites"] = pairing_cites
    return plan


def score_candidate(
    card: dict[str, Any],
    plan: dict[str, Any],
    *,
    what_sounds_good: str = "",
) -> float:
    blob = _blob(card)
    score = 0.0
    anchor = plan.get("dish_anchor")
    category = card.get("category") or "main"
    is_side = category in ("side", "salad", "dip")

    if anchor and not is_side:
        if matches_dish_family(card, anchor):
            score += 28.0
        for kw in dish_keywords(anchor):
            if kw in blob:
                score += 6.0

    for thread in plan.get("craving_threads") or []:
        label = (thread.get("label") or "").lower()
        if label and label in blob:
            score += 8.0
        for term in thread.get("search_terms") or []:
            tl = str(term).lower()
            if tl and tl in blob:
                score += 7.0
            for word in tl.split():
                if len(word) > 3 and word in blob:
                    score += 2.0

    for term in plan.get("street_food_terms") or []:
        if str(term).lower() in blob:
            score += 10.0

    for term in plan.get("pairing_side_terms") or []:
        if str(term).lower() in blob:
            score += 5.0 if is_side else 1.0

    protein = (plan.get("protein") or "").lower()
    if protein and mentions_protein(card, protein):
        score += 14.0

    for word in _query_words(what_sounds_good):
        if word in blob:
            score += 4.0

    if "street" in blob or "food truck" in blob:
        score += 6.0

    pop = card.get("popularity") or card.get("aggregate_likes") or 0
    try:
        score += min(float(pop) / 50.0, 15.0)
    except (TypeError, ValueError):
        pass

    if is_side and ("easy" in blob or "quick" in blob or "simple" in blob):
        score += 4.0

    # Penalize obvious mismatches when we have a strong anchor
    if anchor and not is_side and not matches_dish_family(card, anchor):
        mismatch_markers = {
            "taco": ("scramble", "pancake", "oatmeal", "smoothie", "cupcake"),
            "chili": ("pancake", "smoothie", "cupcake", "salad only"),
            "pasta": ("taco", "burrito", "sushi"),
        }
        for bad in mismatch_markers.get(anchor, ()):
            if bad in blob:
                score -= 25.0

    return score


def rank_and_filter_candidates(
    candidates: list[dict[str, Any]],
    plan: dict[str, Any],
    *,
    what_sounds_good: str = "",
    max_pool: int = 70,
    min_score: float = 10.0,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    scored: list[tuple[dict[str, Any], float]] = []
    for card in candidates:
        s = score_candidate(card, plan, what_sounds_good=what_sounds_good)
        enriched = dict(card)
        enriched["_relevance"] = s
        scored.append((enriched, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    strong = [c for c, s in scored if s >= min_score]
    pool = strong if len(strong) >= 20 else [c for c, _ in scored]

    mains = [c for c in pool if c.get("category") == "main"]
    sides = [c for c in pool if c.get("category") in ("side", "salad", "dip")]
    other = [c for c in pool if c not in mains and c not in sides]

    # Ensure sides present for curator
    ordered = mains + sides + other
    return ordered[:max_pool]


def pairing_cite_for_term(plan: dict[str, Any], term: str) -> str:
    cites = plan.get("pairing_cites") or {}
    return cites.get(term, "popular easy side — accents your main")