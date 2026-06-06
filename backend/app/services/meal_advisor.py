"""AlchemyPantry meal advisor — xAI-powered insights with mock fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services import mock_data
from app.services.xai_client import chat_completion

ADVISOR_SYSTEM = """You are the AlchemyPantry cooking advisor: practical, warm, and direct.
You help home cooks use what they have, respect health restrictions, and elevate meals.

TWO INPUT LAYERS:
1. "ingredients" / pantry — what they actually have (Spoonacular already searched from this).
2. "what_sounds_good" — mood, craving, texture, cuisine vibe. Weight this heavily when ranking and comparing.

SCOPE:
- Compare recipes in the list: trade-offs (time, missing items, diet fit, vibe match).
- Pick mains from the recipe list AND suggest complementary sides, salads, dips, sauces when sensible.
- Explain WHY each pick fits restrictions, pantry, and what sounds good.
- Never invent recipes with a recipe_id — only use ids from the provided recipe list.
- You MAY suggest generic sides/salads/dips (recipe_id null) when pantry ingredients support them.

DEEPER INSIGHT (when deeper_insight is true):
- Add sections on protein preparation (brined vs store-bought, pat dry, resting, internal temps).
- Explain cooking methods that elevate the dish (sear vs simmer, when to add acid, finishing fats).
- Compare 2–3 top options directly: "If you want X choose A; if you want Y choose B."

RULES:
- Honor ALL diets, intolerances, and medical conditions in the payload.
- No medical diagnosis — general cooking guidance only; suggest consulting a clinician for strict medical diets.
- Be concise unless deeper_insight is true (then technique sections may be one short paragraph each).
- Output ONLY valid JSON, no markdown fences, matching this schema:
{
  "headline": "short encouraging title",
  "summary": "2-3 sentence overview comparing best fits to what sounds good",
  "top_picks": [
    {
      "category": "main|side|salad|dip|upgrade|pairing",
      "title": "name",
      "why": "why it fits restrictions, pantry, and craving",
      "recipe_id": null or integer from recipe list
    }
  ],
  "sections": [
    {"heading": "section title", "body": "insight text"}
  ]
}

