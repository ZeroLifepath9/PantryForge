"""Parse 'what sounds good' into search terms via xAI."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.dish_families import (
    FLAVOR_WORDS,
    PROTEIN_OPTIONS,
    detect_dish_anchor,
)
from app.services.xai_client import chat_completion

PARSER_SYSTEM = """You translate what a home cook says into structured recipe-search criteria.
Think like a chef who hears a craving and knows what to type into AllRecipes — NOT a literal copy of their sentence.

The input may be compound: a list of ideas, styles, or examples separated by periods, commas, or "or" (e.g. "Something like mexican. Something spicy, like chili, or tacos, or gumbo.").

Output ONLY valid JSON:
{
  "search_mode": "dish|protein|ingredient|flavor|mood|general",
  "dish_anchor": "taco|chili|pasta|pizza|burger|curry|stir_fry|soup|salad|null",
  "dish_queries": ["short dish names or styles mentioned, e.g. chili, tacos, gumbo, mexican spicy stew"],
  "protein": "chicken|beef|...|null",
  "protein_query": "protein word only or null",
  "ingredients": ["lime", "garlic", "cheese", ...],
  "starches": ["rice", "pasta", ...],
  "flavors": ["spicy", "cheesy", "lemony", "crispy", ...],
  "cuisine": "mexican|italian|null",
  "mood": "light|comfort|crispy|null",
  "main_query": "2-4 word summary for search e.g. spicy mexican chili",
  "search_terms": ["chili", "tacos", "gumbo", "mexican spicy", "spicy chili", "taco gumbo", ... many short targeted queries covering ALL ideas mentioned]
}

RULES:
1. EXTRACT signals — do not echo filler words (something, want, sounds, good, tonight, cold night).
2. "cheesy" / "warm and cheesy" → flavors=[cheesy], ingredients may include cheese, mood=comfort.
3. "light lemony fish" → protein=fish, flavors=[light, lemony], ingredients=[lemon], mood=light.
4. "comfort food for a cold night" → mood=comfort, no protein unless stated — main_query=comfort food.
5. For compound inputs listing multiple styles (mexican, chili, tacos, gumbo, spicy etc.): 
   - Set cuisine if mexican/italian etc. mentioned.
   - flavors for spicy/hot etc.
   - dish_queries and especially search_terms MUST include entries for EACH mentioned idea (chili, tacos, gumbo, mexican spicy stew, spicy chili tacos, etc.) plus logical combinations.
   - dish_anchor can be the strongest single one or null; do not limit to one.
6. ingredients[] = real foods. flavors[] = taste/texture words (cheesy, crispy, smoky).
7. protein = explicit only; null if not stated.
8. main_query = the distilled overall search intent in 2-4 words.
9. search_terms: always produce a rich list (8-15 items) of short, effective AllRecipes-style queries that together cover every part of the user's list of ideas. Include direct mentions + protein/flavor/cuisine combos + fusions.
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
    "corn", "potato", "cream", "butter", "honey", "ginger", "cumin",
)
FLAVOR_HINTS = ("spicy", "hot", "smoky", "tangy", "mild", "crispy", "creamy")

MOODS = {
    "light": ("light", "fresh", "healthy", "simple", "lemony"),
    "comfort": ("comfort", "cozy", "hearty", "warm", "cheesy"),
    "crispy": ("crispy", "crunchy", "fried"),
}

_STOP = frozenset({
    "something", "with", "and", "the", "for", "that", "good", "sounds", "like",
    "want", "some", "have", "what", "your", "side", "food", "meal", "make",
    "need", "craving", "idea", "ideas", "recipe", "recipes", "dish", "dishes",
    "way", "ways", "different", "please", "maybe", "really", "very", "tonight",
    "today", "night", "cold", "nice", "kind", "sort", "type", "anything",
    "dinner", "lunch", "breakfast", "eating", "eat", "cook", "cooking",
})

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
    ingredients = [
        str(i).lower().strip() for i in (raw.get("ingredients") or [])
        if i and str(i).lower().strip() not in FLAVOR_WORDS
    ]
    flavors = [str(f).lower().strip() for f in (raw.get("flavors") or []) if f]

    starches = [str(s).lower().strip() for s in (raw.get("starches") or []) if s]
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


def _detect_protein(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"\bground\s+beef\b", lower):
        return "beef"
    return next((p for p in PROTEINS if re.search(rf"\b{re.escape(p)}\b", lower)), None)


def mock_parse_craving(text: str) -> dict[str, Any]:
    lower = text.lower()
    protein = _detect_protein(text)
    starches = [s for s in STARCHES if re.search(rf"\b{re.escape(s)}\b", lower)]

    flavors: list[str] = []
    for f in FLAVOR_HINTS:
        if re.search(rf"\b{re.escape(f)}\b", lower):
            flavors.append(f)
    if re.search(r"\bcheesy\b", lower) and "cheesy" not in flavors:
        flavors.append("cheesy")
    if re.search(r"\blemony\b", lower) and "lemony" not in flavors:
        flavors.append("lemony")

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
    dish_words = set(dish_queries) | ({dish_anchor.replace("_", " ")} if dish_anchor else set())

    ingredients = [
        i for i in INGREDIENT_HINTS
        if re.search(rf"\b{re.escape(i)}\b", lower) and i not in dish_words
    ]
    if "cheesy" in flavors and "cheese" not in ingredients:
        ingredients.append("cheese")
    if "lemony" in flavors and "lemon" not in ingredients:
        ingredients.append("lemon")
    ingredients = list(dict.fromkeys(ingredients))

    if dish_anchor:
        search_mode = "dish"
    elif protein and (ingredients or flavors):
        search_mode = "protein"
    elif protein:
        search_mode = "protein"
    elif flavors or ingredients:
        search_mode = "flavor"
    elif mood:
        search_mode = "mood"
    else:
        search_mode = "general"

    main_bits: list[str] = []
    if protein:
        main_bits.append(protein)
    if flavors:
        main_bits.extend(flavors[:2])
    if dish_queries:
        main_bits.append(dish_queries[0])
    if mood and not main_bits:
        main_bits.append(mood)
    if not main_bits:
        main_bits = [w for w in re.findall(r"[a-z]{4,}", lower) if w not in _STOP][:2]
    main_query = " ".join(main_bits[:4]) or text.strip()[:40]

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
        "main_query": main_query,
        "pairing_queries": [],
        "search_terms": [],
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