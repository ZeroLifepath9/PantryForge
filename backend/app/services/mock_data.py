"""Mock recipes and search logic — no Spoonacular API calls."""

from __future__ import annotations

import re
from typing import Any

DIET_OPTIONS = [
    {"value": "vegetarian", "label": "Vegetarian"},
    {"value": "vegan", "label": "Vegan"},
    {"value": "gluten-free", "label": "Gluten free"},
    {"value": "dairy-free", "label": "Dairy free"},
    {"value": "ketogenic", "label": "Keto"},
    {"value": "paleo", "label": "Paleo"},
    {"value": "pescetarian", "label": "Pescetarian"},
]

INTOLERANCE_OPTIONS = [
    {"value": "dairy", "label": "Dairy"},
    {"value": "egg", "label": "Egg"},
    {"value": "gluten", "label": "Gluten"},
    {"value": "grain", "label": "Grain"},
    {"value": "peanut", "label": "Peanut"},
    {"value": "seafood", "label": "Seafood"},
    {"value": "sesame", "label": "Sesame"},
    {"value": "shellfish", "label": "Shellfish"},
    {"value": "soy", "label": "Soy"},
    {"value": "tree-nut", "label": "Tree nut"},
    {"value": "wheat", "label": "Wheat"},
]

HEALTH_CONDITION_OPTIONS = [
    {"value": "cardiac", "label": "Heart-healthy / cardiac"},
    {"value": "diabetes", "label": "Diabetes-friendly"},
    {"value": "low-sodium", "label": "Low sodium"},
    {"value": "low-cholesterol", "label": "Low cholesterol"},
    {"value": "renal", "label": "Kidney-friendly / renal"},
    {"value": "gerd", "label": "Acid reflux / GERD"},
    {"value": "anti-inflammatory", "label": "Anti-inflammatory"},
]

MOCK_RECIPES: list[dict[str, Any]] = [
    {
        "id": 1001,
        "title": "Basil Tomato Egg Scramble",
        "image": "https://images.unsplash.com/photo-1525351484163-7529414344d8?w=400",
        "summary": "A quick skillet scramble using eggs, fresh tomato, and basil.",
        "ready_in_minutes": 15,
        "servings": 2,
        "diets": ["vegetarian", "gluten-free"],
        "intolerance_conflicts": ["dairy", "egg"],
        "health_friendly": ["diabetes", "gerd", "anti-inflammatory"],
        "required": ["egg", "tomato", "basil", "butter", "salt", "pepper"],
        "source_url": "https://example.com/basil-tomato-egg-scramble",
        "video_url": "https://www.youtube.com/watch?v=mock-scramble",
        "instructions": [
            "Beat eggs in a bowl with a pinch of salt and pepper.",
            "Warm butter in a nonstick pan over medium heat.",
            "Add diced tomato and cook 2 minutes until softened.",
            "Pour in eggs and stir gently until just set.",
            "Fold in torn basil leaves and serve warm.",
        ],
    },
    {
        "id": 1002,
        "title": "Cheddar Basil Omelette",
        "image": "https://images.unsplash.com/photo-1510693209232-c4c4837e9917?w=400",
        "summary": "Fluffy omelette with melted cheddar and fresh basil.",
        "ready_in_minutes": 12,
        "servings": 1,
        "diets": ["vegetarian", "gluten-free"],
        "intolerance_conflicts": ["dairy", "egg"],
        "health_friendly": ["gerd"],
        "required": ["egg", "cheese", "basil", "butter", "salt"],
        "source_url": "https://example.com/cheddar-basil-omelette",
        "video_url": None,
        "instructions": [
            "Whisk eggs with a pinch of salt.",
            "Melt butter in a pan over medium-low heat.",
            "Pour eggs and let set briefly, then lift edges to let raw egg flow under.",
            "Add grated cheese and basil, fold in half, finish 1 minute.",
        ],
    },
    {
        "id": 1003,
        "title": "Simple Tomato Pasta",
        "image": "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=400",
        "summary": "Weeknight pasta with tomato, garlic, and olive oil.",
        "ready_in_minutes": 25,
        "servings": 3,
        "diets": ["vegetarian", "vegan"],
        "intolerance_conflicts": ["gluten", "wheat", "grain"],
        "health_friendly": [
            "cardiac", "diabetes", "low-cholesterol", "renal", "gerd", "anti-inflammatory",
        ],
        "required": ["pasta", "tomato", "garlic", "olive oil", "salt", "basil"],
        "source_url": "https://example.com/simple-tomato-pasta",
        "video_url": "https://www.youtube.com/watch?v=mock-pasta",
        "instructions": [
            "Boil pasta in salted water until al dente.",
            "Sauté minced garlic in olive oil until fragrant, not brown.",
            "Add chopped tomato and simmer 8 minutes.",
            "Toss drained pasta with sauce and fresh basil.",
        ],
    },
    {
        "id": 1004,
        "title": "Cheesy Garlic Pasta",
        "image": "https://images.unsplash.com/photo-1563379926898-05f4575a2d88?w=400",
        "summary": "Comfort pasta with cheese, garlic, and butter.",
        "ready_in_minutes": 20,
        "servings": 2,
        "diets": ["vegetarian"],
        "intolerance_conflicts": ["dairy", "gluten", "wheat", "grain"],
        "health_friendly": [],
        "required": ["pasta", "cheese", "garlic", "butter", "salt", "pepper"],
        "source_url": "https://example.com/cheesy-garlic-pasta",
        "video_url": None,
        "instructions": [
            "Cook pasta until al dente; reserve 1/2 cup pasta water.",
            "Melt butter, sauté garlic 30 seconds.",
            "Add pasta, cheese, and splash of pasta water; toss until creamy.",
        ],
    },
    {
        "id": 1005,
        "title": "Mushroom Onion Stir-Fry",
        "image": "https://images.unsplash.com/photo-1512058564366-7f0d4a4a409f?w=400",
        "summary": "Savory stir-fry — needs mushrooms you don't have yet.",
        "ready_in_minutes": 18,
        "servings": 2,
        "diets": ["vegan", "dairy-free", "gluten-free"],
        "intolerance_conflicts": ["soy"],
        "health_friendly": [
            "cardiac", "diabetes", "low-cholesterol", "renal", "anti-inflammatory",
        ],
        "required": ["mushroom", "onion", "garlic", "olive oil", "soy sauce", "pepper"],
        "source_url": "https://example.com/mushroom-onion-stirfry",
        "video_url": "https://www.youtube.com/watch?v=mock-stirfry",
        "instructions": [
            "Slice mushrooms and onion.",
            "Heat oil in a hot pan; add onion, cook 3 minutes.",
            "Add mushrooms and garlic; cook until browned.",
            "Splash soy sauce and pepper; serve immediately.",
        ],
    },
]


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _matches_ingredient(required: str, available: set[str]) -> bool:
    req = _normalize(required)
    for item in available:
        if req in item or item in req:
            return True
        # egg/eggs
        if req.rstrip("s") == item.rstrip("s"):
            return True
    return False