Always include at least one side, salad, or dip when ingredients allow.
Include technique or protein-prep guidance when meat, poultry, or fish appear in ingredients or recipes.
"""

ADVISOR_PROMPT_VERSION = "alchemy-advisor-v2"


def _label_map(options: list[dict[str, str]]) -> dict[str, str]:
    return {o["value"]: o["label"] for o in options}


def _restriction_labels(
    diets: list[str],
    intolerances: list[str],
    health_conditions: list[str],
) -> dict[str, list[str]]:
    diet_labels = _label_map(mock_data.DIET_OPTIONS)
    intolerance_labels = _label_map(mock_data.INTOLERANCE_OPTIONS)
    health_labels = _label_map(mock_data.HEALTH_CONDITION_OPTIONS)
    return {
        "diets": [diet_labels.get(d, d) for d in diets],
        "intolerances": [intolerance_labels.get(i, i) for i in intolerances],
        "health_conditions": [health_labels.get(h, h) for h in health_conditions],
    }


def _recipe_payload(recipes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": r.get("id"),
            "title": r.get("title"),
            "match_tier": r.get("match_tier"),
            "match_label": r.get("match_label"),
            "summary": r.get("summary"),
            "diets": r.get("diets", []),
            "used_ingredients": [u.get("name") for u in r.get("used_ingredients", [])],
            "missed_ingredients": [m.get("name") for m in r.get("missed_ingredients", [])],
        }
        for r in recipes[:25]
    ]


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def mock_meal_insights(
    *,
    ingredients: list[str],
    diets: list[str],
    intolerances: list[str],
    health_conditions: list[str],
    recipes: list[dict[str, Any]],
    what_sounds_good: str | None = None,
    deeper_insight: bool = False,
) -> dict[str, Any]:
    restrictions = _restriction_labels(diets, intolerances, health_conditions)
    active_filters = (
        restrictions["diets"]
        + restrictions["intolerances"]
        + restrictions["health_conditions"]
    )
    filter_note = (
        f" respecting {', '.join(active_filters)}"
        if active_filters
        else " with no extra diet filters applied"
    )
    craving = (
        f" You mentioned wanting something like: {what_sounds_good}."
        if what_sounds_good
        else ""
    )

    mains = [r for r in recipes if r.get("match_tier") in ("exact", "stretch")][:3]
    if not mains:
        mains = recipes[:3]

    top_picks: list[dict[str, Any]] = []
    for r in mains:
        top_picks.append({
            "category": "main",
            "title": r.get("title", "Recipe"),
            "why": f"Uses your pantry well{filter_note}. {r.get('match_label', '')}",
            "recipe_id": r.get("id"),
        })

    ing_lower = " ".join(ingredients).lower()
    has_tomato = "tomato" in ing_lower
    has_basil = "basil" in ing_lower

    if has_tomato:
        top_picks.append({
            "category": "salad",
            "title": "Quick cucumber-tomato salad",
            "why": "Cold side that pairs with hot mains; stays within most restrictions if you skip heavy dressing.",
            "recipe_id": None,
        })
    if has_tomato and has_basil:
        top_picks.append({
            "category": "dip",
            "title": "Tomato-basil yogurt dip",
            "why": "Fast dip for bread or vegetables; skip dairy if that intolerance is active.",
            "recipe_id": None,
        })
    top_picks.append({
        "category": "side",
        "title": "Garlic olive oil greens",
        "why": "Wilt spinach or any greens in garlic oil — balances pasta or egg mains.",
        "recipe_id": None,
    })

    sections: list[dict[str, str]] = [
        {
            "heading": "How to read these results",
            "body": (
                "Mains are recipe cards below. Sides, salads, and dips here are advisor suggestions "
                "you can make from the same pantry without a separate search."
                + craving
            ),
        },
    ]

    has_protein = any(k in ing_lower for k in ("chicken", "pork", "beef", "meat", "fish", "salmon", "shrimp"))
    if has_protein:
        body = (
            "Raw poultry from the package is fine but often bland and can dry out. "
            "A quick brine (salt + water, 30 minutes to overnight) seasons meat through and "
            "helps it stay juicy — especially for skillet or roast dishes. "
            "Pre-brined or kosher birds are already salted; taste before adding more salt. "
            "Pat dry before searing so you get color, not steam."
        )
        if deeper_insight:
            body += (
                " For skillet chicken: medium-high heat, don't crowd the pan, and let pieces sit "
                "until they release naturally before flipping. Rest 5 minutes before slicing."
            )
        sections.append({"heading": "Brined vs raw from the store", "body": body})
    else:
        sections.append({
            "heading": "Small upgrades that matter",
            "body": (
                "Toast dried spices in the pan for 30 seconds before adding fat. "
                "Finish with a squeeze of lemon or splash of vinegar to brighten egg and tomato dishes. "
                "Rest cooked proteins 3–5 minutes before slicing so juices stay in the plate."
            ),
        })

    if deeper_insight and len(mains) >= 2:
        compare = " vs ".join(r.get("title", "option") for r in mains[:2])
        sections.append({
            "heading": "Comparing your top options",
            "body": (
                f"Between {compare}: pick the one with fewer missed ingredients if you want fastest path; "
                f"pick the other if it better matches what sounds good{craving.rstrip('.')}. "
                "Both can share the same side salad from your tomato and herbs."
            ),
        })

    if restrictions["health_conditions"]:
        sections.append({
            "heading": "Medical dietary note",
            "body": (
                f"Filters active: {', '.join(restrictions['health_conditions'])}. "
                "Advisor picks lean toward lower sodium and simpler preparations — "
                "always confirm strict medical diets with your care team."
            ),
        })

    return {
        "headline": "Your pantry, sorted",
        "summary": (
            f"From {len(recipes)} matches, start with a main that uses what you listed{filter_note}. "
            "Add a side or salad to round out the plate without another shopping trip."
        ),
        "top_picks": top_picks[:8],
        "sections": sections,
        "mock": True,
        "xai_configured": bool(settings.xai_api_key),
        "prompt_version": ADVISOR_PROMPT_VERSION,
    }


def _normalize_response(raw: dict[str, Any]) -> dict[str, Any]:
    top_picks = raw.get("top_picks") or []
    sections = raw.get("sections") or []
    return {
        "headline": str(raw.get("headline") or "Kitchen insights"),
        "summary": str(raw.get("summary") or ""),
        "top_picks": [
            {
                "category": str(p.get("category") or "main"),
                "title": str(p.get("title") or ""),
                "why": str(p.get("why") or ""),
                "recipe_id": p.get("recipe_id"),
            }
            for p in top_picks
            if p.get("title")
        ],
        "sections": [
            {
                "heading": str(s.get("heading") or ""),
                "body": str(s.get("body") or ""),
            }
            for s in sections
            if s.get("heading") and s.get("body")
        ],
        "mock": False,
        "xai_configured": True,
        "prompt_version": ADVISOR_PROMPT_VERSION,
    }


async def generate_meal_insights(
    *,
    ingredients: list[str],
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
    recipes: list[dict[str, Any]] | None = None,
    what_sounds_good: str | None = None,
    deeper_insight: bool = False,
) -> dict[str, Any]:
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []
    recipes = recipes or []

    if not settings.xai_api_key:
        return mock_meal_insights(
            ingredients=ingredients,
            diets=diets,
            intolerances=intolerances,
            health_conditions=health_conditions,
            recipes=recipes,
            what_sounds_good=what_sounds_good,
            deeper_insight=deeper_insight,
        )

    payload = {
        "ingredients": ingredients,
        "restrictions": _restriction_labels(diets, intolerances, health_conditions),
        "what_sounds_good": what_sounds_good,
        "deeper_insight": deeper_insight,
        "recipes": _recipe_payload(recipes),
    }
    user_content = (
        "Analyze this AlchemyPantry search and return advisor JSON only.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        text = await chat_completion(system=ADVISOR_SYSTEM, user_content=user_content)
        parsed = _extract_json(text)
        result = _normalize_response(parsed)
        result["mock"] = False
        result["xai_configured"] = True
        result["prompt_version"] = ADVISOR_PROMPT_VERSION
        return result
    except Exception:
        fallback = mock_meal_insights(
            ingredients=ingredients,
            diets=diets,
            intolerances=intolerances,
            health_conditions=health_conditions,
            recipes=recipes,
            what_sounds_good=what_sounds_good,
            deeper_insight=deeper_insight,
        )
        fallback["summary"] = (
            "AI advisor is temporarily unavailable — showing rule-based guidance. "
            + fallback.get("summary", "")
        )
        return fallback