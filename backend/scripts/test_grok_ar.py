"""Smoke tests for craving translator + AllRecipes search."""

import asyncio
import re

from app.services.craving_translator import build_search_queries, translate_craving
from app.services.grok_recipes import search_craving_lineup

_BANNED = re.compile(r"\b(taco|burrito|fajita|quesadilla|street\s*food|taqueria|elote|birria)\b", re.I)
_SENTENCE_MARKERS = ("something warm and cheesy", "I want a light lemony fish dinner", "comfort food for a cold night")


def _assert_no_banned(text: str, context: str) -> None:
    if _BANNED.search(text):
        raise AssertionError(f"Banned term in {context}: {text!r}")


def _assert_no_raw_sentence(queries: list[str], prompt: str) -> None:
    pl = prompt.strip().lower()
    for q in queries:
        if q.strip().lower() == pl:
            raise AssertionError(f"Raw sentence used as query: {q!r}")


async def test_translate(prompt: str) -> None:
    plan, _ = await translate_craving(prompt)
    queries = plan.get("search_queries") or []
    assert queries, f"No queries for {prompt!r}"
    if prompt in _SENTENCE_MARKERS or len(prompt.split()) > 3:
        _assert_no_raw_sentence(queries, prompt)
    print(f"  {prompt!r}")
    print(f"    mode={plan.get('search_mode')} main={plan.get('main_query')!r}")
    print(f"    queries={queries[:6]}")


async def test_lineup(prompt: str) -> None:
    payload, _ = await search_craving_lineup(prompt)
    recipes = payload.get("recipes") or []
    queries = (payload.get("parsed") or {}).get("search_terms") or []
    assert recipes, f"No recipes for {prompt!r} (queries={queries})"
    if "chicken" == prompt:
        for r in recipes:
            _assert_no_banned(r.get("title") or "", "chicken title")
    print(f"  {prompt!r} → {len(recipes)} recipes")


async def main() -> None:
    print("Translator:")
    for p in ["chicken", "something warm and cheesy", "I want a light lemony fish dinner", "comfort food for a cold night"]:
        await test_translate(p)

    print("\nLineups:")
    for p in ["chicken", "something warm and cheesy", "comfort food for a cold night"]:
        await test_lineup(p)
    print("\nAll OK")


if __name__ == "__main__":
    asyncio.run(main())