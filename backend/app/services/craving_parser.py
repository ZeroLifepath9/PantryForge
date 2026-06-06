"""Parse 'what sounds good' into search terms via xAI."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.dish_families import (
    PROTEIN_OPTIONS,
    detect_dish_anchor,
    dish_keywords,
)
from app.services.xai_client import chat_completion

PARSER_SYSTEM = """You parse what a home cook says sounds good for recipe search.

Output ONLY valid JSON:
{
  "search_mode": "dish|protein|ingredient|general",
  "dish_anchor": "taco|pasta|pizza|burger|curry|stir_fry|soup|salad|null",
  "dish_queries": ["taco", "burrito", "fajita", ...],
  "protein": "chicken|beef|...|null",
  "protein_query": "protein word only or null",
  "ingredients": ["lime", "garlic", "cilantro", ...],
  "starches": [],
  "flavors": [],
  "cuisine": "mexican|italian|null",
  "mood": "light|comfort|null",
  "main_query": "fallback 2-4 words",
  "search_terms": []
}

RULES:
1. DISH: tacos/pasta/pizza etc → search_mode=dish, dish_anchor, dish_queries WITH adjacents
   (tacos → taco, burrito, fajita, quesadilla, enchilada).
2. Extract every food ingredient mentioned (lime, tomato, garlic, rice…) into ingredients[].
   Do NOT put proteins or dish names in ingredients.
