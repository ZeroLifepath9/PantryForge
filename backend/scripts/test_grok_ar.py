"""Smoke tests for prompt-only craving search."""

import asyncio
import re

from app.services.chef_agent import mock_analyze
from app.services.grok_recipes import search_craving_lineup

_BANNED = re.compile(r"\b(taco|burrito|fajita|quesadilla|street\s*food|taqueria|elote|birria)\b", re.I)


def _assert_no_banned(text: str, context: str) -> None:
    if _BANNED.search(text):
        raise AssertionError(f"Banned term in {context}: {text!r}")


async def test_mock_chicken_plan() -> None:
    plan = mock_analyze("chicken")
    terms = " ".join(plan.get("search_terms") or [])
    _assert_no_banned(terms, "chicken search_terms")
    _assert_no_banned(plan.get("chef_intro") or "", "chicken chef_intro")
    assert "chicken" in terms.lower(), f"expected chicken in terms: {terms}"


async def test_lineup_chicken() -> None:
    payload, _ = await search_craving_lineup("chicken")
    queries = " ".join((payload.get("parsed") or {}).get("search_terms") or [])
    _assert_no_banned(queries, "chicken queries")
    _assert_no_banned(payload.get("chef_intro") or "", "chicken lineup intro")
    recipes = payload.get("recipes") or []
    for r in recipes:
        title = r.get("title") or ""
        _assert_no_banned(title, "chicken lineup title")
    print(f"chicken: {len(recipes)} recipes, queries={queries[:80]}")


async def test_lineup_street_tacos_allowed() -> None:
    payload, _ = await search_craving_lineup("street tacos")
    queries = " ".join((payload.get("parsed") or {}).get("search_terms") or [])
    assert "taco" in queries.lower(), f"expected taco in queries: {queries}"
    print(f"street tacos: {len(payload.get('recipes') or [])} recipes")


async def main() -> None:
    await test_mock_chicken_plan()
    print("mock chicken plan OK")
    await test_lineup_chicken()
    print("chicken lineup OK")
    await test_lineup_street_tacos_allowed()
    print("street tacos lineup OK")


if __name__ == "__main__":
    asyncio.run(main())