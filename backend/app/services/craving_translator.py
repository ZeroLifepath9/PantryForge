"""Translate free-form cravings into structured search criteria + AllRecipes queries."""

from __future__ import annotations

import re
from typing import Any

from app.services.craving_parser import apply_protein_filter, parse_craving
from app.services.dish_families import detect_dish_anchor

_STOP = frozenset({
    "something", "with", "and", "the", "for", "that", "good", "sounds", "like",
    "want", "some", "have", "what", "your", "side", "food", "meal", "make",
    "need", "craving", "idea", "ideas", "recipe", "recipes", "dish", "dishes",
    "way", "ways", "different", "please", "maybe", "really", "very", "tonight",
    "today", "night", "cold", "hot", "nice", "kind", "sort", "type", "anything",
    "dinner", "lunch", "breakfast", "eating", "eat", "cook", "cooking",
})

_FLAVOR_TO_INGREDIENT = {
    "cheesy": "cheese",
    "lemony": "lemon",
    "garlicky": "garlic",
    "buttery": "butter",
    "creamy": "cream",
    "smoky": "smoked",
    "tangy": "lemon",
    "zesty": "lemon",
}

_MOOD_SEARCHES: dict[str, list[str]] = {
    "comfort": ["comfort food", "hearty stew", "chicken soup", "mac and cheese", "casserole"],
    "light": ["light dinner", "healthy dinner", "grilled fish", "fresh salad"],
    "crispy": ["crispy chicken", "fried chicken", "crispy baked"],
}


def build_search_queries(parsed: dict[str, Any], what_sounds_good: str) -> list[str]:
    """Turn parsed intent into short AllRecipes queries — never the full sentence.
    For compound inputs (multiple styles like mexican + spicy + chili + tacos + gumbo),
    generate queries covering EACH idea + combinations so discovery pulls diverse candidates
    (chili recipes, taco recipes, gumbo, spicy mexican fusions, etc.)."""
    text = (what_sounds_good or "").strip()
    lower = text.lower()
    seen: set[str] = set()
    out: list[str] = []

    def add(q: str) -> None:
        q = re.sub(r"\s+", " ", q.strip())
        if len(q) < 3 or q.lower() in seen:
            return
        seen.add(q.lower())
        out.append(q)

    protein = (parsed.get("protein") or "").strip()
    dish_queries = list(parsed.get("dish_queries") or [])
    flavors = list(parsed.get("flavors") or [])
    ingredients = list(parsed.get("ingredients") or [])
    starches = list(parsed.get("starches") or [])
    mood = parsed.get("mood")
    cuisine = parsed.get("cuisine")
    dish_anchor = parsed.get("dish_anchor")

    for flavor in flavors:
        mapped = _FLAVOR_TO_INGREDIENT.get(flavor)
        if mapped and mapped not in ingredients:
            ingredients.append(mapped)

    # Core expansion for EVERY dish idea / style mentioned in compound input
    # (this is the key fix for "chili or tacos or gumbo" etc.)
    all_dish_ideas = list(dish_queries)
    if dish_anchor and dish_anchor not in [d.lower() for d in all_dish_ideas]:
        all_dish_ideas.append(dish_anchor)
    # Pull rich list from parser (Grok now instructed to output many for compounds)
    for t in (parsed.get("search_terms") or []):
        if t and t not in [d.lower() for d in all_dish_ideas]:
            all_dish_ideas.append(t)

    for idea in all_dish_ideas[:10]:
        add(idea)
        if protein:
            add(f"{protein} {idea}")
        for flavor in flavors[:3]:
            add(f"{flavor} {idea}")
        if cuisine:
            add(f"{cuisine} {idea}")

    # If no strong dish ideas extracted, fall back to traditional branches
    if not all_dish_ideas:
        if protein:
            add(protein)
            add(f"easy {protein}")
            add(f"baked {protein}")
            for flavor in flavors[:3]:
                add(f"{flavor} {protein}")
            for ing in ingredients[:3]:
                add(f"{protein} {ing}")
            for starch in starches[:2]:
                add(f"{protein} {starch}")
            if mood:
                for q in _MOOD_SEARCHES.get(mood, [])[:2]:
                    if protein in q or "chicken" in q or mood == "comfort":
                        add(q.replace("chicken", protein) if "chicken" in q else f"{mood} {protein}")
        elif flavors or ingredients:
            if flavors and ingredients:
                f0, i0 = flavors[0], ingredients[0]
                if f0.replace("y", "") not in i0 and i0 not in f0:
                    add(f"{f0} {i0}")
            for flavor in flavors[:3]:
                add(f"{flavor} recipe")
                if mood:
                    add(f"{mood} {flavor}")
            for ing in ingredients[:4]:
                add(ing)
                add(f"{ing} recipe")
            if "cheese" in ingredients or "cheesy" in flavors:
                add("cheese")
                add("mac and cheese")
                add("cheesy pasta")
                add("baked pasta")
                add("casserole")
            if mood == "comfort":
                for q in ("bake", "casserole", "soup", "stew", "pasta"):
                    add(q)
            elif mood:
                for q in _MOOD_SEARCHES.get(mood, [])[:4]:
                    add(q)
        elif mood:
            for q in _MOOD_SEARCHES.get(mood, []):
                add(q)
        elif starches:
            for s in starches[:3]:
                add(s)
                add(f"easy {s}")

    # Cuisine + flavor + explicit combinations for "things that combine them all"
    if cuisine:
        add(cuisine)
        for flavor in flavors[:2]:
            add(f"{flavor} {cuisine}")
        if any(f in ("spicy", "hot") for f in flavors) or "spicy" in lower:
            add(f"spicy {cuisine}")
            add(f"mexican spicy" if cuisine == "mexican" else f"{cuisine} spicy")
    for flavor in flavors[:3]:
        add(flavor)
        if cuisine:
            add(f"{cuisine} {flavor}")

    # From parser's search_terms (now rich for compounds thanks to updated prompt)
    for term in (parsed.get("search_terms") or [])[:12]:
        add(term)

    # Main query and raw keywords from original
    mq = (parsed.get("main_query") or "").strip()
    if mq and len(mq.split()) <= 4 and mq.lower() != text.lower():
        add(mq)

    words = [w for w in re.findall(r"[a-z]{4,}", lower) if w not in _STOP]
    for w in words[:8]:
        add(w)

    # Fusion/combo queries for the "or" list of ideas
    if len(all_dish_ideas) >= 2:
        # e.g. "chili tacos gumbo", "mexican spicy chili"
        combo = " ".join([i for i in all_dish_ideas[:3] if i])
        if combo:
            add(combo)
        if cuisine and flavors:
            add(f"{cuisine} {' '.join(flavors[:2])}")

    # Final dedup + limit (higher to support 15-25 results)
    deduped = []
    for q in out:
        if q.lower() not in {d.lower() for d in deduped}:
            deduped.append(q)
    return deduped[:18]