3. protein = explicit protein only; null if not stated (UI will offer a protein filter).
4. protein+ingredients without a dish → search_mode=protein or ingredient.
5. main_query = short summary of the craving.
"""

PROTEINS = (
    "chicken", "beef", "pork", "fish", "salmon", "shrimp", "tofu", "egg", "turkey",
    "lamb", "bacon", "sausage", "steak", "cod", "tuna", "crab",
)
STARCHES = (
    "noodles", "pasta", "spaghetti", "potato", "potatoes", "rice", "bread",
    "tortilla", "quinoa", "couscous", "macaroni",
)
INGREDIENT_HINTS = (
    "lime", "lemon", "garlic", "onion", "tomato", "cilantro", "basil", "cheese",
    "rice", "beans", "avocado", "pepper", "mushroom", "spinach", "broccoli",
    "corn", "potato", "cream", "butter", "honey", "ginger", "cumin", "chili",
)

MOODS = {
    "light": ("light", "fresh", "healthy", "simple"),
    "comfort": ("comfort", "cozy", "hearty", "warm"),
    "crispy": ("crispy", "crunchy", "fried"),
}


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _apply_dish_detection(parsed: dict[str, Any], original: str) -> dict[str, Any]:
    anchor, queries = detect_dish_anchor(original)
    if anchor:
        parsed["search_mode"] = "dish"
        parsed["dish_anchor"] = anchor
        parsed["dish_queries"] = queries
        if not parsed.get("cuisine"):
            from app.services.dish_families import cuisine_for_anchor
            parsed["cuisine"] = cuisine_for_anchor(anchor)
    return parsed


def _normalize_parsed(raw: dict[str, Any], original: str) -> dict[str, Any]:
    protein = raw.get("protein")
    if protein in (None, "null", ""):
        protein = None
    else:
        protein = str(protein).lower().strip()

    search_mode = str(raw.get("search_mode") or "general").lower()
    dish_anchor = raw.get("dish_anchor")
    if dish_anchor in (None, "null", ""):
        dish_anchor = None
    else:
        dish_anchor = str(dish_anchor).lower().strip()

    dish_queries = [str(q).strip() for q in (raw.get("dish_queries") or []) if q]
    ingredients = [str(i).lower().strip() for i in (raw.get("ingredients") or []) if i]

    starches = [str(s).lower().strip() for s in (raw.get("starches") or []) if s]
    flavors = [str(f).lower().strip() for f in (raw.get("flavors") or []) if f]
    search_terms = [str(t).lower().strip() for t in (raw.get("search_terms") or []) if t]

    cuisine = raw.get("cuisine")
    if cuisine in (None, "null", ""):
        cuisine = None
    else:
        cuisine = str(cuisine).lower().strip()

    mood = raw.get("mood")
    if mood in (None, "null", ""):
        mood = None
    else:
        mood = str(mood).lower().strip()

    protein_query = str(raw.get("protein_query") or protein or "").strip().lower() or None
    main_query = str(raw.get("main_query") or "").strip()
    if not main_query:
        main_query = original.strip()[:60]

    result = {
        "search_mode": search_mode,
        "dish_anchor": dish_anchor,
        "dish_queries": dish_queries,
        "protein": protein,
        "protein_query": protein_query,
        "ingredients": ingredients,
        "starches": starches,
        "flavors": flavors,
        "cuisine": cuisine,
        "mood": mood,
        "main_query": main_query,
        "pairing_queries": [],
        "search_terms": list(dict.fromkeys(search_terms)),
        "needs_protein_prompt": False,
        "protein_options": PROTEIN_OPTIONS,
    }

    result = _apply_dish_detection(result, original)
    if result["search_mode"] == "dish" or result["dish_anchor"]:
        result["search_mode"] = "dish"
        if not result["dish_queries"] and result["dish_anchor"]:
            _, result["dish_queries"] = detect_dish_anchor(original)
    elif protein:
        result["search_mode"] = "protein"
    else:
        result["search_mode"] = search_mode if search_mode in ("protein", "dish", "general") else "general"

    if not result["protein"]:
        result["needs_protein_prompt"] = True

    for ing in result["ingredients"]:
        if ing not in result["search_terms"]:
            result["search_terms"].append(ing)

    if protein and protein not in result["search_terms"]:
        result["search_terms"].insert(0, protein)

    return result


def mock_parse_craving(text: str) -> dict[str, Any]:
    lower = text.lower()
    protein = next((p for p in PROTEINS if re.search(rf"\b{re.escape(p)}\b", lower)), None)
    starches = [s for s in STARCHES if re.search(rf"\b{re.escape(s)}\b", lower)]
    flavors = [f for f in ("garlic", "lemon", "basil", "tomato", "cheese", "spicy") if f in lower]

    mood = None
    for mood_key, words in MOODS.items():
        if any(w in lower for w in words):
            mood = mood_key
            break

    cuisine = None
    for c in ("italian", "mexican", "asian", "indian", "thai", "chinese"):
        if c in lower:
            cuisine = c
            break

    dish_anchor, dish_queries = detect_dish_anchor(text)
    ingredients = [
        i for i in INGREDIENT_HINTS
        if re.search(rf"\b{re.escape(i)}\b", lower)
    ]
    ingredients += [f for f in flavors if f not in ingredients]
    ingredients = list(dict.fromkeys(ingredients))

    if dish_anchor:
        search_mode = "dish"
    elif protein and ingredients:
        search_mode = "ingredient"
    elif protein:
        search_mode = "protein"
    else:
        search_mode = "general"

    search_terms = list(dict.fromkeys(
        ([protein] if protein else [])
        + ingredients
        + starches
        + dish_queries[:3]
        + [w for w in re.findall(r"[a-z]{3,}", lower) if w not in ("something", "with", "and", "the", "want")]
    ))[:12]

    result = {
        "search_mode": search_mode,
        "dish_anchor": dish_anchor,
        "dish_queries": dish_queries,
        "protein": protein,
        "protein_query": protein,
        "ingredients": ingredients,
        "starches": starches,
        "flavors": flavors,
        "cuisine": cuisine,
        "mood": mood,
        "main_query": dish_queries[0] if dish_queries else (protein or text.strip()[:60]),
        "pairing_queries": [],
        "search_terms": search_terms,
        "needs_protein_prompt": not protein,
        "protein_options": PROTEIN_OPTIONS,
    }
    return result


async def parse_craving(text: str) -> tuple[dict[str, Any], bool]:
    text = text.strip()
    if not text:
        raise ValueError("what_sounds_good is required")

    if not settings.xai_key:
        return mock_parse_craving(text), True

    user_content = f'Parse this craving: "{text}"'
    try:
        raw_text = await chat_completion(system=PARSER_SYSTEM, user_content=user_content, temperature=0.3)
        parsed = _normalize_parsed(_extract_json(raw_text), text)
        return parsed, False
    except Exception:
        return mock_parse_craving(text), True


def apply_protein_filter(parsed: dict[str, Any], protein_filter: str | None) -> dict[str, Any]:
    """Apply an explicit UI protein choice (narrow or clear)."""
    out = dict(parsed)
    if protein_filter is None:
        out["protein"] = None
        out["protein_query"] = None
        out["vegetarian_filter"] = False
        out["needs_protein_prompt"] = True
        return out
    p = protein_filter.strip().lower()
    if p == "vegetarian":
        out["protein"] = None
        out["protein_query"] = None
        out["needs_protein_prompt"] = False
        out["vegetarian_filter"] = True
        return out
    out["protein"] = p
    out["protein_query"] = p
    out["needs_protein_prompt"] = False
    out["vegetarian_filter"] = False
    return out