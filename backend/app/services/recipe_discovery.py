"""Discover recipe hits — AllRecipes when possible, reliable API fallbacks on cloud."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import unquote

import httpx

from app.config import settings
from app.services.allrecipes_scraper import gather_search_hits, search_allrecipes
from app.services.spoonacular import complex_search
from app.services.themealdb import gather_themealdb_hits

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

_RECIPE_URL = re.compile(
    r"https://www\.allrecipes\.com/(?:recipe/\d+[^\"'\s]*|[^\"'\s]+-recipe-\d+[^\"'\s]*)",
    re.I,
)


def _is_recipe_url(url: str) -> bool:
    if "/search" in url or "/article/" in url or "/gallery/" in url:
        return False
    return "/recipe/" in url or "-recipe-" in url


async def _ddg_allrecipes_hits(queries: list[str], *, per_query: int = 10) -> list[dict[str, Any]]:
    """Google-style site search when AllRecipes blocks datacenter IPs."""
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for query in queries[:4]:
            if not query.strip():
                continue
            ddg_q = f"site:allrecipes.com {query} recipe"
            try:
                r = await client.post(
                    "https://html.duckduckgo.com/html/",
                    headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                    data={"q": ddg_q, "b": "", "kl": "us-en"},
                )
            except Exception as exc:
                logger.warning("DDG search failed for %r: %s", query, exc)
                continue

            for raw_url in re.findall(r'class="result__a"[^>]+href="([^"]+)"', r.text):
                url = unquote(raw_url).split("?")[0]
                if "allrecipes.com" not in url or not _is_recipe_url(url):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                slug = url.rstrip("/").split("/")[-1].replace("-", " ")
                hits.append({
                    "title": slug.title(),
                    "url": url,
                    "source": "allrecipes",
                    "search_query": query,
                })
                if len([h for h in hits if h.get("search_query") == query]) >= per_query:
                    break

    return hits


async def _spoonacular_hits(
    queries: list[str],
    *,
    per_query: int = 8,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not settings.spoonacular_key:
        return []

    async def one(q: str) -> list[dict[str, Any]]:
        try:
            batch = await complex_search(
                query=q,
                number=per_query,
                diets=diets or [],
                intolerances=intolerances or [],
                sort="popularity",
                dish_type="main course",
            )
            out: list[dict[str, Any]] = []
            for card in batch:
                c = dict(card)
                c["_full_card"] = True
                c["search_query"] = q
                c["source"] = "spoonacular"
                out.append(c)
            return out
        except Exception as exc:
            logger.warning("Spoonacular search %r failed: %s", q, exc)
            return []

    batches = await asyncio.gather(*[one(q) for q in queries[:5] if q.strip()])
    merged: list[dict[str, Any]] = []
    seen: set[int] = set()
    for batch in batches:
        for card in batch:
            rid = card["id"]
            if rid not in seen:
                seen.add(rid)
                merged.append(card)
    return merged


async def discover_recipe_hits(
    queries: list[str],
    *,
    per_query: int = 12,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Try sources in order until we get hits.
    Returns (hits, source_name).
    """
    queries = [q.strip() for q in queries if q and q.strip()]
    if not queries:
        return [], "none"

    # 1. AllRecipes direct (works on home networks; often blocked on Render)
    hits = await gather_search_hits(queries, per_query=per_query)
    if hits:
        logger.info("recipe_discovery: allrecipes direct → %d hits", len(hits))
        return hits, "allrecipes"

    # Quick probe — log if scrape is broken vs empty results
    probe = await search_allrecipes(queries[0], limit=3)
    if not probe:
        logger.warning("AllRecipes direct scrape returned 0 for %r — trying fallbacks", queries[0])

    # 2. DuckDuckGo → AllRecipes URLs
    ddg = await _ddg_allrecipes_hits(queries, per_query=per_query)
    if ddg:
        logger.info("recipe_discovery: ddg+allrecipes → %d hits", len(ddg))
        return ddg, "allrecipes-ddg"

    # 3. TheMealDB — always works from cloud
    tmdb = await gather_themealdb_hits(queries, per_query=per_query)
    if len(tmdb) < 6:
        broad = await gather_themealdb_hits(
            ["chicken", "pasta", "beef", "fish", "soup", "bake"],
            per_query=6,
        )
        seen = {c["id"] for c in tmdb}
        for card in broad:
            if card["id"] not in seen:
                seen.add(card["id"])
                tmdb.append(card)
    if tmdb:
        logger.info("recipe_discovery: themealdb → %d hits", len(tmdb))
        return tmdb, "themealdb"

    # 4. Spoonacular API if configured
    sp = await _spoonacular_hits(queries, per_query=per_query, diets=diets, intolerances=intolerances)
    if sp:
        logger.info("recipe_discovery: spoonacular → %d hits", len(sp))
        return sp, "spoonacular"

    return [], "none"