def build_match_keywords(parsed: dict[str, Any], what_sounds_good: str) -> list[str]:
    """Keywords for relevance — the forest, not every word in the sentence."""
    seen: set[str] = set()
    out: list[str] = []

    def add(term: str) -> None:
        t = term.strip().lower()
        if len(t) >= 3 and t not in seen and t not in _STOP:
            seen.add(t)
            out.append(t)

    for field in ("protein", "dish_anchor", "cuisine", "mood", "main_query"):
        val = parsed.get(field)
        if val:
            add(str(val))
            if field == "dish_anchor":
                add(str(val).replace("_", " "))

    for key in ("dish_queries", "flavors", "ingredients", "starches", "search_queries"):
        for item in parsed.get(key) or []:
            for word in re.findall(r"[a-z]{3,}", str(item).lower()):
                if word not in _STOP:
                    add(word)

    mood = parsed.get("mood")
    if mood == "comfort":
        for w in ("comfort", "hearty", "warm", "cozy", "stew", "soup", "casserole", "mac"):
            add(w)
    elif mood == "light":
        for w in ("light", "fresh", "healthy", "grilled", "salad", "lemon"):
            add(w)
    elif mood == "crispy":
        for w in ("crispy", "crunchy", "fried", "baked"):
            add(w)

    for flavor in parsed.get("flavors") or []:
        mapped = _FLAVOR_TO_INGREDIENT.get(flavor)
        if mapped:
            add(mapped)

    for w in re.findall(r"[a-z]{4,}", what_sounds_good.lower()):
        if w not in _STOP:
            add(w)

    return sorted(out, key=len, reverse=True)


def _chef_headline(parsed: dict[str, Any], text: str) -> str:
    bits: list[str] = []
    if parsed.get("protein"):
        bits.append(parsed["protein"])
    if parsed.get("dish_anchor"):
        bits.append(parsed["dish_anchor"].replace("_", " "))
    for f in (parsed.get("flavors") or [])[:2]:
        bits.append(f)
    if parsed.get("mood"):
        bits.append(parsed["mood"])
    if bits:
        return f"Searching for {' + '.join(bits)} mains"
    return f"Finding recipes for «{text[:50]}»"


def _chef_intro(parsed: dict[str, Any], text: str) -> str:
    queries = parsed.get("search_queries") or []
    sample = ", ".join(queries[:4])
    mode = parsed.get("search_mode") or "general"
    if mode == "protein" and parsed.get("protein"):
        return (
            f"You said «{text[:80]}» — I translated that into popular {parsed['protein']} "
            f"searches like {sample}. Pick favorites and I'll build your cook kit."
        )
    if mode == "dish":
        return (
            f"«{text[:80]}» maps to focused dish searches ({sample}). "
            "These are real AllRecipes mains matched to your craving."
        )
    return (
        f"I read «{text[:80]}» and broke it into targeted searches — {sample}. "
        "Pick up to five and I'll refine from there."
    )


async def translate_craving(
    what_sounds_good: str,
    *,
    protein_filter: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Parse natural language → structured intent + AllRecipes queries."""
    text = what_sounds_good.strip()
    parsed, is_mock = await parse_craving(text)
    if protein_filter:
        parsed = apply_protein_filter(parsed, protein_filter)

    queries = build_search_queries(parsed, text)
    keywords = build_match_keywords(parsed, text)

    plan: dict[str, Any] = {
        **parsed,
        "search_queries": queries,
        "search_terms": queries,
        "match_keywords": keywords,
        "chef_headline": _chef_headline(parsed, text),
        "chef_intro": _chef_intro(parsed, text),
        "what_sounds_good": text,
        "craving_threads": [{
            "label": (parsed.get("main_query") or text[:40]).title(),
            "search_terms": queries,
            "chef_note": "Translated from your craving into recipe searches.",
        }],
    }

    anchor = parsed.get("dish_anchor")
    plan["user_dish_anchor"] = bool(anchor)
    plan["dish_anchor"] = anchor

    return plan, is_mock