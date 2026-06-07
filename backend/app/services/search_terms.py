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
    """Many queries → many preparations (taco styles, chili variations, etc.)."""
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

    anchor, dish_queries = detect_dish_anchor(text)
    if not parsed.get("dish_queries") and dish_queries:
        parsed_dish = dish_queries
    else:
        parsed_dish = list(parsed.get("dish_queries") or [])

    for dq in parsed_dish:
        add(dq)

    protein = (parsed.get("protein") or "").strip()
    if protein:
        add(protein)
        for dq in parsed_dish[:6]:
            add(f"{protein} {dq}")

    if "ground beef" in lower or "groundbeef" in lower.replace(" ", ""):
        add("ground beef")
        for extra in ("tacos", "chili", "burrito", "nachos", "spicy"):
            if extra in lower or parsed_dish:
                add(f"ground beef {extra}")

    for flavor in parsed.get("flavors") or []:
        if protein:
            add(f"{protein} {flavor}")
        add(f"{flavor} {parsed_dish[0]}" if parsed_dish else flavor)

    for ing in (parsed.get("ingredients") or [])[:4]:
        if protein:
            add(f"{protein} {ing}")

    words = [w for w in re.findall(r"[a-z]{3,}", lower) if w not in _STOP]
    for w in words[:6]:
        add(w)

    if anchor == "taco":
        for prep in (
            "fish taco", "chicken taco", "beef taco", "carnitas", "al pastor",
            "street tacos", "birria tacos", "breakfast tacos",
        ):
            add(prep)
    elif anchor == "chili":
        for prep in (
            "beef chili", "turkey chili", "vegetarian chili", "white chicken chili",
            "texas chili", "slow cooker chili",
        ):
            add(prep)

    return terms[:18]