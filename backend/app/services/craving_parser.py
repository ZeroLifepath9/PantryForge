"""Parse 'what sounds good' into search terms via xAI."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.xai_client import chat_completion

PARSER_SYSTEM = """You parse what a home cook says sounds good into structured search terms.
Output ONLY valid JSON, no markdown, matching:
{
  "protein": "chicken|beef|pork|fish|shrimp|tofu|egg|turkey|lamb|null",
  "starches": ["noodles", "potato", "rice", ...],
  "flavors": ["garlic", "lemon", ...],
  "cuisine": "italian|mexican|asian|null",
  "mood": "light|comfort|crispy|fresh|hearty|null",
  "main_query": "short Spoonacular search phrase for main course with protein if any",
  "pairing_queries": ["side salad", "garlic dip", ...],
  "search_terms": ["all", "normalized", "terms"]
}

Rules:
- Extract explicit proteins (chicken, beef, salmon, etc.) even if phrased casually.
- Extract starches/carbs: noodles, pasta, potatoes, rice, bread, etc.
- main_query should be 2-5 words ideal for recipe API search.
- pairing_queries: 2-4 short queries for sides, salads, dips that pair with the main_query.
- search_terms: deduplicated list of concrete food words from the request.
"""

PROTEINS = (
    "chicken", "beef", "pork", "fish", "salmon", "shrimp", "tofu", "egg", "turkey",
    "lamb", "bacon", "sausage", "steak", "cod", "tuna", "crab",
)
STARCHES = (
    "noodles", "pasta", "spaghetti", "potato", "potatoes", "rice", "bread",
    "tortilla", "quinoa", "couscous", "macaroni",
)
MOODS = {
    "light": ("light", "fresh", "healthy", "simple"),
    "comfort": ("comfort", "cozy", "hearty", "warm"),
    "crispy": ("crispy", "crunchy", "fried"),
}


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _normalize_parsed(raw: dict[str, Any], original: str) -> dict[str, Any]:
    protein = raw.get("protein")
    if protein in (None, "null", ""):
        protein = None
    else:
        protein = str(protein).lower().strip()

    starches = [str(s).lower().strip() for s in (raw.get("starches") or []) if s]
    flavors = [str(f).lower().strip() for f in (raw.get("flavors") or []) if f]
    search_terms = [str(t).lower().strip() for t in (raw.get("search_terms") or []) if t]

    cuisine = raw.get("cuisine")
    if cuisine in (None, "null", ""):
        cuisine = None
    else:
        cuisine = str(cuisine).lower().strip()

    mood = raw.get("mood")
    if mood in (None, "null", ""):
        mood = None
    else:
        mood = str(mood).lower().strip()

    main_query = str(raw.get("main_query") or "").strip()
    if not main_query:
        parts = [p for p in [protein, *starches[:2], mood] if p]
        main_query = " ".join(parts) or original.strip()[:80]

    pairing_queries = [
        str(q).strip() for q in (raw.get("pairing_queries") or []) if q
    ]
    if not pairing_queries:
        pairing_queries = ["side salad", "roasted vegetables", "dip"]

    if protein and protein not in search_terms:
        search_terms.insert(0, protein)
    for s in starches:
        if s not in search_terms:
            search_terms.append(s)

    return {
        "protein": protein,
        "starches": starches,
        "flavors": flavors,
        "cuisine": cuisine,
        "mood": mood,
        "main_query": main_query,
        "pairing_queries": pairing_queries[:4],
        "search_terms": list(dict.fromkeys(search_terms)),
    }


def mock_parse_craving(text: str) -> dict[str, Any]:
    lower = text.lower()
    protein = next((p for p in PROTEINS if re.search(rf"\b{re.escape(p)}\b", lower)), None)
    starches = [s for s in STARCHES if re.search(rf"\b{re.escape(s)}\b", lower)]
    flavors = [f for f in ("garlic", "lemon", "basil", "tomato", "cheese", "spicy") if f in lower]

    mood = None
    for mood_key, words in MOODS.items():
        if any(w in lower for w in words):
            mood = mood_key
            break

    cuisine = None
    for c in ("italian", "mexican", "asian", "indian", "thai", "chinese"):
        if c in lower:
            cuisine = c
            break

    parts = [p for p in [protein, *starches[:2], mood] if p]
    main_query = " ".join(parts) if parts else text.strip()[:60]

    pairing_queries = []
    if protein:
        pairing_queries.append(f"{protein} side dish")
    pairing_queries.extend(["fresh salad", "vegetable side", "dip sauce"])
    pairing_queries = list(dict.fromkeys(pairing_queries))[:4]

    search_terms = list(dict.fromkeys(
        ([protein] if protein else [])
        + starches
        + flavors
        + [w for w in re.findall(r"[a-z]{3,}", lower) if w not in ("something", "with", "and", "the")]
    ))[:12]

    return {
        "protein": protein,
        "starches": starches,
        "flavors": flavors,
        "cuisine": cuisine,
        "mood": mood,
        "main_query": main_query,
        "pairing_queries": pairing_queries,
        "search_terms": search_terms,
    }


async def parse_craving(text: str) -> tuple[dict[str, Any], bool]:
    text = text.strip()
    if not text:
        raise ValueError("what_sounds_good is required")

    if not settings.xai_api_key:
        return mock_parse_craving(text), True

    user_content = f'Parse this craving: "{text}"'
    try:
        raw_text = await chat_completion(system=PARSER_SYSTEM, user_content=user_content, temperature=0.3)
        parsed = _normalize_parsed(_extract_json(raw_text), text)
        return parsed, False
    except Exception:
        return mock_parse_craving(text), True