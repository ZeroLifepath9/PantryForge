"""Diet- and health-aware accent side for a selected main."""

from __future__ import annotations

from typing import Any

from app.services.chef_relevance import GENERIC_PAIRING_SIDES, PAIRING_ACCENTS, pairing_cite_for_term

# keys map to recipe templates in recipe_elevation.ELEVATION_COMPANIONS
SIDE_TEMPLATE_KEYS: dict[str, list[str]] = {
    "taco": ["pico", "pickled_onions", "salsa_verde"],
    "pasta": ["pepper_arugula", "garlic_bread"],
    "burger": ["special_sauce", "caramelized_onions"],
    "curry": ["raita", "quick_chutney"],
    "stir_fry": ["cucumber_salad", "ginger_scallion"],
    "pizza": ["chili_honey"],
    "chili": ["cornbread"],
    "soup": ["herb_oil"],
}

SIDE_DIET_PROFILE: dict[str, dict[str, Any]] = {
    "pico": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ("diabetes", "low-sodium", "anti-inflammatory")},
    "pickled_onions": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ("diabetes", "anti-inflammatory")},
    "salsa_verde": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ("diabetes", "anti-inflammatory")},
    "pepper_arugula": {"diets": ("vegetarian", "gluten-free"), "health": ("cardiac", "low-cholesterol", "anti-inflammatory")},
    "garlic_bread": {"diets": ("vegetarian",), "health": ()},
    "special_sauce": {"diets": (), "health": ()},
    "caramelized_onions": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ("diabetes",)},
    "raita": {"diets": ("vegetarian", "gluten-free"), "health": ("gerd",)},
    "quick_chutney": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ("diabetes",)},
    "cucumber_salad": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ("diabetes", "low-sodium", "renal", "anti-inflammatory")},
    "ginger_scallion": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ()},
    "chili_honey": {"diets": ("vegetarian", "gluten-free"), "health": ()},
    "cornbread": {"diets": ("vegetarian",), "health": ()},
    "herb_oil": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ("anti-inflammatory",)},
    "quick_pickles": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ("diabetes", "low-sodium")},
    "herb_salad": {"diets": ("vegetarian", "vegan", "gluten-free", "dairy-free"), "health": ("cardiac", "low-cholesterol", "diabetes", "anti-inflammatory")},
}

INTOLERANCE_CONFLICTS: dict[str, tuple[str, ...]] = {
    "dairy": ("cheese", "butter", "cream", "yogurt", "sour cream", "milk"),
    "gluten": ("bread", "baguette", "flour", "cornbread"),
    "egg": ("egg",),
    "soy": ("soy",),
}


def _side_passes_diets(key: str, diets: list[str]) -> bool:
    if not diets:
        return True
    profile = SIDE_DIET_PROFILE.get(key, {})
    allowed = set(profile.get("diets") or ())
    if not allowed:
        return True
    return all(d in allowed for d in diets)


def _side_passes_health(key: str, health_conditions: list[str]) -> bool:
    if not health_conditions:
        return True
    profile = SIDE_DIET_PROFILE.get(key, {})
    friendly = set(profile.get("health") or ())
    if not friendly:
        return True
    return any(h in friendly for h in health_conditions)


def _side_passes_intolerances(key: str, intolerances: list[str], template: dict[str, Any]) -> bool:
    if not intolerances:
        return True
    blob = " ".join(template.get("ingredients") or []).lower()
    for intolerance in intolerances:
        for marker in INTOLERANCE_CONFLICTS.get(intolerance, (intolerance,)):
            if marker in blob:
                return False
    return True


def _lookup_template(key: str) -> dict[str, Any] | None:
    from app.services.recipe_elevation import ELEVATION_COMPANIONS

    for pool in ELEVATION_COMPANIONS.values():
        for t in pool:
            if t.get("key") == key:
                return t
    if key == "quick_pickles":
        return {
            "key": "quick_pickles",
            "title": "5-Minute Quick Pickles",
            "why": "Acid crunch elevates almost any main.",
            "ingredients": ["Cucumber or onion, thinly sliced", "Vinegar", "Sugar", "Salt"],
            "steps": [
                {"step": 1, "text": "Cover sliced veg with hot vinegar, sugar, and salt.", "tip": None},
                {"step": 2, "text": "Use after 10 minutes as a bright topping.", "tip": None},
            ],
        }
    if key == "herb_salad":
        return {
            "key": "herb_salad",
            "title": "Simple Herb Salad",
            "why": "Fresh herbs and lemon cut richness on any heavy main.",
            "ingredients": ["Parsley", "Cilantro or mint", "Lemon", "Olive oil", "Salt"],
            "steps": [
                {"step": 1, "text": "Chop herbs; dress with lemon, oil, and salt.", "tip": None},
                {"step": 2, "text": "Pile beside your main.", "tip": None},
            ],
        }
    if key == "cornbread":
        return {
            "key": "cornbread",
            "title": "Skillet Cornbread",
            "why": "Sweet crumb soaks chili — classic bowl pairing.",
            "ingredients": ["Cornmeal", "Flour", "Buttermilk", "Egg", "Butter", "Honey", "Salt"],
            "steps": [
                {"step": 1, "text": "Mix batter; pour into hot buttered skillet.", "tip": "Preheated pan = crisp crust."},
                {"step": 2, "text": "Bake at 400°F until golden; brush with honey butter.", "tip": None},
            ],
        }
    return None


