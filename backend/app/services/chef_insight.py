"""Executive-chef voice: landscape intro + per-recipe technique notes via Grok."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.xai_client import chat_completion

CHEF_SYSTEM = """You are a world-class executive chef advising a home cook on AlchemyPantry.

The user named what sounds good. You receive up to 25 real recipes already fetched from a recipe API.
Your job is INSIGHT — never remove recipes, never return fewer than given.

Output ONLY valid JSON:
{
  "chef_headline": "one vivid line (e.g. 'Tacos are a universe — here are 25 ways in')",
  "chef_intro": "2-4 sentences: the landscape of preparations, techniques, regional styles, what differs between picks",
  "recipes": [
    {"id": <exact id from input>, "fit_note": "one chef sentence: technique, flavor angle, or why this variation matters"}
  ]
}

Rules:
- Include EVERY recipe id from the input list in recipes[].
- fit_note = professional insight (braise vs grill, spice profile, texture, tradition) — not generic praise.
- chef_intro should educate: different ways the dish is prepared when the craving is broad.
"""

RECIPE_LIMIT = 25


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _mock_chef_enrichment(
    what_sounds_good: str,
    parsed: dict[str, Any],
    recipes: list[dict[str, Any]],
) -> tuple[str, str, list[dict[str, Any]]]:
    anchor = (parsed.get("dish_anchor") or "").replace("_", " ")
    protein = parsed.get("protein")
    if anchor:
        headline = f"{anchor.title()} — many ways to nail it"
        intro = (
            f"You asked for {anchor} — that's a whole family of preparations: grilled, braised, "
            f"street-style, baked, slow-cooked. Each recipe below shows a different technique and flavor profile. "
            f"Scan the list for the cooking method that matches your night."
        )
    elif protein:
        headline = f"{protein.title()} — let's explore the options"
        intro = (
            f"There's more than one way to cook {protein} for this craving. "
            f"Below are distinct preparations — pay attention to heat (sear vs simmer), "
            f"spice level, and what sides or wraps complete the plate."
        )
    else:
        headline = "Here's your lineup"
        intro = (
            f"For '{what_sounds_good}', I've pulled varied preparations so you can compare techniques "
            f"and flavors — not just one path to the same dish."
        )

    enriched = []
    for card in recipes:
        c = dict(card)
        title = card.get("title", "This dish")
        c["fit_note"] = (
            f"Chef's take: {title} — study how this version handles seasoning and texture; "
            f"borrow the technique that fits your pantry."
        )
        enriched.append(c)
    return headline, intro, enriched


async def enrich_with_chef_insight(
    what_sounds_good: str,
    parsed: dict[str, Any],
    recipes: list[dict[str, Any]],
) -> tuple[str | None, str | None, list[dict[str, Any]], bool]:
    if not recipes:
        return None, None, [], not bool(settings.xai_key)

    if not settings.xai_key:
        h, i, r = _mock_chef_enrichment(what_sounds_good, parsed, recipes)
        return h, i, r, True

    slim = [
        {"id": c["id"], "title": c.get("title"), "summary": (c.get("summary") or "")[:180]}
        for c in recipes[:RECIPE_LIMIT]
    ]
    payload = {
        "what_sounds_good": what_sounds_good,
        "parsed": {
            "dish_anchor": parsed.get("dish_anchor"),
            "protein": parsed.get("protein"),
            "flavors": parsed.get("flavors"),
            "ingredients": parsed.get("ingredients"),
        },
        "recipes": slim,
    }
    try:
        text = await chat_completion(
            system=CHEF_SYSTEM,
            user_content=json.dumps(payload, ensure_ascii=False),
            temperature=0.45,
        )
        raw = _extract_json(text)
        by_id = {c["id"]: dict(c) for c in recipes}
        notes = {p["id"]: p.get("fit_note") for p in (raw.get("recipes") or []) if p.get("id") is not None}
        enriched = []
        for card in recipes:
            c = dict(card)
            note = notes.get(card["id"])
            if note:
                c["fit_note"] = str(note)
            enriched.append(c)
        return (
            str(raw.get("chef_headline") or "").strip() or None,
            str(raw.get("chef_intro") or "").strip() or None,
            enriched,
            False,
        )
    except Exception:
        h, i, r = _mock_chef_enrichment(what_sounds_good, parsed, recipes)
        return h, i, r, True