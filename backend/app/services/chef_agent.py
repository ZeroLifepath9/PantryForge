"""Grok chef agent: parse cravings, search terms, curate 25 mains + sides."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.xai_client import chat_completion

PROTEIN_OPTIONS = [
    "chicken", "beef", "pork", "shrimp", "fish", "salmon", "tofu", "turkey", "lamb", "vegetarian",
]

CHEF_ANALYZE = """You are an executive chef at the absolute peak of the profession — AlchemyPantry's culinary brain.

The home cook says what sounds good. You interpret like a chef, not a search engine.
Think street food, food trucks, regional icons, AND home versions. Every search term must be something Spoonacular would actually return.

Output ONLY valid JSON:
{
  "chef_headline": "one vivid line tied to THEIR exact craving",
  "chef_intro": "2-3 sentences: you will show street-style + popular home versions + easy accent sides that cite why they pair",
  "craving_threads": [
    {
      "label": "short name e.g. Tacos",
      "search_terms": ["8-10 concrete queries: street taco, birria, al pastor, fish taco, carnitas, burrito, ..."],
      "chef_note": "one sentence why this thread matches what they said"
    }
  ],
  "shared_bridge": {
    "label": "accent they didn't ask for but pros always add",
    "search_terms": ["2-4 queries for that bridge dish/side"],
    "chef_note": "cite the flavor logic — acid/fat/crunch/heat link"
  },
  "street_food_terms": ["4-6 street-food or food-truck style queries matching the craving"],
  "pairing_side_terms": ["6-10 EASY popular sides/salads — pico, elote, beans, slaw, rice, pickles, etc."],
  "pairing_cites": {
    "exact side search term": "one line: why this ACCENTS the main (acid cuts fat, crunch vs soft, etc.)"
  },
  "protein": null,
  "protein_options": ["chicken","beef","pork","shrimp","fish","salmon","tofu","turkey","lamb","vegetarian"]
}

RULES:
- search_terms must be tightly relevant to the user's words — no generic "dinner" or "food".
- Include STREET variants (street taco, smash burger, pad thai cart style) when the craving fits.
- pairing_side_terms = popular, easy sides a chef would actually plate alongside — not random salads.
- pairing_cites: one entry per side term explaining the pairing chemistry.
- Adjacent dishes count (tacos → burrito, fajita, quesadilla)."""

CHEF_CURATE = """You are the same executive chef. You receive Spoonacular candidates PRE-SORTED by relevance, the chef plan, and what_sounds_good.

Pick exactly 25 recipes: ~18 mains + ~7 sides/salads/dips. REJECT candidates whose title does not match the craving — no random eggs, smoothies, or unrelated dishes.

Output ONLY valid JSON:
{
  "recipes": [
    {
      "id": <candidate id only>,
      "fit_note": "MUST cite relevance: for mains name style (street/home/regional) + why it hits the urge; for sides end with 'Pairs because: ...' citing acid/fat/crunch/heat accent",
      "thread_label": "thread name | Street food | Pairing accent | Shared bridge"
    }
  ]
}

Rules:
- Every pick must clearly connect to what_sounds_good — if you cannot explain it in fit_note, do NOT pick it.
- Include several street-food or food-truck style mains when the craving fits tacos, burgers, noodles, etc.
- ~7 sides: popular, easy, with fit_note ending "Pairs because: [flavor logic]".
- Use pairing_cites from chef_plan when available.
- Prefer higher-relevance candidates (listed first)."""

CHEF_REFINE = """You are the executive chef. The cook selected up to 5 recipes from your lineup. Refresh the OTHER slots (keep their selections) with mains and sides that pair better with what they chose.

Output ONLY valid JSON:
{
  "chef_intro": "1-2 sentences on how the lineup now complements their picks",
  "recipes": [
    {"id": <candidate id>, "fit_note": "chef note", "thread_label": "..."}
  ]
}

