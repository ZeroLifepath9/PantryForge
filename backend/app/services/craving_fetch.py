"""Fetch a large, diverse candidate pool from Spoonacular."""

from __future__ import annotations

from typing import Any

from app.services.dish_families import cuisine_for_anchor, detect_dish_anchor
from app.services.spoonacular import complex_search

POOL_TARGET = 100


def _real_ingredients(parsed: dict[str, Any]) -> list[str]:
    """Food ingredients only — not flavors like 'spicy'."""
    from app.services.dish_families import FLAVOR_WORDS

    dish_words = set()
    for q in parsed.get("dish_queries") or []:
        dish_words.add(q.lower())
    anchor = parsed.get("dish_anchor")
    if anchor:
        dish_words.add(anchor.replace("_", " "))

    out: list[str] = []
    for raw in parsed.get("ingredients") or []:
        ing = str(raw).strip().lower()
        if not ing or ing in FLAVOR_WORDS or ing in dish_words:
            continue
        out.append(ing)
    return out


async def fetch_live_candidates(
    parsed: dict[str, Any],
    *,
    diets: list[str],
    intolerances: list[str],
    what_sounds_good: str = "",
) -> list[dict[str, Any]]:
    dish_anchor = parsed.get("dish_anchor")
    dish_queries = list(parsed.get("dish_queries") or [])
    if dish_anchor and not dish_queries:
        _, dish_queries = detect_dish_anchor(what_sounds_good or parsed.get("main_query") or "")

    protein = (parsed.get("protein") or "").strip().lower()
    flavors = [str(f).lower() for f in (parsed.get("flavors") or []) if f]
    ingredients = _real_ingredients(parsed)
    main_query = (what_sounds_good or parsed.get("main_query") or "dinner").strip()
    cuisine = parsed.get("cuisine") or cuisine_for_anchor(dish_anchor)

    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()

    async def _add_batch(
        *,
        query: str,
        number: int,
        source_query: str | None = None,
        dish_type: str | None = None,
        sort: str = "popularity",
        include_ing: str | None = None,
        cuisine_param: str | None = None,
    ) -> None:
        batch = await complex_search(
            query=query,
            number=number,
            diets=diets,
            intolerances=intolerances,
            dish_type=dish_type,
            sort=sort,
            sort_direction="desc",
            include_ingredients=include_ing,
            fill_ingredients=bool(include_ing),
            cuisine=cuisine_param,
        )
        tag = (source_query or query).lower()
        for card in batch:
            if card["id"] in seen:
                for existing in candidates:
                    if existing["id"] == card["id"]:
                        sq = existing.setdefault("source_queries", [])
                        if tag not in sq:
                            sq.append(tag)
                        break
                continue
            seen.add(card["id"])
            card = dict(card)
            card["category"] = card.get("category") or "main"
            card["source_queries"] = [tag]
            candidates.append(card)

    # 1) Broad craving search — cast the widest net first
    await _add_batch(query=main_query, number=25, source_query=main_query)

    # 2) Dish-family: many queries, no meal-type lock
    if dish_anchor and dish_queries:
        per_query = max(6, POOL_TARGET // max(len(dish_queries), 1))
        for dq in dish_queries[:14]:
            q = f"{protein} {dq}".strip() if protein else dq
            await _add_batch(query=q, number=min(per_query, 15), source_query=dq)

        if cuisine:
            cq = f"{protein} {cuisine}".strip() if protein else cuisine
            await _add_batch(query=cq, number=20, source_query=cuisine, cuisine_param=cuisine)

    # 3) Protein + flavor (e.g. spicy ground beef) — no ingredient gate
    if protein:
        flavor_q = " ".join(flavors[:2])
        pq = f"{protein} {flavor_q}".strip() if flavor_q else protein
        await _add_batch(query=pq, number=20, source_query=pq)
        if "ground" in main_query.lower() or "ground beef" in main_query.lower():
            await _add_batch(query="ground beef", number=20, source_query="ground beef")
            if flavors:
                await _add_batch(
                    query=f"ground beef {' '.join(flavors[:2])}".strip(),
                    number=20,
                    source_query="ground beef spicy",
                )

    # 4) Protein + real ingredients only when user named pantry items
    if protein and len(ingredients) >= 1:
        await _add_batch(
            query=protein,
            number=20,
            include_ing=",".join(ingredients[:4]),
            source_query=f"{protein}+ingredients",
        )
    elif ingredients and not dish_anchor:
        await _add_batch(
            query=main_query,
            number=20,
            include_ing=",".join(ingredients[:4]),
            source_query="ingredients",
        )

    if not candidates:
        await _add_batch(query=main_query, number=25)

    return candidates[:POOL_TARGET]