def _term_to_key(term: str) -> str | None:
    lower = term.lower()
    mapping = {
        "pico": "pico",
        "pico de gallo": "pico",
        "pickled onions": "pickled_onions",
        "salsa verde": "salsa_verde",
        "guacamole": "pico",
        "elote": "pico",
        "coleslaw": "cucumber_salad",
        "garlic bread": "garlic_bread",
        "arugula": "pepper_arugula",
        "salad": "herb_salad",
        "raita": "raita",
        "naan": "raita",
        "rice": "raita",
        "cornbread": "cornbread",
        "quick pickles": "quick_pickles",
        "easy side salad": "herb_salad",
        "roasted vegetables": "herb_salad",
    }
    for phrase, key in sorted(mapping.items(), key=lambda x: -len(x[0])):
        if phrase in lower:
            return key
    return None


async def pick_accent_side_from_allrecipes(
    *,
    dish_anchor: str | None,
    main_title: str = "",
    side_filters: list[str] | None = None,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Try to pull a real accent side recipe from AllRecipes."""
    from app.services.allrecipes_scraper import fetch_recipe_page, search_allrecipes

    plan = plan or {}
    side_filters = side_filters or []
    search_terms: list[str] = []
    if side_filters:
        search_terms.extend(side_filters[:2])
    pool = list(PAIRING_ACCENTS.get(dish_anchor or "", [])) + list(GENERIC_PAIRING_SIDES)
    for term, _ in pool[:3]:
        search_terms.append(term)
    if dish_anchor == "taco":
        search_terms.extend(["pico de gallo", "mexican street corn"])

    for query in search_terms[:4]:
        hits = await search_allrecipes(query, limit=5)
        for hit in hits:
            title = (hit.get("title") or "").lower()
            if any(skip in title for skip in ("sauce only", "taco bell", "copycat")):
                continue
            if "salad" in title or "pico" in title or "slaw" in title or "rice" in title or "corn" in title or "beans" in title:
                card = await fetch_recipe_page(hit["url"])
                if not card:
                    continue
                key = _term_to_key(query) or "accent"
                if not _side_passes_diets(key, diets or []):
                    continue
                if not _side_passes_intolerances(key, intolerances or [], card):
                    continue
                cite = pairing_cite_for_term(plan, card.get("title", ""))
                return {
                    "key": key,
                    "title": card.get("title"),
                    "why": cite,
                    "pairs_because": cite,
                    "diet_note": _diet_note(diets, health_conditions),
                    "ingredients": [i["name"] if isinstance(i, dict) else i for i in (card.get("ingredients") or [])],
                    "steps": [
                        {"step": i + 1, "text": t, "tip": None}
                        for i, t in enumerate(card.get("instructions") or [])
                    ],
                    "source_url": card.get("source_url"),
                }
    return None


def _diet_note(diets: list[str] | None, health: list[str] | None) -> str | None:
    bits = []
    if diets:
        bits.append(f"fits {', '.join(diets)}")
    if health:
        bits.append(f"works for {', '.join(health)}")
    return "; ".join(bits) if bits else None


def pick_accent_side(
    *,
    dish_anchor: str | None,
    side_filters: list[str] | None = None,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []
    side_filters = side_filters or []
    plan = plan or {}

    candidate_keys: list[str] = []
    for sf in side_filters:
        k = _term_to_key(sf)
        if k:
            candidate_keys.append(k)
    for key in SIDE_TEMPLATE_KEYS.get(dish_anchor or "", []):
        if key not in candidate_keys:
            candidate_keys.append(key)
    for term, _ in PAIRING_ACCENTS.get(dish_anchor or "", [])[:4]:
        k = _term_to_key(term)
        if k and k not in candidate_keys:
            candidate_keys.append(k)
    for term, _ in GENERIC_PAIRING_SIDES:
        k = _term_to_key(term)
        if k and k not in candidate_keys:
            candidate_keys.append(k)

    for key in candidate_keys:
        if not _side_passes_diets(key, diets):
            continue
        if not _side_passes_health(key, health_conditions):
            continue
        template = _lookup_template(key)
        if not template:
            continue
        if not _side_passes_intolerances(key, intolerances, template):
            continue
        cite = pairing_cite_for_term(plan, template["title"])
        diet_note = None
        if diets or health_conditions:
            bits = []
            if diets:
                bits.append(f"fits {', '.join(diets)}")
            if health_conditions:
                bits.append(f"works for {', '.join(health_conditions)}")
            diet_note = "; ".join(bits)
        return {
            "key": template["key"],
            "title": template["title"],
            "why": template.get("why") or cite,
            "pairs_because": cite,
            "diet_note": diet_note,
            "ingredients": template.get("ingredients") or [],
            "steps": template.get("steps") or [],
        }
    return None