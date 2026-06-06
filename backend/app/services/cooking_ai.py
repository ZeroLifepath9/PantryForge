"""AI ingredient parsing and step simplification — mock until XAI_API_KEY is set."""

from __future__ import annotations

from app.config import settings
from app.services import mock_data


async def parse_ingredients(text: str) -> tuple[list[str], bool]:
    if settings.mock_mode or not settings.xai_api_key:
        return mock_data.mock_parse_ingredients(text), True
    # Phase 3: call xAI here
    return mock_data.mock_parse_ingredients(text), True


async def simplify_recipe(
    recipe_id: int,
    *,
    explain_techniques: bool = True,
    skill_level: str = "beginner",
) -> tuple[dict | None, bool]:
    if settings.mock_mode or not settings.xai_api_key:
        result = mock_data.mock_simplify_steps(
            recipe_id,
            explain_techniques=explain_techniques,
            skill_level=skill_level,
        )
        return result, True
    result = mock_data.mock_simplify_steps(
        recipe_id,
        explain_techniques=explain_techniques,
        skill_level=skill_level,
    )
    return result, True