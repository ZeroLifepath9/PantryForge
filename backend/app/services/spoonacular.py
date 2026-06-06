"""Spoonacular API client for ingredient-based recipe search."""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

from app.config import settings
from app.services import mock_data

BASE_URL = "https://api.spoonacular.com"
RESULT_LIMIT = 25

# Our diet chip values → Spoonacular diet strings on recipe info.
DIET_MAP = {
    "vegetarian": "vegetarian",
    "vegan": "vegan",
    "gluten-free": "gluten free",
    "dairy-free": "dairy free",
    "ketogenic": "ketogenic",
    "paleo": "paleo",
    "pescetarian": "pescatarian",
}

PANTRY_DEFAULT = {
    "pasta", "spaghetti", "olive oil", "vegetable oil", "cheese", "parmesan",
    "salt", "pepper", "garlic", "onion", "butter",
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", cleaned)).strip()


def _ingredient_rows(items: list[dict[str, Any]] | None) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    for item in items or []:
        name = item.get("name") or item.get("originalName") or ""
        if not name:
            continue
        amount = item.get("amount")
        unit = item.get("unit") or ""
        amount_str = None
        if amount is not None:
            amount_str = f"{amount:g} {unit}".strip() if unit else f"{amount:g}"
        rows.append({"name": name, "amount": amount_str})
    return rows


INTOLERANCE_FLAGS: dict[str, str] = {
    "dairy": "dairyFree",
    "gluten": "glutenFree",
    "wheat": "glutenFree",
    "grain": "glutenFree",
}


def _recipe_intolerances_ok(info: dict[str, Any], intolerances: list[str]) -> bool:
    if not intolerances:
        return True
    for intolerance in intolerances:
        flag = INTOLERANCE_FLAGS.get(intolerance)
        if flag and not info.get(flag):
            return False
    return True


def _recipe_diets_match(recipe_diets: list[str], selected: list[str]) -> bool:
    if not selected:
        return True
    normalized = {_normalize(d) for d in recipe_diets}
    for diet in selected:
        spoon = DIET_MAP.get(diet, diet.replace("-", " "))
        if _normalize(spoon) not in normalized:
            return False
    return True


def _classify_tier(
    missed: list[str],
    effective: set[str],
    include_pantry: bool,
) -> tuple[str, str]:
    if not missed:
        return "exact", "You can make this now"
    pantry_misses = [
        m for m in missed
        if _normalize(m) in effective
        or any(_normalize(m) in _normalize(p) or _normalize(p) in _normalize(m) for p in effective)
    ]
    if include_pantry and len(missed) == len(pantry_misses):
        return "stretch", "Add a few pantry basics"
    if len(missed) <= 3:
        return "almost", "Almost — you need a little more"
    return "almost", "Close match — missing several items"


async def _request(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    query = dict(params or {})
    query["apiKey"] = settings.spoonacular_key
    response = await client.get(f"{BASE_URL}{path}", params=query)
    response.raise_for_status()
    return response.json()


async def find_by_ingredients(
    ingredients: list[str],
    *,
    number: int = RESULT_LIMIT,
    include_pantry: bool = True,
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await _request(
            client,
            "/recipes/findByIngredients",
            params={
                "ingredients": ",".join(ingredients),
                "number": number,
                "ranking": 2,
                "ignorePantry": not include_pantry,
            },
        )


async def information_bulk(recipe_ids: list[int]) -> list[dict[str, Any]]:
    if not recipe_ids:
        return []
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await _request(
            client,
            "/recipes/informationBulk",
            params={
                "ids": ",".join(str(i) for i in recipe_ids),
                "includeNutrition": False,
            },
        )


async def get_recipe_information(recipe_id: int) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            return await _request(
                client,
                f"/recipes/{recipe_id}/information",
                params={"includeNutrition": False},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise


def _map_search_result(
    raw: dict[str, Any],
    info: dict[str, Any] | None,
    *,
    user_set: set[str],
    effective: set[str],
    include_pantry: bool,
) -> dict[str, Any] | None:
    used = _ingredient_rows(raw.get("usedIngredients"))
    missed = _ingredient_rows(raw.get("missedIngredients"))
    unused = _ingredient_rows(raw.get("unusedIngredients"))
    missed_names = [m["name"] for m in missed if m.get("name")]

    tier, label = _classify_tier(missed_names, effective, include_pantry)

    diets_raw = (info or {}).get("diets") or []
    diets = []
    for d in diets_raw:
        key = d.lower().replace(" ", "-")
        if key == "pescatarian":
            key = "pescetarian"
        diets.append(key)

    summary = _strip_html((info or {}).get("summary")) or None
    title = (info or {}).get("title") or raw.get("title") or "Recipe"

    return {
        "id": raw["id"],
        "title": title,
        "image": raw.get("image") or (info or {}).get("image"),
        "match_tier": tier,
        "match_label": label,
        "used_ingredients": used,
        "missed_ingredients": missed,
        "unused_ingredients": unused,
        "diets": diets,
        "ready_in_minutes": (info or {}).get("readyInMinutes"),
        "servings": (info or {}).get("servings"),
        "source_url": (info or {}).get("sourceUrl"),
        "video_url": (info or {}).get("videoUrl") or None,
        "summary": summary,
    }


def _map_recipe_detail(info: dict[str, Any]) -> dict[str, Any]:
    instructions: list[str] = []
    if info.get("analyzedInstructions"):
        for block in info["analyzedInstructions"]:
            for step in block.get("steps", []):
                text = step.get("step")
                if text:
                    instructions.append(text)
    if not instructions and info.get("instructions"):
        instructions = [
            line.strip()
            for line in _strip_html(info["instructions"]).split(".")
            if line.strip()
        ]

    diets_raw = info.get("diets") or []
    diets = []
    for d in diets_raw:
        key = d.lower().replace(" ", "-")
        if key == "pescatarian":
            key = "pescetarian"
        diets.append(key)

    ingredients = _ingredient_rows(info.get("extendedIngredients"))

    return {
        "id": info["id"],
        "title": info.get("title") or "Recipe",
        "image": info.get("image"),
        "summary": _strip_html(info.get("summary")),
        "ready_in_minutes": info.get("readyInMinutes"),
        "servings": info.get("servings"),
        "source_url": info.get("sourceUrl"),
        "video_url": info.get("videoUrl"),
        "ingredients": ingredients,
        "instructions": instructions or ["See the original recipe for full steps."],
        "diets": diets,
    }


async def search_recipes(
    ingredients: list[str],
    *,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
    include_pantry_staples: bool = True,
    pantry_staples: list[str] | None = None,
) -> dict[str, Any]:
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []

    user_set = {_normalize(i) for i in ingredients}
    pantry = {_normalize(p) for p in (pantry_staples or [])}
    effective_list = list(ingredients)
    effective_set = set(user_set)
    if include_pantry_staples:
        for staple in (pantry_staples or []) + list(PANTRY_DEFAULT):
            norm = _normalize(staple)
            if norm and norm not in effective_set:
                effective_list.append(staple)
                effective_set.add(norm)

    raw_results = await find_by_ingredients(
        effective_list,
        number=RESULT_LIMIT,
        include_pantry=include_pantry_staples,
    )
    if not raw_results:
        return {
            "query_ingredients": ingredients,
            "effective_ingredients": sorted(effective_set),
            "results": [],
            "message": (
                "Spoonacular found no matches for those ingredients. "
                "Try adding a staple like pasta, rice, or eggs."
            ),
        }

    ids = [r["id"] for r in raw_results[:RESULT_LIMIT]]
    bulk = await information_bulk(ids)
    info_by_id = {item["id"]: item for item in bulk}

    results: list[dict[str, Any]] = []
    for raw in raw_results:
        info = info_by_id.get(raw["id"])
        if info:
            if diets and not _recipe_diets_match(info.get("diets") or [], diets):
                continue
            if intolerances and not _recipe_intolerances_ok(info, intolerances):
                continue
        mapped = _map_search_result(
            raw,
            info,
            user_set=user_set,
            effective=effective_set,
            include_pantry=include_pantry_staples,
        )
        if mapped and mapped["used_ingredients"]:
            results.append(mapped)

    tier_order = {"exact": 0, "stretch": 1, "almost": 2}
    results.sort(key=lambda r: tier_order.get(r["match_tier"], 9))
    results = results[:RESULT_LIMIT]

    message = None
    if not results:
        message = (
            "No recipes matched your diet filters. Try loosening lifestyle diets "
            "or add more pantry ingredients."
        )
    elif not any(r["match_tier"] == "exact" for r in results):
        message = (
            "Nothing exact with only what you listed — here are the closest options "
            "and what you'd still need."
        )
    if health_conditions:
        labels = mock_data.HEALTH_CONDITION_OPTIONS
        label_map = {o["value"]: o["label"] for o in labels}
        names = [label_map.get(h, h) for h in health_conditions]
        note = (
            f"Medical filters ({', '.join(names)}) are applied in the kitchen advisor; "
            "confirm strict medical diets with your care team."
        )
        message = f"{message} {note}" if message else note
    if results:
        shown = len(results)
        suffix = f"Showing {shown} recipe{'s' if shown != 1 else ''} from Spoonacular."
        message = f"{message} {suffix}" if message else suffix

    return {
        "query_ingredients": ingredients,
        "effective_ingredients": sorted(effective_set),
        "results": results,
        "message": message,
    }


async def get_recipe_detail(recipe_id: int) -> dict[str, Any] | None:
    info = await get_recipe_information(recipe_id)
    if not info:
        return None
    return _map_recipe_detail(info)


def _spoon_diet_param(diets: list[str]) -> str | None:
    if not diets:
        return None
    return ",".join(DIET_MAP.get(d, d.replace("-", " ")) for d in diets)


def _classify_dish_category(dish_types: list[str], title: str) -> str:
    types = " ".join(dish_types).lower()
    title_lower = title.lower()
    if any(t in types for t in ("salad", "salads")) or "salad" in title_lower:
        return "salad"
    if any(t in types for t in ("dip", "sauce", "condiment", "spread")) or "dip" in title_lower:
        return "dip"
    if any(
        t in types
        for t in ("side dish", "antipasti", "appetizer", "beverage", "soup", "starter")
    ):
        return "side"
    if "bruschetta" in title_lower or "bread" in title_lower and "main" not in types:
        return "side"
    return "main"


def _map_complex_card(info: dict[str, Any], *, category: str) -> dict[str, Any]:
    diets_raw = info.get("diets") or []
    diets = []
    for d in diets_raw:
        key = d.lower().replace(" ", "-")
        if key == "pescatarian":
            key = "pescetarian"
        diets.append(key)
    return {
        "id": info["id"],
        "title": info.get("title") or "Recipe",
        "category": category,
        "image": info.get("image"),
        "summary": _strip_html(info.get("summary")),
        "ready_in_minutes": info.get("readyInMinutes"),
        "servings": info.get("servings"),
        "source_url": info.get("sourceUrl"),
        "diets": diets,
    }


async def complex_search(
    *,
    query: str,
    number: int = 10,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    dish_type: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "query": query,
        "number": number,
        "addRecipeInformation": True,
        "fillIngredients": False,
        "instructionsRequired": True,
    }
    diet_param = _spoon_diet_param(diets or [])
    if diet_param:
        params["diet"] = diet_param
    if intolerances:
        params["intolerances"] = ",".join(intolerances)
    if dish_type:
        params["type"] = dish_type

    async with httpx.AsyncClient(timeout=60.0) as client:
        data = await _request(client, "/recipes/complexSearch", params=params)

    results: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        if diets and not _recipe_diets_match(item.get("diets") or [], diets):
            continue
        if intolerances and not _recipe_intolerances_ok(item, intolerances):
            continue
        dish_types = item.get("dishTypes") or []
        category = _classify_dish_category(dish_types, item.get("title") or "")
        if dish_type == "main course" and category != "main":
            category = "main"
        results.append(_map_complex_card(item, category=category))
    return results


def _mentions_protein(card: dict[str, Any], protein: str) -> bool:
    blob = _normalize(f"{card.get('title') or ''} {card.get('summary') or ''}")
    return protein in blob


async def search_by_craving(
    parsed: dict[str, Any],
    *,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
) -> dict[str, Any]:
    diets = diets or []
    intolerances = intolerances or []
    protein = (parsed.get("protein") or "").strip().lower()
    search_anchor = protein or (parsed.get("protein_query") or parsed.get("main_query") or "dinner")

    # Protein-first: every Spoonacular query leads with the protein, not noodles/mood/etc.
    search_plan: list[tuple[str, str | None, str, int]] = []
    if protein:
        search_plan = [
            (protein, "main course", "main", 10),
            (protein, None, "side", 8),
            (protein, None, "salad", 8),
            (protein, None, "dip", 6),
        ]
    else:
        search_plan = [
            (search_anchor, "main course", "main", 10),
            (search_anchor, None, "side", 6),
            (search_anchor, None, "salad", 6),
        ]

    mains: list[dict[str, Any]] = []
    pairings: list[dict[str, Any]] = []
    seen: set[int] = set()

    for query, dish_type, target_cat, number in search_plan:
        batch = await complex_search(
            query=query,
            number=number,
            diets=diets,
            intolerances=intolerances,
            dish_type=dish_type,
        )
        for card in batch:
            if card["id"] in seen:
                continue
            if protein and not _mentions_protein(card, protein):
                continue

            cat = card.get("category") or target_cat
            if target_cat == "main":
                cat = "main"
            elif target_cat in ("side", "salad", "dip"):
                cat = target_cat if cat in ("side", "salad", "dip") else target_cat
            else:
                cat = target_cat

            card = dict(card)
            card["category"] = cat
            seen.add(card["id"])

            if cat == "main" and len(mains) < 8:
                mains.append(card)
            elif cat != "main" and len(pairings) < 20:
                pairings.append(card)

    message = None
    if protein:
        total = len(mains) + len(pairings)
        if total:
            message = (
                f"Dishes featuring {protein} — mains, sides, and more to scratch that craving."
            )
        else:
            message = f"No recipes found for {protein}. Try another protein or loosen diet filters."
    elif not mains and not pairings:
        message = "No matches — name a protein in what sounds good (chicken, salmon, beef…)."

    return {
        "mains": mains[:8],
        "pairings": pairings[:20],
        "message": message,
        "protein_search": protein or search_anchor,
    }