Rules:
- Must include ALL selected_ids in output (unchanged fit_note ok).
- Fill to 25 total using candidates only.
- Favor sides that pair with selections."""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _mock_pairing_terms(lower: str, threads: list[dict]) -> list[str]:
    from app.services.chef_relevance import PAIRING_ACCENTS, GENERIC_PAIRING_SIDES

    if "taco" in lower or any("taco" in t.get("label", "").lower() for t in threads):
        pool = PAIRING_ACCENTS.get("taco", [])
    elif "chili" in lower:
        pool = PAIRING_ACCENTS.get("chili", [])
    elif "pasta" in lower:
        pool = PAIRING_ACCENTS.get("pasta", [])
    elif "burger" in lower:
        pool = PAIRING_ACCENTS.get("burger", [])
    else:
        pool = GENERIC_PAIRING_SIDES
    return [t for t, _ in pool[:8]]


def _mock_pairing_cites(lower: str) -> dict[str, str]:
    from app.services.chef_relevance import PAIRING_ACCENTS, GENERIC_PAIRING_SIDES

    if "taco" in lower:
        pool = PAIRING_ACCENTS.get("taco", [])
    elif "chili" in lower:
        pool = PAIRING_ACCENTS.get("chili", [])
    else:
        pool = GENERIC_PAIRING_SIDES
    return {t: c for t, c in pool}


def STREET_FROM_MOCK(lower: str, threads: list[dict]) -> list[str]:
    from app.services.chef_relevance import STREET_FOOD_TERMS

    if "taco" in lower or any("taco" in t.get("label", "").lower() for t in threads):
        return STREET_FOOD_TERMS.get("taco", [])[:5]
    if "burger" in lower:
        return STREET_FOOD_TERMS.get("burger", [])[:4]
    return []


def _split_craving_threads(text: str) -> list[str]:
    lower = text.lower()
    parts = re.split(r"\s+(?:and|or|&|\+|,)\s+", lower)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def mock_analyze(what_sounds_good: str, protein_filter: str | None = None) -> dict[str, Any]:
    text = what_sounds_good.strip()
    lower = text.lower()
    parts = _split_craving_threads(text)
    threads: list[dict[str, Any]] = []

    dish_map = {
        "taco": (
            ["street taco", "birria taco", "al pastor", "fish taco", "carnitas", "carne asada taco", "burrito", "quesadilla"],
            "Tacos & street food",
        ),
        "chili": (["chili", "beef chili", "texas chili", "turkey chili", "chili bowl"], "Chili"),
        "pasta": (["pasta", "spaghetti", "carbonara", "cacio e pepe"], "Pasta"),
        "pizza": (["pizza", "margherita pizza", "flatbread"], "Pizza"),
        "burger": (["smash burger", "burger", "slider"], "Burgers"),
        "salad": (["salad", "grain bowl"], "Salad"),
        "soup": (["soup", "stew"], "Soup"),
    }

    used = set()
    for part in parts[:3]:
        matched = False
        for key, (terms, label) in dish_map.items():
            if key in part:
                threads.append({
                    "label": label,
                    "search_terms": terms,
                    "chef_note": f"A chef explores many {label.lower()} preparations for you.",
                })
                used.add(key)
                matched = True
                break
        if not matched and len(part) > 3:
            threads.append({
                "label": part[:40].title(),
                "search_terms": [part[:50], f"{part} recipe"],
                "chef_note": f"Varied approaches to {part}.",
            })

    if not threads:
        threads.append({
            "label": "Your craving",
            "search_terms": [text[:60], *parts[:2]] if parts else [text[:60]],
            "chef_note": "Several preparations worth comparing.",
        })

    bridge_label = "Chef's bridge"
    bridge_terms = ["rice", "pickled onions"]
    if len(threads) >= 2:
        bridge_label = "Shared accent — citrus & herbs"
        bridge_terms = ["cilantro lime rice", "quick pickled onions", "avocado crema"]
    elif "taco" in lower or any("taco" in t["label"].lower() for t in threads):
        bridge_label = "Elote-style corn"
        bridge_terms = ["mexican street corn", "elote", "cilantro lime rice"]

    protein = protein_filter
    if not protein:
        for p in PROTEIN_OPTIONS:
            if p != "vegetarian" and re.search(rf"\b{re.escape(p)}\b", lower):
                protein = p
                break

    return {
        "chef_headline": "Let me show you the full landscape",
        "chef_intro": (
            "I'm pulling real recipes across every preparation style — mains and sides that "
            "actually belong on the same plate. Select up to five and I'll refine the rest around your picks."
        ),
        "craving_threads": threads,
        "shared_bridge": {
            "label": bridge_label,
            "search_terms": bridge_terms,
            "chef_note": "Something you didn't ask for — but it ties the plate together.",
        },
        "street_food_terms": STREET_FROM_MOCK(lower, threads),
        "pairing_side_terms": _mock_pairing_terms(lower, threads),
        "pairing_cites": _mock_pairing_cites(lower),
        "protein": protein,
        "protein_options": PROTEIN_OPTIONS,
        "protein_filter": protein_filter,
    }


async def analyze_craving(
    what_sounds_good: str,
    *,
    protein_filter: str | None = None,
) -> tuple[dict[str, Any], bool]:
    if not settings.xai_key:
        plan = mock_analyze(what_sounds_good, protein_filter)
        if protein_filter:
            plan["protein"] = protein_filter if protein_filter != "vegetarian" else None
            plan["protein_filter"] = protein_filter
        return plan, True

    user = json.dumps({
        "what_sounds_good": what_sounds_good,
        "protein_filter": protein_filter,
    })
    try:
        raw = await chat_completion(system=CHEF_ANALYZE, user_content=user, temperature=0.4)
        plan = _extract_json(raw)
        plan.setdefault("protein_options", PROTEIN_OPTIONS)
        if protein_filter:
            plan["protein"] = None if protein_filter == "vegetarian" else protein_filter
            plan["protein_filter"] = protein_filter
        return plan, False
    except Exception:
        plan = mock_analyze(what_sounds_good, protein_filter)
        return plan, True


def _apply_pairing_cites(curated: list[dict[str, Any]], plan: dict[str, Any]) -> None:
    from app.services.chef_relevance import pairing_cite_for_term

    for card in curated:
        if card.get("category") not in ("side", "salad", "dip"):
            continue
        note = card.get("fit_note") or ""
        if "pairs because" in note.lower():
            continue
        cite = pairing_cite_for_term(plan, card.get("title", ""))
        card["fit_note"] = f"{note} Pairs because: {cite}".strip()


def _mock_curate(plan: dict[str, Any], candidates: list[dict[str, Any]], limit: int = 25) -> list[dict[str, Any]]:
    mains = [c for c in candidates if c.get("category") == "main"]
    sides = [c for c in candidates if c.get("category") in ("side", "salad", "dip")]
    other = [c for c in candidates if c not in mains and c not in sides]

    picked: list[dict[str, Any]] = []
    seen: set[int] = set()

    def take(pool: list, n: int, label: str) -> None:
        for card in pool:
            if card["id"] in seen:
                continue
            c = dict(card)
            c["fit_note"] = c.get("fit_note") or f"Chef pick — {label}."
            c["thread_label"] = label
            picked.append(c)
            seen.add(card["id"])
            if len(picked) >= limit:
                return
            if sum(1 for x in picked if x.get("category") == "main") >= 18 and card.get("category") == "main":
                continue

    target_mains = min(18, max(12, limit - 7))
    for card in mains[:target_mains]:
        if len(picked) >= limit:
            break
        if card["id"] in seen:
            continue
        c = dict(card)
        label = plan["craving_threads"][0]["label"] if plan.get("craving_threads") else "Main"
        c["fit_note"] = f"Hits your craving — {label.lower()} style worth comparing."
        c["thread_label"] = label
        picked.append(c)
        seen.add(card["id"])

    bridge = (plan.get("shared_bridge") or {}).get("label", "Shared bridge")
    for card in sides + other:
        if len(picked) >= limit:
            break
        if card["id"] in seen:
            continue
        c = dict(card)
        from app.services.chef_relevance import pairing_cite_for_term

        cite = pairing_cite_for_term(plan, card.get("title", ""))
        c["fit_note"] = f"Popular easy side. Pairs because: {cite}"
        c["thread_label"] = "Pairing accent"
        picked.append(c)
        seen.add(card["id"])

    for card in mains + sides + other:
        if len(picked) >= limit:
            break
        if card["id"] in seen:
            continue
        c = dict(card)
        picked.append(c)
        seen.add(card["id"])

    result = picked[:limit]
    _apply_pairing_cites(result, plan)
    return result


async def curate_lineup(
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    selected_ids: list[int] | None = None,
    limit: int = 25,
) -> tuple[list[dict[str, Any]], bool]:
    selected_ids = selected_ids or []
    by_id = {c["id"]: c for c in candidates}

    if not settings.xai_key or not candidates:
        locked = [dict(by_id[i]) for i in selected_ids if i in by_id]
        rest = _mock_curate(plan, [c for c in candidates if c["id"] not in selected_ids], limit - len(locked))
        return (locked + rest)[:limit], True

    slim = [
        {
            "id": c["id"],
            "title": c.get("title"),
            "category": c.get("category"),
            "summary": (c.get("summary") or "")[:160],
            "relevance": c.get("_relevance"),
            "ingredients": (c.get("ingredient_names") or [])[:8],
        }
        for c in candidates
    ]
    payload = {
        "chef_plan": plan,
        "what_sounds_good": plan.get("what_sounds_good") or "",
        "candidates": slim,
        "selected_ids": selected_ids,
        "target_count": limit,
    }

    system = CHEF_REFINE if selected_ids else CHEF_CURATE
    try:
        raw = await chat_completion(
            system=system,
            user_content=json.dumps(payload, ensure_ascii=False),
            temperature=0.35,
        )
        data = _extract_json(raw)
        if selected_ids and data.get("chef_intro"):
            plan["chef_intro"] = data["chef_intro"]
        picks = data.get("recipes") or []
        curated: list[dict[str, Any]] = []
        seen: set[int] = set()
        for pick in picks:
            rid = pick.get("id")
            if rid is None or rid in seen or rid not in by_id:
                continue
            card = dict(by_id[rid])
            card["fit_note"] = str(pick.get("fit_note") or "Chef selection.")
            card["thread_label"] = pick.get("thread_label")
            curated.append(card)
            seen.add(rid)
            if len(curated) >= limit:
                break
        if curated:
            _apply_pairing_cites(curated, plan)
            return curated, False
    except Exception:
        pass

    locked = [dict(by_id[i]) for i in selected_ids if i in by_id]
    rest = _mock_curate(plan, [c for c in candidates if c["id"] not in selected_ids], limit - len(locked))
    return (locked + rest)[:limit], True