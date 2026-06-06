"""Inspired-by cooking: pantry check, substitutions, adjusted steps."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.recipe_search import get_recipe_detail
from app.services.xai_client import chat_completion

SUB_SYSTEM = """You suggest culinary substitutions when a cook lacks recipe ingredients.
Each substitute must serve the SAME PURPOSE (acid for acid, fat for fat, binder for binder).
Output ONLY valid JSON array:
[
  {
    "original_key": "key from payload",
    "original_name": "name",
    "substitute": "replacement ingredient",
    "purpose": "why this role matters",
    "note": "one sentence on how it changes the dish"
  }
]
Only suggest for ingredients NOT in available_keys. Max one substitute per missing item."""

COOK_SYSTEM = """You write clear home-cooking steps for a meal inspired by selected recipes.
The cook may have substitutions — honor approved_substitutions exactly.
Output ONLY valid JSON:
{
  "meal_title": "short name for the combined meal",
  "steps": [
    {"step": 1, "text": "instruction", "tip": "optional beginner tip or null"}
  ]
}
Order steps logically across mains and sides (prep → cook main → cook sides → serve).
If explain_techniques is false, keep tips null and be direct."""


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _guess_role(name: str) -> str:
    lower = name.lower()
    if any(p in lower for p in ("chicken", "beef", "pork", "fish", "shrimp", "egg", "tofu")):
        return "protein"
    if any(s in lower for s in ("pasta", "noodle", "rice", "potato", "bread")):
        return "starch"
    if any(a in lower for a in ("garlic", "onion", "shallot", "ginger")):
        return "aromatic"
    if any(f in lower for f in ("oil", "butter", "cream", "cheese")):
        return "fat"
    if any(a in lower for a in ("lemon", "vinegar", "lime")):
        return "acid"
    if any(h in lower for h in ("basil", "parsley", "cilantro", "thyme")):
        return "herb"
    return "ingredient"


MOCK_SUBS: dict[str, tuple[str, str]] = {
    "butter": ("olive oil", "Fat for sautéing — use a bit more oil."),
    "cream": ("milk", "Still adds richness; reduce heat to avoid curdling."),
    "parmesan": ("cheddar", "Salty hard cheese — grate finely."),
    "basil": ("parsley", "Fresh green herb — different flavor, still bright."),
    "mushroom": ("zucchini", "Earthy vegetable — slice and sauté similarly."),
    "chicken": ("tofu", "Protein — press dry and sear for texture."),
    "lemon": ("vinegar", "Acid to brighten — use half the amount."),
}


async def load_recipes(recipe_ids: list[int]) -> list[dict[str, Any]]:
    recipes = []
    for rid in recipe_ids:
        detail, _ = await get_recipe_detail(rid)
        if detail:
            recipes.append(detail)
    return recipes


async def inspired_setup(
    recipe_ids: list[int],
    *,
    what_sounds_good: str | None = None,
) -> tuple[dict[str, Any], bool]:
    recipes = await load_recipes(recipe_ids)
    if not recipes:
        raise ValueError("No recipes found for selection")

    ingredients: list[dict[str, Any]] = []
    for recipe in recipes:
        for idx, ing in enumerate(recipe.get("ingredients") or []):
            name = ing.get("name") or "ingredient"
            key = f"{recipe['id']}-{idx}"
            ingredients.append({
                "key": key,
                "name": name,
                "amount": ing.get("amount"),
                "role": _guess_role(name),
                "recipe_id": recipe["id"],
                "recipe_title": recipe["title"],
            })

    titles = [r["title"] for r in recipes]
    if len(titles) == 1:
        meal_title = titles[0]
    else:
        meal_title = f"Meal inspired by: {titles[0]}" + (f" + {len(titles) - 1} more" if len(titles) > 1 else "")

    if what_sounds_good:
        meal_title = f"{meal_title} ({what_sounds_good[:40]})"

    return {
        "meal_title": meal_title,
        "ingredients": ingredients,
        "recipe_titles": titles,
    }, False


def _mock_substitutions(
    ingredients: list[dict[str, Any]],
    available_keys: list[str],
) -> list[dict[str, str]]:
    available = set(available_keys)
    subs: list[dict[str, str]] = []
    for ing in ingredients:
        if ing["key"] in available:
            continue
        name_lower = ing["name"].lower()
        substitute, note = None, ""
        for key, (sub, n) in MOCK_SUBS.items():
            if key in name_lower:
                substitute, note = sub, n
                break
        if not substitute:
            substitute = "similar pantry item"
            note = f"Use something that fills the {_guess_role(ing['name'])} role."
        subs.append({
            "original_key": ing["key"],
            "original_name": ing["name"],
            "substitute": substitute,
            "purpose": _guess_role(ing["name"]),
            "note": note,
        })
    return subs


async def suggest_substitutions(
    recipe_ids: list[int],
    available_keys: list[str],
    *,
    what_sounds_good: str | None = None,
) -> tuple[dict[str, Any], bool]:
    setup, _ = await inspired_setup(recipe_ids, what_sounds_good=what_sounds_good)
    ingredients = setup["ingredients"]
    missing = [i for i in ingredients if i["key"] not in set(available_keys)]

    if not missing:
        return {"substitutions": []}, not bool(settings.xai_api_key)

    if not settings.xai_api_key:
        return {"substitutions": _mock_substitutions(ingredients, available_keys)}, True

    payload = {
        "available_keys": available_keys,
        "missing": missing,
        "what_sounds_good": what_sounds_good,
    }
    try:
        text = await chat_completion(
            system=SUB_SYSTEM,
            user_content=json.dumps(payload, ensure_ascii=False),
            temperature=0.4,
        )
        raw = _extract_json(text)
        if not isinstance(raw, list):
            raw = raw.get("substitutions") or []
        subs = [
            {
                "original_key": str(s.get("original_key") or ""),
                "original_name": str(s.get("original_name") or ""),
                "substitute": str(s.get("substitute") or ""),
                "purpose": str(s.get("purpose") or "ingredient"),
                "note": str(s.get("note") or ""),
            }
            for s in raw
            if s.get("original_key") and s.get("substitute")
        ]
        return {"substitutions": subs}, False
    except Exception:
        return {"substitutions": _mock_substitutions(ingredients, available_keys)}, True


def _mock_inspired_steps(
    recipes: list[dict[str, Any]],
    *,
    substitutions: list[dict[str, str]],
    explain_techniques: bool,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    step_num = 1
    sub_map = {s["original_name"].lower(): s["substitute"] for s in substitutions}

    for recipe in recipes:
        steps.append({
            "step": step_num,
            "text": f"Prep ingredients for {recipe['title']}.",
            "tip": "Mise en place — gather and measure before heat." if explain_techniques else None,
        })
        step_num += 1
        for instruction in recipe.get("instructions") or []:
            text = instruction
            for orig, sub in sub_map.items():
                if orig in text.lower():
                    text = f"{text} (using {sub} instead of {orig})"
            tip = None
            if explain_techniques:
                if "sauté" in text.lower():
                    tip = "Sauté: medium heat, stir, don't brown garlic too fast."
                elif "simmer" in text.lower():
                    tip = "Simmer: small gentle bubbles, not a rolling boil."
            steps.append({"step": step_num, "text": text, "tip": tip})
            step_num += 1

    steps.append({
        "step": step_num,
        "text": "Plate the main with sides and serve while hot.",
        "tip": None,
    })

    titles = [r["title"] for r in recipes]
    meal_title = titles[0] if len(titles) == 1 else f"Inspired meal: {', '.join(titles[:2])}"

    return {"meal_title": meal_title, "steps": steps}


async def generate_inspired_steps(
    recipe_ids: list[int],
    available_keys: list[str],
    *,
    approved_substitutions: list[dict[str, str]] | None = None,
    explain_techniques: bool = True,
    what_sounds_good: str | None = None,
) -> tuple[dict[str, Any], bool]:
    recipes = await load_recipes(recipe_ids)
    if not recipes:
        raise ValueError("No recipes found")

    approved = approved_substitutions or []
    setup, _ = await inspired_setup(recipe_ids, what_sounds_good=what_sounds_good)

    if not settings.xai_api_key:
        result = _mock_inspired_steps(
            recipes,
            substitutions=approved,
            explain_techniques=explain_techniques,
        )
        result["substitutions_applied"] = approved
        return result, True

    recipe_payload = [
        {
            "id": r["id"],
            "title": r["title"],
            "ingredients": r.get("ingredients") or [],
            "instructions": r.get("instructions") or [],
        }
        for r in recipes
    ]
    available_names = [
        i["name"] for i in setup["ingredients"] if i["key"] in set(available_keys)
    ]
    payload = {
        "recipes": recipe_payload,
        "available_ingredients": available_names,
        "approved_substitutions": approved,
        "explain_techniques": explain_techniques,
        "what_sounds_good": what_sounds_good,
    }

    try:
        text = await chat_completion(
            system=COOK_SYSTEM,
            user_content=json.dumps(payload, ensure_ascii=False),
            temperature=0.5,
        )
        parsed = _extract_json(text)
        steps = [
            {
                "step": int(s.get("step") or i + 1),
                "text": str(s.get("text") or ""),
                "tip": s.get("tip") or None,
            }
            for i, s in enumerate(parsed.get("steps") or [])
            if s.get("text")
        ]
        return {
            "meal_title": str(parsed.get("meal_title") or setup["meal_title"]),
            "steps": steps,
            "substitutions_applied": approved,
        }, False
    except Exception:
        result = _mock_inspired_steps(
            recipes,
            substitutions=approved,
            explain_techniques=explain_techniques,
        )
        result["substitutions_applied"] = approved
        return result, True