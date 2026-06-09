"""Derive broad Spoonacular search terms from a craving."""

from __future__ import annotations

import re
from typing import Any

from app.services.dish_families import detect_dish_anchor

_STOP = frozenset({
    "something", "with", "and", "the", "for", "that", "good", "sounds", "like",
    "want", "some", "have", "what", "your", "side", "food", "meal", "make",
    "need", "craving", "idea", "ideas", "recipe", "recipes", "dish", "dishes",
    "way", "ways", "different", "please", "maybe", "really", "very",
})


def collect_search_terms(parsed: dict[str, Any], what_sounds_good: str) -> list[str]:
    """Many queries → many preparations for compound cravings.
    For inputs like 'mexican. spicy like chili or tacos or gumbo', produce terms
    for each idea + combinations so we can surface chili, tacos, gumbo, and fusions."""
    text = (what_sounds_good or "").strip()
    lower = text.lower()
    terms: list[str] = []

    def add(term: str) -> None:
        t = term.strip()
        if not t or len(t) < 2:
            return
        if t.lower() not in {x.lower() for x in terms}:
            terms.append(t)

    add(text)
    add(parsed.get("main_query") or "")

    # Support multiple dish ideas from parser (compound fix)
    parsed_dish = list(parsed.get("dish_queries") or [])
    anchor, _ = detect_dish_anchor(text)
    if anchor and anchor not in [d.lower() for d in parsed_dish]:
        parsed_dish.append(anchor)

    for dq in parsed_dish[:8]:
        add(dq)

    protein = (parsed.get("protein") or "").strip()
    if protein:
        add(protein)
        for dq in parsed_dish[:6]:
            add(f"{protein} {dq}")

    if "ground beef" in lower or "groundbeef" in lower.replace(" ", ""):
        add("ground beef")
        for extra in ("tacos", "chili", "burrito", "nachos", "spicy", "gumbo"):
            if extra in lower or parsed_dish:
                add(f"ground beef {extra}")

    for flavor in parsed.get("flavors") or []:
        if protein:
            add(f"{protein} {flavor}")
        for dq in parsed_dish[:3]:
            add(f"{flavor} {dq}")
        add(flavor)

    for ing in (parsed.get("ingredients") or [])[:4]:
        if protein:
            add(f"{protein} {ing}")

    words = [w for w in re.findall(r"[a-z]{3,}", lower) if w not in _STOP]
    for w in words[:8]:
        add(w)

    # Explicit expansion for common compound anchors mentioned
    if any(x in lower for x in ("taco", "tacos")) or "taco" in [d.lower() for d in parsed_dish]:
        for prep in ("taco", "tacos", "fish taco", "chicken taco", "beef taco", "spicy taco", "mexican taco"):
            add(prep)
    if any(x in lower for x in ("chili", "chilli")) or "chili" in [d.lower() for d in parsed_dish]:
        for prep in ("chili", "beef chili", "turkey chili", "white chicken chili", "vegetarian chili", "spicy chili", "texas chili"):
            add(prep)
    if "gumbo" in lower or "gumbo" in [d.lower() for d in parsed_dish]:
        for prep in ("gumbo", "chicken gumbo", "shrimp gumbo", "spicy gumbo", "cajun gumbo"):
            add(prep)
    if "mexican" in lower or parsed.get("cuisine") == "mexican":
        for prep in ("mexican", "mexican spicy", "mexican chili", "mexican stew", "spicy mexican"):
            add(prep)

    # Add combinations for "things that combine them all"
    if len(parsed_dish) >= 2:
        for i in range(min(3, len(parsed_dish))):
            for j in range(i+1, min(4, len(parsed_dish))):
                add(f"{parsed_dish[i]} {parsed_dish[j]}")

    return terms[:20]