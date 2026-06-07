"""Score and rank Spoonacular candidates against the chef plan and craving."""

from __future__ import annotations

import re
from typing import Any

from app.services.dish_families import (
    cuisine_for_anchor,
    detect_dish_anchor,
    dish_keywords,
    family_adjacent_queries,
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


def _matches_cuisine(
    card: dict[str, Any],
    cuisine_filters: list[str],
    *,
    dish_anchor: str | None = None,
) -> bool:
    if not cuisine_filters:
        return True
    card_cuisines = [c.lower() for c in (card.get("cuisines") or [])]
    source_cuisine = (card.get("source_cuisine") or "").lower()
    blob = _blob(card)
    anchor_cuisine = cuisine_for_anchor(dish_anchor)
    filters = [c.lower() for c in cuisine_filters]
    if anchor_cuisine and anchor_cuisine in filters and matches_dish_family(card, dish_anchor):
        return True
    for cuisine in filters:
        if source_cuisine and (source_cuisine == cuisine or cuisine in source_cuisine):
            return True
        if cuisine in card_cuisines:
            return True
        if cuisine in blob:
            return True
        if cuisine.replace(" ", "-") in blob or cuisine.replace(" ", "") in blob:
            return True
    return False


def enrich_search_plan(
    plan: dict[str, Any],
    what_sounds_good: str,
    *,
    side_filters: list[str] | None = None,
    cuisine_filters: list[str] | None = None,
) -> dict[str, Any]:
    """Add dish anchor, family adjacents, street-food queries, and pairing terms."""
    plan = dict(plan)
    anchor, family_queries = detect_dish_anchor(what_sounds_good)
    plan["dish_anchor"] = anchor
    plan["what_sounds_good"] = what_sounds_good
    plan["cuisine_filters"] = [c.strip().lower() for c in (cuisine_filters or []) if c]

    adjacent = family_adjacent_queries(anchor)
    plan["family_adjacent_queries"] = adjacent

    for thread in plan.get("craving_threads") or []:
        terms = list(thread.get("search_terms") or [])
        if anchor and anchor in STREET_FOOD_TERMS:
            for st in STREET_FOOD_TERMS[anchor][:4]:
                if st not in terms:
                    terms.insert(0, st)
        for fq in (family_queries or []) + adjacent:
            if fq not in terms:
                terms.append(fq)
        thread["search_terms"] = terms[:14]

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


def collect_match_terms(plan: dict[str, Any], what_sounds_good: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(term: str) -> None:
        t = term.strip().lower()
        if len(t) >= 3 and t not in seen:
            seen.add(t)
            out.append(t)

    for w in _query_words(what_sounds_good):
        add(w)
    for thread in plan.get("craving_threads") or []:
        for term in thread.get("search_terms") or []:
            add(str(term))
    for term in plan.get("street_food_terms") or []:
        add(str(term))
    for term in plan.get("family_adjacent_queries") or []:
        add(str(term))
    anchor = plan.get("dish_anchor")
    if anchor:
        for kw in dish_keywords(anchor):
            add(kw)
    return sorted(out, key=len, reverse=True)


def is_relevant_main(
    card: dict[str, Any],
    plan: dict[str, Any],
    *,
    what_sounds_good: str = "",
) -> tuple[bool, str]:
    """Strict gate: title/phrase/family match + active filters. No filler."""
    if card.get("category") in ("side", "salad", "dip"):
        return False, ""

    title = (card.get("title") or "").lower()
    anchor = plan.get("dish_anchor")
    cuisine_filters = plan.get("cuisine_filters") or []

    if cuisine_filters and not _matches_cuisine(card, cuisine_filters, dish_anchor=anchor):
        return False, ""

    protein = (plan.get("protein") or "").strip().lower()
    if protein:
        if protein == "vegetarian":
            diets_set = {d.lower() for d in (card.get("diets") or [])}
            veg_markers = ("vegetarian", "vegan", "tofu", "bean", "lentil", "meatless")
            if "vegetarian" not in diets_set and "vegan" not in diets_set:
                if not any(m in title for m in veg_markers):
                    return False, ""
        elif not mentions_protein(card, protein):
            return False, ""

    terms = collect_match_terms(plan, what_sounds_good)

    if anchor:
        if matches_dish_family(card, anchor):
            for term in terms:
                if term in title:
                    return True, term
            return True, anchor.replace("_", " ")
        for term in terms:
            if term in title and any(kw in term for kw in dish_keywords(anchor)):
                return True, term
        return False, ""

    for term in terms:
        if term in title:
            return True, term

    for w in _query_words(what_sounds_good):
        if len(w) >= 4 and w in title:
            return True, w

    return False, ""


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

    cuisine_filters = plan.get("cuisine_filters") or []
    anchor = plan.get("dish_anchor")
    if cuisine_filters:
        if _matches_cuisine(card, cuisine_filters, dish_anchor=anchor):
            score += 16.0
        else:
            score -= 20.0

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
    max_pool: int = 12,
    min_score: float = 12.0,
    mains_only: bool = False,
    strict: bool = True,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    if mains_only:
        candidates = [c for c in candidates if c.get("category") not in ("side", "salad", "dip")]

    scored: list[tuple[dict[str, Any], float]] = []
    for card in candidates:
        if strict:
            ok, match_term = is_relevant_main(card, plan, what_sounds_good=what_sounds_good)
            if not ok:
                continue
        else:
            match_term = ""

        s = score_candidate(card, plan, what_sounds_good=what_sounds_good)
        if s < min_score:
            continue
        enriched = dict(card)
        enriched["_relevance"] = s
        if match_term:
            enriched["_match_term"] = match_term
        scored.append((enriched, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored[:max_pool]]


def pairing_cite_for_term(plan: dict[str, Any], term: str) -> str:
    cites = plan.get("pairing_cites") or {}
    return cites.get(term, "popular easy side — accents your main")