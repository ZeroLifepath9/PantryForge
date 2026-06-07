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

Output ONLY valid JSON:
{
  "chef_headline": "one vivid line",
  "chef_intro": "2-3 sentences welcoming them and framing how you'll guide the meal",
  "craving_threads": [
    {
      "label": "short name e.g. Tacos",
      "search_terms": ["taco", "street taco", "fish taco", ...],
      "chef_note": "one sentence why this thread matters"
    }
  ],
  "shared_bridge": {
    "label": "something both cravings share that they did NOT ask for",
    "search_terms": ["2-4 spoonacular queries for that bridge dish/side"],
    "chef_note": "why a top chef would add this — technique or flavor link"
  },
  "pairing_side_terms": ["side dishes that pair with the mains — 4-8 queries"],
  "protein": null,
  "protein_options": ["chicken","beef","pork","shrimp","fish","salmon","tofu","turkey","lamb","vegetarian"]
}

RULES:
- If they name ONE craving (tacos), one thread. If they name TWO+ (tacos and salad, pasta or chicken), one thread PER option.
- shared_bridge is your professional insight — a dish/side/technique connecting their threads they didn't mention.
- search_terms = concrete Spoonacular queries (2-6 per thread). Include variations (preparations, styles).
- protein only if they explicitly named one; else null (UI filters later).
- pairing_side_terms = sides/salads/dips that complete the plate."""

CHEF_CURATE = """You are the same executive chef. You receive Spoonacular recipe candidates and the chef plan.

Pick exactly 25 recipes: roughly 18 mains and 7 sides/salads/dips that pair well. Honor every craving thread with several mains each. Include shared_bridge picks. Sides must complement the mains.

Output ONLY valid JSON:
{
  "recipes": [
    {
      "id": <candidate id only>,
      "fit_note": "one chef sentence: technique, pairing role, or why this preparation",
      "thread_label": "which thread or Shared bridge or Pairing"
    }
  ]
}

Rules:
- Exactly 25 ids from candidates (or all if fewer than 25).
- Mix categories: mostly main, ~7 sides.
- fit_note = professional insight, not generic.
- Distribute across threads when multiple exist."""

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
        "taco": (["taco", "street taco", "fish taco", "carnitas", "burrito"], "Tacos"),
        "chili": (["chili", "beef chili", "turkey chili"], "Chili"),
        "pasta": (["pasta", "spaghetti", "lasagna"], "Pasta"),
        "pizza": (["pizza", "flatbread pizza"], "Pizza"),
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
        "pairing_side_terms": [
            "black beans", "mexican rice", "guacamole", "pico de gallo",
            "cilantro lime slaw", "refried beans",
        ][:6],
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
        c["fit_note"] = "A distinct preparation worth studying."
        c["thread_label"] = plan["craving_threads"][0]["label"] if plan.get("craving_threads") else "Main"
        picked.append(c)
        seen.add(card["id"])

    bridge = (plan.get("shared_bridge") or {}).get("label", "Shared bridge")
    for card in sides + other:
        if len(picked) >= limit:
            break
        if card["id"] in seen:
            continue
        c = dict(card)
        c["fit_note"] = f"Pairs with your mains — {bridge} energy on the plate."
        c["thread_label"] = "Pairing"
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

    return picked[:limit]


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
        }
        for c in candidates
    ]
    payload = {
        "chef_plan": plan,
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
            return curated, False
    except Exception:
        pass

    locked = [dict(by_id[i]) for i in selected_ids if i in by_id]
    rest = _mock_curate(plan, [c for c in candidates if c["id"] not in selected_ids], limit - len(locked))
    return (locked + rest)[:limit], True