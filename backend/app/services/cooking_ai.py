"""AI step simplification and ingredient parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services import mock_data
from app.services.recipe_search import get_recipe_detail
from app.services.xai_client import chat_completion

SIMPLIFY_SYSTEM = """You are an executive chef teaching a home cook through a recipe.
Honor their diets, allergies, medical needs, protein preference, and side/salad choices.
Suggest ingredient substitutions inline when an ingredient conflicts with their filters.

Output ONLY valid JSON:
{
  "steps": [
    {"step": 1, "text": "clear instructor-level instruction", "tip": "technique tip or null"}
  ]
}
Keep every cooking step — do not skip. If explain_techniques is false, set all tips to null.
One action per step. Precise heat, timing, and sensory cues."""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


async def parse_ingredients(text: str) -> tuple[list[str], bool]:
    return mock_data.mock_parse_ingredients(text), True


async def simplify_recipe(
    recipe_id: int,
    *,
    explain_techniques: bool = True,
    skill_level: str = "beginner",
    what_sounds_good: str | None = None,
    protein_filters: list[str] | None = None,
    side_filters: list[str] | None = None,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
) -> tuple[dict | None, bool]:
    detail, is_mock_detail = await get_recipe_detail(recipe_id)
    if not detail:
        return None, True

    direct = skill_level == "direct" or not explain_techniques
    if not settings.xai_key or is_mock_detail:
        result = mock_data.mock_simplify_steps(
            recipe_id,
            explain_techniques=explain_techniques,
            skill_level=skill_level,
        )
        return result, True

    payload = {
        "title": detail["title"],
        "ingredients": detail.get("ingredients") or [],
        "instructions": detail.get("instructions") or [],
        "explain_techniques": not direct,
        "what_sounds_good": what_sounds_good,
        "protein_filters": protein_filters or [],
        "side_filters": side_filters or [],
        "diets": diets or [],
        "intolerances": intolerances or [],
        "health_conditions": health_conditions or [],
    }
    try:
        text = await chat_completion(
            system=SIMPLIFY_SYSTEM,
            user_content=json.dumps(payload, ensure_ascii=False),
            temperature=0.4,
        )
        parsed = _extract_json(text)
        steps = [
            {
                "step": int(s.get("step") or i + 1),
                "text": str(s.get("text") or ""),
                "tip": s.get("tip") if not direct else None,
            }
            for i, s in enumerate(parsed.get("steps") or [])
            if s.get("text")
        ]
        if not steps:
            raise ValueError("empty steps")
        mode = "direct" if direct else "beginner"
        return {
            "recipe_id": recipe_id,
            "title": detail["title"],
            "mode": mode,
            "steps": steps,
        }, False
    except Exception:
        result = mock_data.mock_simplify_steps(
            recipe_id,
            explain_techniques=explain_techniques,
            skill_level=skill_level,
        )
        return result, True