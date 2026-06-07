"""In-process cache for Grok + AllRecipes recipe cards."""

from __future__ import annotations

from typing import Any

_RECIPES: dict[int, dict[str, Any]] = {}


def put(recipe: dict[str, Any]) -> int:
    rid = int(recipe["id"])
    _RECIPES[rid] = recipe
    return rid


def put_many(recipes: list[dict[str, Any]]) -> None:
    for r in recipes:
        put(r)


def get(recipe_id: int) -> dict[str, Any] | None:
    return _RECIPES.get(recipe_id)


def get_detail(recipe_id: int) -> dict[str, Any] | None:
    r = get(recipe_id)
    if not r:
        return None
    return {
        "id": r["id"],
        "title": r.get("title"),
        "image": r.get("image"),
        "summary": r.get("summary"),
        "ready_in_minutes": r.get("ready_in_minutes"),
        "servings": r.get("servings"),
        "source_url": r.get("source_url"),
        "video_url": r.get("video_url"),
        "ingredients": r.get("ingredients") or [
            {"name": n, "amount": None} for n in (r.get("ingredient_names") or [])
        ],
        "instructions": r.get("instructions") or [],
        "diets": r.get("diets") or [],
    }