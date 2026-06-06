"""Fetch recipe candidates from Spoonacular for a parsed craving."""

from __future__ import annotations

from typing import Any

from app.services.dish_families import detect_dish_anchor, matches_dish_family
from app.services.spoonacular import complex_search

POOL_TARGET = 60


def _ingredient_list(parsed: dict[str, Any]) -> list[str]:
    return [str(i).strip().lower() for i in (parsed.get("ingredients") or []) if i]


async def fetch_live_candidates(
    parsed: dict[str, Any],
    *,
    diets: list[str],
    intolerances: list[str],
) -> list[dict[str, Any]]:
    dish_anchor = parsed.get("dish_anchor")
    dish_queries = list(parsed.get("dish_queries") or [])
    if dish_anchor and not dish_queries:
        _, dish_queries = detect_dish_anchor(parsed.get("main_query") or "")

    protein = (parsed.get("protein") or "").strip().lower()
    ingredients = _ingredient_list(parsed)
    include_ingredients = ",".join(ingredients[:6]) if ingredients else None
    main_query = (parsed.get("main_query") or "dinner").strip()

    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    async def _add_batch(
        *,
        query: str,
        number: int,
        sort: str = "popularity",
        include_ing: str | None = None,
        fill_ingredients: bool = False,
    ) -> None:
        batch = await complex_search(
            query=query,
            number=number,
            diets=diets,
            intolerances=intolerances,
            dish_type="main course",
            sort=sort,
            sort_direction="desc",
            include_ingredients=include_ing or include_ingredients,
            fill_ingredients=fill_ingredients or bool(ingredients),
        )
        for card in batch:
            if card["id"] in seen:
                continue
            seen.add(card["id"])
            card = dict(card)
            card["category"] = "main"
            candidates.append(card)

    if dish_anchor and dish_queries:
        per_query = max(4, POOL_TARGET // max(len(dish_queries), 1))
        for dq in dish_queries:
            q = f"{protein} {dq}".strip() if protein else dq
            await _add_batch(query=q, number=min(per_query, 12))

    if protein and ingredients:
        await _add_batch(
            query=protein,
            number=20,
            fill_ingredients=True,
        )
    elif ingredients:
        await _add_batch(
            query=main_query,
            number=20,
            fill_ingredients=True,
        )
    elif protein and not dish_anchor:
        await _add_batch(query=protein, number=25)

    if not candidates:
        await _add_batch(query=main_query, number=25)

    # Drop obvious off-topic results when we have a dish anchor
    if dish_anchor:
        filtered = [c for c in candidates if matches_dish_family(c, dish_anchor)]
        if filtered:
            candidates = filtered + [c for c in candidates if c not in filtered]

    return candidates[:POOL_TARGET]