def mock_parse_ingredients(text: str) -> list[str]:
    """Simple mock parser — splits on commas/newlines; real AI later."""
    parts = re.split(r"[,;\n]+", text.lower())
    cleaned: list[str] = []
    for part in parts:
        part = re.sub(r"^\d+\s*", "", part.strip())
        part = re.sub(
            r"\b(some|a few|old|fresh|leftover|about|roughly)\b", "", part
        ).strip()
        if part and len(part) > 1:
            cleaned.append(part)
    return cleaned or ["egg", "tomato"]


def _recipe_matches_diets(recipe: dict[str, Any], diets: list[str]) -> bool:
    if not diets:
        return True
    recipe_diets = set(recipe.get("diets", []))
    return all(d in recipe_diets for d in diets)


def _recipe_matches_intolerances(recipe: dict[str, Any], intolerances: list[str]) -> bool:
    if not intolerances:
        return True
    conflicts = set(recipe.get("intolerance_conflicts", []))
    return not conflicts.intersection(intolerances)


def _recipe_matches_health_conditions(
    recipe: dict[str, Any], health_conditions: list[str]
) -> bool:
    if not health_conditions:
        return True
    friendly = set(recipe.get("health_friendly", []))
    return all(h in friendly for h in health_conditions)


def _classify_tier(
    missed: list[str],
    pantry: set[str],
    allow_pantry: bool,
) -> tuple[str, str]:
    if not missed:
        return "exact", "You can make this now"
    pantry_misses = [m for m in missed if _normalize(m) in pantry or any(
        _normalize(m) in _normalize(p) or _normalize(p) in _normalize(m) for p in pantry
    )]
    if allow_pantry and len(missed) == len(pantry_misses):
        return "stretch", "Add a few pantry basics"
    if len(missed) <= 3:
        return "almost", "Almost — you need a little more"
    return "almost", "Close match — missing several items"


