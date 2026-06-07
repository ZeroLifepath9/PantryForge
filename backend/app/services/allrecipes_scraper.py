"""Scrape real recipes from AllRecipes.com (search + JSON-LD detail pages)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

BASE = "https://www.allrecipes.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_SKIP_TITLE_MARKERS = (
    "taco bell", "aldi", "costco", "mcdonald", "starbucks",
    "ingredient this home cook", "menu item", "fan-favorite",
    "coming for", "newest menu", "meal kits",
)

_RECIPE_URL = re.compile(
    r"https://www\.allrecipes\.com/(?:recipe/\d+[^\"'\s]*|[^\"'\s]+-recipe-\d+[^\"'\s]*)",
    re.I,
)


def _is_recipe_url(url: str) -> bool:
    if "/search" in url or "/article/" in url:
        return False
    return "/recipe/" in url or "-recipe-" in url


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def _parse_iso_minutes(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?", value)
    if not m:
        return None
    hours = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    total = hours * 60 + mins
    return total or None


def _parse_instructions(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    steps: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            steps.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("text") or item.get("name") or ""
            if text:
                steps.append(str(text).strip())
    return steps


def _parse_ld_recipe(html: str) -> dict[str, Any] | None:
    pat = re.compile(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.S | re.I,
    )
    for m in pat.finditer(html):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Recipe" in types:
                return item
    return None


def url_to_recipe_id(url: str) -> int:
    nums = re.findall(r"\d+", url)
    if nums:
        n = int(nums[-1])
        if n > 0:
            return n
    return abs(hash(url)) % 800_000 + 200_000


async def search_allrecipes(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Return recipe hits from AllRecipes search for a query string."""
    q = query.strip()
    if not q:
        return []
    url = f"{BASE}/search?q={quote_plus(q)}"
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.warning("AllRecipes search %r failed: %s", query, exc)
        return []

    titles = re.findall(r'<span class="card__title-text[^"]*">([^<]+)</span>', html)
    urls = _RECIPE_URL.findall(html)

    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, link in enumerate(urls):
        if not _is_recipe_url(link):
            continue
        if link in seen:
            continue
        title = _clean_title(titles[i]) if i < len(titles) else ""
        if not title:
            slug = link.rstrip("/").split("/")[-1].replace("-", " ")
            title = _clean_title(slug)
        lower = title.lower()
        if any(marker in lower for marker in _SKIP_TITLE_MARKERS):
            continue
        seen.add(link)
        hits.append({
            "title": title,
            "url": link.split("?")[0],
            "source": "allrecipes",
            "search_query": q,
        })
        if len(hits) >= limit:
            break
    return hits


async def fetch_recipe_page(url: str) -> dict[str, Any] | None:
    """Fetch a single AllRecipes recipe page and parse JSON-LD."""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            ld = _parse_ld_recipe(resp.text)
    except Exception as exc:
        logger.warning("AllRecipes fetch %s failed: %s", url, exc)
        return None

    if not ld:
        return None

    title = _clean_title(str(ld.get("name") or "Recipe"))
    ingredients = [str(i).strip() for i in (ld.get("recipeIngredient") or []) if str(i).strip()]
    instructions = _parse_instructions(ld.get("recipeInstructions"))
    image = ld.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")

    aggregate = ld.get("aggregateRating") or {}
    rating_count = 0
    try:
        rating_count = int(aggregate.get("ratingCount") or 0)
    except (TypeError, ValueError):
        pass

    rid = url_to_recipe_id(url)
    prep = _parse_iso_minutes(ld.get("prepTime"))
    cook = _parse_iso_minutes(ld.get("cookTime"))
    total = _parse_iso_minutes(ld.get("totalTime")) or ((prep or 0) + (cook or 0) or None)

    return {
        "id": rid,
        "title": title,
        "category": "main",
        "image": image,
        "summary": (ld.get("description") or "")[:500] or None,
        "ready_in_minutes": total,
        "servings": ld.get("recipeYield"),
        "source_url": url.split("?")[0],
        "diets": [],
        "ingredient_names": [i.lower() for i in ingredients],
        "ingredients": [{"name": i, "amount": None} for i in ingredients],
        "instructions": instructions,
        "rating_count": rating_count,
        "source": "allrecipes",
    }


async def gather_search_hits(queries: list[str], *, per_query: int = 12) -> list[dict[str, Any]]:
    tasks = [search_allrecipes(q, limit=per_query) for q in queries if q.strip()]
    if not tasks:
        return []
    batches = await asyncio.gather(*tasks)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for batch in batches:
        for hit in batch:
            u = hit.get("url") or ""
            if u and u not in seen:
                seen.add(u)
                merged.append(hit)
    return merged


async def fetch_recipes_parallel(urls: list[str], *, concurrency: int = 6) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(concurrency)
    results: list[dict[str, Any]] = []

    async def one(u: str) -> None:
        async with sem:
            card = await fetch_recipe_page(u)
            if card:
                results.append(card)

    await asyncio.gather(*(one(u) for u in urls))
    return results