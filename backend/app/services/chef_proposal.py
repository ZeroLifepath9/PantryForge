"""Competition-style dish proposal: chef pitches, judge approves."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.inspired_cook import inspired_setup, load_recipes
from app.services.xai_client import chat_completion

PROPOSAL_SYSTEM = """You are an executive chef in a televised cooking competition.
The judge told you what sounds good. You studied their inspiration dishes — you will NOT copy them.
You must scratch their urge with ONLY what they have at home (plus any approved substitutions).

Speak like a confident professional pitching one original plate to the judge.

Output ONLY valid JSON:
{
  "dish_name": "evocative name for your competition plate",
  "pitch": "2-3 sentences: why this dish hits their craving tonight",
  "technique_highlight": "the signature technique that makes this plate yours",
  "plate_description": "how it looks, smells, and eats on the plate",
  "pantry_note": "one sentence on how you are using what they actually have"
}"""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _mock_proposal(
    *,
    what_sounds_good: str | None,
    available_names: list[str],
    approved_subs: list[dict[str, str]],
    recipe_titles: list[str],
) -> dict[str, Any]:
    urge = (what_sounds_good or "something satisfying").strip()[:80]
    sub_note = ""
    if approved_subs:
        sub_note = f" I'm swapping {approved_subs[0]['original_name']} for {approved_subs[0]['substitute']}."
    pantry = ", ".join(available_names[:5]) if available_names else "your pantry"
    insp = recipe_titles[0] if recipe_titles else "your picks"
    return {
        "dish_name": f"Judge's {urge.title()} Plate",
        "pitch": (
            f"You wanted {urge} — I'm building one composed plate that steals the best idea from "
            f"{insp} without cooking every recipe separately.{sub_note}"
        ),
        "technique_highlight": "Layer flavor in stages: sear protein hard, build a quick pan sauce, finish with fresh contrast.",
        "plate_description": (
            "One focal main with a supporting side element on the same plate — color, acid, and heat balanced."
        ),
        "pantry_note": f"Built around what you have: {pantry}.",
    }


async def generate_chef_proposal(
    recipe_ids: list[int],
    available_keys: list[str],
    *,
    approved_substitutions: list[dict[str, str]] | None = None,
    what_sounds_good: str | None = None,
) -> tuple[dict[str, Any], bool]:
    approved = approved_substitutions or []
    setup, _ = await inspired_setup(recipe_ids, what_sounds_good=what_sounds_good)
    recipes = await load_recipes(recipe_ids)
    available = set(available_keys)
    available_names = [i["name"] for i in setup["ingredients"] if i["key"] in available]
    for sub in approved:
        available_names.append(sub.get("substitute") or "")

    titles = setup.get("recipe_titles") or [r["title"] for r in recipes]
    insight = setup.get("creation_insight") or {}

    if not settings.xai_key:
        return _mock_proposal(
            what_sounds_good=what_sounds_good,
            available_names=[n for n in available_names if n],
            approved_subs=approved,
            recipe_titles=titles,
        ), True

    missing = [i for i in setup["ingredients"] if i["key"] not in available]
    payload = {
        "what_sounds_good": what_sounds_good,
        "inspiration_titles": titles,
        "creation_insight": insight,
        "available_ingredients": [n for n in available_names if n],
        "missing_ingredients": [i["name"] for i in missing],
        "approved_substitutions": approved,
    }
    try:
        text = await chat_completion(
            system=PROPOSAL_SYSTEM,
            user_content=json.dumps(payload, ensure_ascii=False),
            temperature=0.55,
        )
        raw = _extract_json(text)
        return {
            "dish_name": str(raw.get("dish_name") or "Chef's plate"),
            "pitch": str(raw.get("pitch") or ""),
            "technique_highlight": str(raw.get("technique_highlight") or ""),
            "plate_description": str(raw.get("plate_description") or ""),
            "pantry_note": str(raw.get("pantry_note") or ""),
        }, False
    except Exception:
        return _mock_proposal(
            what_sounds_good=what_sounds_good,
            available_names=[n for n in available_names if n],
            approved_subs=approved,
            recipe_titles=titles,
        ), True