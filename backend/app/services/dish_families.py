"""Dish-family anchors, adjacents, and flexible matching."""

from __future__ import annotations

import re
from typing import Any

DISH_FAMILIES: dict[str, dict[str, Any]] = {
    "taco": {
        "triggers": (r"\btacos?\b", r"\btaco\s*night\b"),
        "queries": [
            "taco", "tacos", "street taco", "fish taco", "carnitas", "carne asada",
            "burrito", "fajita", "quesadilla", "enchilada", "taquito", "tostada", "nachos",
        ],
        "keywords": (
            "taco", "tacos", "burrito", "fajita", "quesadilla", "enchilada", "taquito",
            "tostada", "nachos", "carnitas", "carne asada", "tex-mex", "tortilla",
        ),
        "cuisine": "mexican",
    },
    "chili": {
        "triggers": (r"\bchili\b", r"\bchilli\b", r"\bchile\s*con\s*carne\b"),
        "queries": [
            "chili", "chilli", "beef chili", "turkey chili", "white chicken chili",
            "vegetarian chili", "chili con carne", "spicy chili",
        ],
        "keywords": (
            "chili", "chilli", "chile con carne", "chili con carne", "chili bowl",
        ),
        "cuisine": None,
    },
    "pasta": {
        "triggers": (r"\bpasta\b", r"\bspaghetti\b", r"\blinguine\b", r"\bpenne\b"),
        "queries": ["pasta", "spaghetti", "lasagna", "ravioli", "fettuccine", "penne"],
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
        "queries": ["burger", "sliders", "patty melt", "cheeseburger"],
        "keywords": ("burger", "cheeseburger", "slider", "patty melt"),
        "cuisine": None,
    },
    "curry": {
        "triggers": (r"\bcurry\b", r"\bcurries\b"),
        "queries": ["curry", "tikka", "korma", "masala", "vindaloo"],
        "keywords": ("curry", "tikka", "korma", "masala", "vindaloo"),
        "cuisine": "indian",
    },
    "stir_fry": {
        "triggers": (r"\bstir\s*fry\b", r"\bstir-fry\b"),
        "queries": ["stir fry", "fried rice", "lo mein", "pad thai"],
        "keywords": ("stir fry", "stir-fry", "fried rice", "lo mein"),
        "cuisine": "chinese",
    },
    "soup": {
        "triggers": (r"\bsoup\b", r"\bstew\b", r"\bchowder\b"),
        "queries": ["soup", "stew", "chowder", "bisque"],
        "keywords": ("soup", "stew", "chowder", "bisque"),
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

PROTEIN_ALIASES: dict[str, tuple[str, ...]] = {
    "beef": ("beef", "ground beef", "minced beef", "steak", "brisket", "sirloin", "chuck"),
    "chicken": ("chicken", "poultry", "thigh", "breast"),
    "pork": ("pork", "bacon", "ham", "sausage", "chorizo"),
    "turkey": ("turkey",),
    "shrimp": ("shrimp", "prawn", "prawns"),
    "fish": ("fish", "cod", "tilapia", "halibut"),
    "salmon": ("salmon",),
    "lamb": ("lamb", "mutton"),
    "tofu": ("tofu", "tempeh"),
}

FLAVOR_WORDS = frozenset({
    "spicy", "hot", "mild", "smoky", "tangy", "zesty", "savory", "sweet", "creamy", "crispy",
    "crunchy", "fresh", "rich", "bold",
})


def detect_dish_anchor(text: str) -> tuple[str | None, list[str]]:
    lower = text.lower()
    # Chili before soup — soup used to steal the chili trigger
    order = ("chili", "taco", "pasta", "pizza", "burger", "curry", "stir_fry", "soup", "salad")
    for anchor in order:
        spec = DISH_FAMILIES[anchor]
        for pattern in spec["triggers"]:
            if re.search(pattern, lower):
                return anchor, list(spec["queries"])
    return None, []


def dish_keywords(anchor: str | None) -> tuple[str, ...]:
    if not anchor or anchor not in DISH_FAMILIES:
        return ()
    return tuple(DISH_FAMILIES[anchor]["keywords"])


def _card_blob(card: dict[str, Any]) -> str:
    parts = [
        card.get("title") or "",
        card.get("summary") or "",
        " ".join(card.get("ingredient_names") or []),
    ]
    return " ".join(parts).lower()


def matches_dish_family(card: dict[str, Any], anchor: str | None) -> bool:
    if not anchor:
        return True
    blob = _card_blob(card)
    return any(kw in blob for kw in dish_keywords(anchor))


def matches_source_query(card: dict[str, Any], queries: list[str]) -> bool:
    source = [q.lower() for q in (card.get("source_queries") or [])]
    if not source:
        return False
    for sq in source:
        for q in queries:
            ql = q.lower()
            if sq == ql or ql in sq or sq in ql:
                return True
    return False


def mentions_protein(card: dict[str, Any], protein: str) -> bool:
    if not protein:
        return True
    blob = _card_blob(card)
    aliases = PROTEIN_ALIASES.get(protein, (protein,))
    return any(alias in blob for alias in aliases)


def cuisine_for_anchor(anchor: str | None) -> str | None:
    if not anchor or anchor not in DISH_FAMILIES:
        return None
    return DISH_FAMILIES[anchor].get("cuisine")