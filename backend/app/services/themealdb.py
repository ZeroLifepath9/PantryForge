"""TheMealDB — free JSON API that works from cloud hosts (Render, etc.)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

BASE = "https://www.themealdb.com/api/json/v1/1"


def _meal_ingredients(meal: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for i in range(1, 21):
        ing = (meal.get(f"strIngredient{i}") or "").strip()
        if not ing:
            continue
        measure = (meal.get(f"strMeasure{i}") or "").strip()
        rows.append(f"{measure} {ing}".strip() if measure else ing)
    return rows


def _meal_instructions(meal: dict[str, Any]) -> list[str]:
    raw = meal.get("strInstructions") or ""
    parts = re.split(r"[\r\n]+", raw)
    steps = [p.strip() for p in parts if len(p.strip()) > 8]
    if steps:
        return steps
    return [raw.strip()] if raw.strip() else []


def meal_to_card(meal: dict[str, Any], *, search_query: str = "") -> dict[str, Any]:
    ingredients = _meal_ingredients(meal)
    return {
        "id": int(meal["idMeal"]),
        "title": meal.get("strMeal") or "Recipe",
        "category": "main",
        "image": meal.get("strMealThumb"),
        "summary": " · ".join(
            x for x in (meal.get("strCategory"), meal.get("strArea")) if x
        ) or None,
        "ready_in_minutes": None,
        "servings": None,
        "source_url": meal.get("strSource") or f"https://www.themealdb.com/meal/{meal['idMeal']}",
        "diets": [],
        "ingredient_names": [i.lower() for i in ingredients],
        "ingredients": [{"name": i, "amount": None} for i in ingredients],
        "instructions": _meal_instructions(meal),
        "rating_count": 0,
        "source": "themealdb",
        "search_query": search_query,
        "_full_card": True,
    }


async def _lookup(client: httpx.AsyncClient, meal_id: str) -> dict[str, Any] | None:
    try:
        r = await client.get(f"{BASE}/lookup.php", params={"i": meal_id})
        meals = r.json().get("meals") or []
        return meals[0] if meals else None
    except Exception as exc:
        logger.warning("TheMealDB lookup %s failed: %s", meal_id, exc)
        return None


async def search_themealdb(query: str, *, limit: int = 12) -> list[dict[str, Any]]:
    q = query.strip()
    if not q:
        return []

    stubs: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for url in (
            f"{BASE}/search.php?s={quote(q)}",
            f"{BASE}/filter.php?i={quote(q)}",
            f"{BASE}/filter.php?c={quote(q.title())}",
        ):
            try:
                r = await client.get(url)
                batch = r.json().get("meals") or []
                for m in batch:
                    if m and m.get("idMeal") and m not in stubs:
                        stubs.append(m)
            except Exception as exc:
                logger.warning("TheMealDB search %s failed: %s", url, exc)

        seen_ids: set[str] = set()
        unique: list[dict[str, Any]] = []
        for m in stubs:
            mid = str(m["idMeal"])
            if mid not in seen_ids:
                seen_ids.add(mid)
                unique.append(m)
            if len(unique) >= limit:
                break

        if not unique:
            return []

        if unique[0].get("strInstructions"):
            return [meal_to_card(m, search_query=q) for m in unique[:limit]]

        lookups = await asyncio.gather(*[_lookup(client, str(m["idMeal"])) for m in unique[:limit]])
        cards: list[dict[str, Any]] = []
        for meal in lookups:
            if meal:
                cards.append(meal_to_card(meal, search_query=q))
        return cards


async def gather_themealdb_hits(queries: list[str], *, per_query: int = 8) -> list[dict[str, Any]]:
    batches = await asyncio.gather(
        *[search_themealdb(q, limit=per_query) for q in queries if q.strip()]
    )
    merged: list[dict[str, Any]] = []
    seen: set[int] = set()
    for batch in batches:
        for card in batch:
            rid = card["id"]
            if rid not in seen:
                seen.add(rid)
                merged.append(card)
    return merged