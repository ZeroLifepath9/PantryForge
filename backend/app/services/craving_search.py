"""Search mains + pairings from a parsed craving."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services import mock_data
from app.services.craving_parser import parse_craving


async def search_by_craving(
    what_sounds_good: str,
    *,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
) -> tuple[dict[str, Any], bool]:
    parsed, parse_mock = await parse_craving(what_sounds_good)
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []

    use_live = bool(settings.spoonacular_api_key) and not settings.mock_mode

    if use_live:
        from app.services import spoonacular

        try:
            result = await spoonacular.search_by_craving(
                parsed, diets=diets, intolerances=intolerances
            )
            return {
                "what_sounds_good": what_sounds_good,
                "parsed": parsed,
                "mains": result["mains"],
                "pairings": result["pairings"],
                "message": result.get("message"),
            }, False
        except Exception:
            pass

    result = mock_data.mock_craving_search(
        parsed,
        diets=diets,
        intolerances=intolerances,
        health_conditions=health_conditions,
    )
    return {
        "what_sounds_good": what_sounds_good,
        "parsed": parsed,
        "mains": result["mains"],
        "pairings": result["pairings"],
        "message": result.get("message"),
        "parse_mock": parse_mock,
    }, True