def mock_search_recipes(
    ingredients: list[str],
    *,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
    include_pantry_staples: bool = True,
    pantry_staples: list[str] | None = None,
) -> dict[str, Any]:
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []
    user_set = {_normalize(i) for i in ingredients}
    pantry = {_normalize(p) for p in (pantry_staples or [])}
    default_pantry = {
        "pasta", "spaghetti", "olive oil", "vegetable oil", "cheese", "parmesan",
        "salt", "pepper", "garlic", "onion", "butter",
    }
    effective = set(user_set)
    if include_pantry_staples:
        effective |= pantry | default_pantry

    results: list[dict[str, Any]] = []
    for recipe in MOCK_RECIPES:
        if not _recipe_matches_diets(recipe, diets):
            continue
        if not _recipe_matches_intolerances(recipe, intolerances):
            continue
        if not _recipe_matches_health_conditions(recipe, health_conditions):
            continue

        required = recipe["required"]
        used: list[dict[str, str]] = []
        missed: list[dict[str, str]] = []
        unused = set(user_set)

        for req in required:
            if _matches_ingredient(req, effective):
                used.append({"name": req, "amount": None})
                for u in list(unused):
                    if _matches_ingredient(req, {u}):
                        unused.discard(u)
            elif _matches_ingredient(req, user_set):
                used.append({"name": req, "amount": None})
            else:
                missed.append({"name": req, "amount": None})

        missed_names = [m["name"] for m in missed]
        tier, label = _classify_tier(missed_names, effective, include_pantry_staples)

        # Skip recipes that need too many non-pantry items unless almost/stretch
        non_pantry_misses = [
            m for m in missed_names
            if not _matches_ingredient(m, default_pantry | pantry)
        ]
        if len(non_pantry_misses) > 2 and tier == "almost":
            continue

        results.append({
            "id": recipe["id"],
            "title": recipe["title"],
            "image": recipe.get("image"),
            "match_tier": tier,
            "match_label": label,
            "used_ingredients": used,
            "missed_ingredients": missed,
            "unused_ingredients": [{"name": u, "amount": None} for u in sorted(unused)],
            "diets": recipe.get("diets", []),
            "ready_in_minutes": recipe.get("ready_in_minutes"),
            "servings": recipe.get("servings"),
            "source_url": recipe.get("source_url"),
            "video_url": recipe.get("video_url"),
            "summary": recipe.get("summary"),
        })

    tier_order = {"exact": 0, "stretch": 1, "almost": 2}
    results.sort(key=lambda r: tier_order.get(r["match_tier"], 9))

    message = None
    if not results:
        message = (
            "No strong matches yet. Try adding pantry staples like pasta, oil, or cheese, "
            "or broaden your diet filters."
        )
    elif not any(r["match_tier"] == "exact" for r in results):
        message = (
            "Nothing exact with only what you listed — here are the closest options "
            "and what you'd still need."
        )

    return {
        "query_ingredients": ingredients,
        "effective_ingredients": sorted(effective),
        "results": results,
        "message": message,
    }


def mock_recipe_detail(recipe_id: int) -> dict[str, Any] | None:
    for recipe in MOCK_RECIPES:
        if recipe["id"] == recipe_id:
            return {
                "id": recipe["id"],
                "title": recipe["title"],
                "image": recipe.get("image"),
                "summary": recipe.get("summary"),
                "ready_in_minutes": recipe.get("ready_in_minutes"),
                "servings": recipe.get("servings"),
                "source_url": recipe.get("source_url"),
                "video_url": recipe.get("video_url"),
                "ingredients": [
                    {"name": r, "amount": None} for r in recipe["required"]
                ],
                "instructions": recipe["instructions"],
                "diets": recipe.get("diets", []),
            }
    return None


def mock_simplify_steps(
    recipe_id: int,
    *,
    explain_techniques: bool = True,
    skill_level: str = "beginner",
) -> dict[str, Any] | None:
    detail = mock_recipe_detail(recipe_id)
    if not detail:
        return None

    direct = skill_level == "direct" or not explain_techniques
    steps: list[dict[str, Any]] = []
    for i, instruction in enumerate(detail["instructions"], start=1):
        tip = None
        if not direct:
            if "sauté" in instruction.lower() or "sauté" in instruction.lower():
                tip = "Sauté means cook in a little hot fat, stirring, over medium heat."
            elif "al dente" in instruction.lower():
                tip = "Al dente means firm to the bite — not mushy."
            elif "whisk" in instruction.lower():
                tip = "Whisk means beat quickly with a fork until smooth and slightly frothy."
        steps.append({"step": i, "text": instruction, "tip": tip})

    mode = "direct" if direct else "beginner"
    return {
        "recipe_id": recipe_id,
        "title": detail["title"],
        "mode": mode,
        "steps": steps,
    }