"""Dish-family anchors and adjacent search terms (tacos → burritos, fajitas, etc.)."""

from __future__ import annotations

import re
from typing import Any

# anchor → (regex triggers, spoonacular search queries, title keywords for matching)
DISH_FAMILIES: dict[str, dict[str, Any]] = {
    "taco": {
        "triggers": (r"\btacos?\b", r"\btaco\s*night\b"),
        "queries": ["taco", "burrito", "fajita", "quesadilla", "enchilada", "taquito"],
        "keywords": (
            "taco", "burrito", "fajita", "quesadilla", "enchilada", "taquito", "tostada",
        ),
        "cuisine": "mexican",
    },
    "pasta": {
        "triggers": (r"\bpasta\b", r"\bspaghetti\b", r"\blinguine\b", r"\bpenne\b"),
        "queries": ["pasta", "spaghetti", "lasagna", "ravioli"],
        "keywords": ("pasta", "spaghetti", "lasagna", "ravioli", "linguine", "penne", "fettuccine"),
        "cuisine": "italian",
    },
    "pizza": {
        "triggers": (r"\bpizza\b", r"\bflatbread\b"),
        "queries": ["pizza", "calzone", "flatbread pizza"],
        "keywords": ("pizza", "calzone", "flatbread"),
        "cuisine": "italian",
    },
    "burger": {
        "triggers": (r"\bburgers?\b", r"\bcheeseburger\b"),
        "queries": ["burger", "sliders", "patty melt"],
        "keywords": ("burger", "cheeseburger", "slider", "patty melt"),
        "cuisine": None,
    },
    "curry": {
        "triggers": (r"\bcurry\b", r"\bcurries\b"),
        "queries": ["curry", "tikka", "korma", "masala"],
        "keywords": ("curry", "tikka", "korma", "masala", "vindaloo"),
        "cuisine": "indian",
    },
    "stir_fry": {
        "triggers": (r"\bstir\s*fry\b", r"\bstir-fry\b"),
        "queries": ["stir fry", "fried rice", "lo mein"],
        "keywords": ("stir fry", "stir-fry", "fried rice", "lo mein"),
        "cuisine": "chinese",
    },
    "soup": {
        "triggers": (r"\bsoup\b", r"\bstew\b", r"\bchili\b"),
        "queries": ["soup", "stew", "chili", "chowder"],
        "keywords": ("soup", "stew", "chili", "chowder", "bisque"),
        "cuisine": None,
    },
    "salad": {
        "triggers": (r"\bsalad\b",),
        "queries": ["salad", "grain bowl", "buddha bowl"],
        "keywords": ("salad", "bowl"),
        "cuisine": None,
    },
}

PROTEIN_OPTIONS = [
    "chicken", "beef", "pork", "shrimp", "fish", "salmon", "tofu", "turkey", "lamb", "vegetarian",
]


def detect_dish_anchor(text: str) -> tuple[str | None, list[str]]:
    lower = text.lower()
    for anchor, spec in DISH_FAMILIES.items():
        for pattern in spec["triggers"]:
            if re.search(pattern, lower):
                return anchor, list(spec["queries"])
    return None, []


def dish_keywords(anchor: str | None) -> tuple[str, ...]:
    if not anchor or anchor not in DISH_FAMILIES:
        return ()
    return tuple(DISH_FAMILIES[anchor]["keywords"])


def matches_dish_family(card: dict[str, Any], anchor: str | None) -> bool:
    if not anchor:
        return True
    keywords = dish_keywords(anchor)
    blob = f"{card.get('title') or ''} {card.get('summary') or ''}".lower()
    return any(kw in blob for kw in keywords)


def cuisine_for_anchor(anchor: str | None) -> str | None:
    if not anchor or anchor not in DISH_FAMILIES:
        return None
    return DISH_FAMILIES[anchor].get("cuisine")