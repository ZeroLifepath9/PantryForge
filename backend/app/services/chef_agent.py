"""Grok chef agent: parse cravings, search terms, curate 12 main courses."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.xai_client import chat_completion

PROTEIN_OPTIONS = [
    "chicken", "beef", "pork", "shrimp", "fish", "salmon", "tofu", "turkey", "lamb", "vegetarian",
]

CHEF_ANALYZE = """You are an executive chef — AlchemyPantry's culinary brain.

The home cook says what sounds good in their own words. Parse ONLY what they said.
Every search term must be something AllRecipes.com would return as a main-course recipe.

Output ONLY valid JSON:
{
  "chef_headline": "one vivid line tied to THEIR exact words",
  "chef_intro": "2-3 sentences: you will find popular home-cook mains that match what they said — no assumptions beyond their prompt",
  "search_terms": ["6-10 concrete AllRecipes search queries derived from their craving"],
  "flavor_notes": ["optional mood words you read from their prompt: light, crispy, lemony, etc."],
  "protein": null,
  "protein_options": ["chicken","beef","pork","shrimp","fish","salmon","tofu","turkey","lamb","vegetarian"]
}

RULES:
- search_terms MUST trace to words or clear implications in what_sounds_good.
- If they say "chicken" → chicken mains only (baked chicken, chicken parmesan, roast chicken, etc.) — NOT tacos or unrelated dishes.
- If they say "tacos" → taco-related queries are allowed; you MAY add close adjacents (burrito, fajita) because they named tacos.
- NEVER add taco, burrito, fajita, quesadilla, street food, food truck, taqueria, elote, birria, al pastor, or carnitas unless those concepts appear in what_sounds_good.
- No generic queries like "dinner", "food", or "meal".
- Do not invent cravings they did not express."""

CHEF_CURATE = """You are the same executive chef. You receive Spoonacular MAIN-COURSE candidates PRE-SORTED by relevance, the chef plan, and what_sounds_good.

Pick exactly 12 MAIN COURSES only — no sides, salads, or dips. REJECT candidates whose title does not match the craving — no random eggs, smoothies, or unrelated dishes.

Output ONLY valid JSON:
{
  "recipes": [
    {
      "id": <candidate id only>,
      "fit_note": "MUST cite relevance: name style (street/home/regional/family-adjacent) + why it hits the urge",
      "thread_label": "thread name | Street food | Dish family | Shared bridge"
    }
  ]
}

Rules:
- Every pick must clearly connect to what_sounds_good — if you cannot explain it in fit_note, do NOT pick it.
- Include street-food or food-truck style mains when the craving fits tacos, burgers, noodles, etc.
- Include same-family adjacents (taco → burrito, fajita, quesadilla, enchilada).
- Prefer higher-relevance candidates (listed first)."""

CHEF_REFINE = """You are the executive chef. The cook selected up to 5 main courses from your lineup. Refresh the OTHER slots (keep their selections) with mains that better match their craving and picks.

Output ONLY valid JSON:
{
  "chef_intro": "1-2 sentences on how the lineup now complements their picks",
  "recipes": [
    {"id": <candidate id>, "fit_note": "chef note", "thread_label": "..."}
  ]
}

Rules:
- Must include ALL selected_ids in output (unchanged fit_note ok).
- Fill to 12 total MAIN COURSES using candidates only — no sides."""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


_MOCK_STOP = frozenset({
    "something", "with", "and", "the", "for", "that", "good", "sounds", "like",
    "want", "some", "have", "what", "your", "side", "fresh", "food", "meal",
    "easy", "popular", "recipe", "recipes", "warm", "nice",
})

_FORBIDDEN_UNLESS_IN_PROMPT = (
    "street food", "food truck", "street taco", "street corn", "taqueria",
    "taco", "burrito", "fajita", "quesadilla", "enchilada", "taquito",
    "elote", "birria", "al pastor", "carnitas",
)


def _term_allowed(term: str, lower_prompt: str) -> bool:
    tl = term.lower()
    for forbidden in _FORBIDDEN_UNLESS_IN_PROMPT:
        if forbidden in tl and forbidden not in lower_prompt:
            return False
    return True


def _split_craving_threads(text: str) -> list[str]:
    lower = text.lower()
    parts = re.split(r"\s+(?:and|or|&|\+|,)\s+", lower)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def _build_mock_search_terms(text: str, lower: str, protein: str | None) -> list[str]:
    from app.services.dish_families import detect_dish_anchor

    seen: set[str] = set()
    terms: list[str] = []

    def add(q: str) -> None:
        q = q.strip()
        if len(q) < 3 or q.lower() in seen:
            return
        if not _term_allowed(q, lower):
            return
        seen.add(q.lower())
        terms.append(q)

    if text:
        add(text[:80])
    words = [w for w in re.findall(r"[a-z]{3,}", lower) if w not in _MOCK_STOP]
    for w in words[:5]:
        add(w)
        add(f"{w} recipe")
    if protein and protein != "vegetarian":
        add(f"{protein} dinner")
        add(f"easy {protein}")
        add(f"baked {protein}")
    anchor, family_queries = detect_dish_anchor(text)
    if anchor:
        for fq in family_queries[:5]:
            add(fq)
    for part in _split_craving_threads(text)[:2]:
        if len(part) > 3:
            add(part[:50])
    return terms[:12]


def _normalize_plan(plan: dict[str, Any], what_sounds_good: str) -> dict[str, Any]:
    from app.services.dish_families import detect_dish_anchor

    plan = dict(plan)
    lower = what_sounds_good.lower()
    anchor, _ = detect_dish_anchor(what_sounds_good)
    plan["user_dish_anchor"] = bool(anchor)
    plan["dish_anchor"] = anchor

    raw_terms: list[str] = list(plan.get("search_terms") or [])
    if not raw_terms:
        for thread in plan.get("craving_threads") or []:
            raw_terms.extend(thread.get("search_terms") or [])

    search_terms: list[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        t = str(term).strip()
        if len(t) < 3 or t.lower() in seen:
            continue
        if not _term_allowed(t, lower):
            continue
        seen.add(t.lower())
        search_terms.append(t)

    if not search_terms:
        search_terms = _build_mock_search_terms(what_sounds_good.strip(), lower, plan.get("protein"))

    plan["search_terms"] = search_terms[:12]
    label = what_sounds_good.strip()[:40].title() or "Your craving"
    plan["craving_threads"] = [{
        "label": label,
        "search_terms": plan["search_terms"],
        "chef_note": f"Searches grounded in «{what_sounds_good.strip()[:60]}».",
    }]
    plan.setdefault("flavor_notes", [])
    plan.setdefault("protein_options", PROTEIN_OPTIONS)
    return plan


def mock_analyze(what_sounds_good: str, protein_filter: str | None = None) -> dict[str, Any]:
    text = what_sounds_good.strip()
    lower = text.lower()

    protein = protein_filter
    if not protein:
        for p in PROTEIN_OPTIONS:
            if p != "vegetarian" and re.search(rf"\b{re.escape(p)}\b", lower):
                protein = p
                break

    search_terms = _build_mock_search_terms(text, lower, protein)
    flavor_notes = [w for w in re.findall(r"[a-z]{4,}", lower) if w in {
        "spicy", "mild", "smoky", "tangy", "zesty", "savory", "sweet", "creamy",
        "crispy", "crunchy", "fresh", "rich", "bold", "light", "warm", "cheesy", "lemony",
    }]

    plan = {
        "chef_headline": f"Popular picks for «{text[:60]}»" if text else "What sounds good?",
        "chef_intro": (
            f"I'm searching AllRecipes for mains that match what you said"
            f"{f' — «{text[:80]}»' if text else ''}. "
            "Pick up to five favorites and I'll refine around your picks."
        ),
        "search_terms": search_terms,
        "flavor_notes": flavor_notes,
        "protein": protein,
        "protein_options": PROTEIN_OPTIONS,
        "protein_filter": protein_filter,
    }
    return _normalize_plan(plan, text)


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
        if protein_filter:
            plan["protein"] = None if protein_filter == "vegetarian" else protein_filter
            plan["protein_filter"] = protein_filter
        plan = _normalize_plan(plan, what_sounds_good)
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


def _mock_curate(
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
    limit: int = 12,
    *,
    mains_only: bool = True,
) -> list[dict[str, Any]]:
    pool = [c for c in candidates if c.get("category") not in ("side", "salad", "dip")] if mains_only else list(candidates)
    mains = [c for c in pool if c.get("category") == "main"]
    other = [c for c in pool if c not in mains]

    picked: list[dict[str, Any]] = []
    seen: set[int] = set()
    label = plan["craving_threads"][0]["label"] if plan.get("craving_threads") else "Main"

    for card in mains + other:
        if len(picked) >= limit:
            break
        if card["id"] in seen:
            continue
        c = dict(card)
        c["category"] = "main"
        c["fit_note"] = c.get("fit_note") or f"Hits your craving — {label.lower()} style worth comparing."
        c["thread_label"] = c.get("thread_label") or label
        picked.append(c)
        seen.add(card["id"])

    return picked[:limit]


async def curate_lineup(
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    selected_ids: list[int] | None = None,
    limit: int = 12,
    mains_only: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    selected_ids = selected_ids or []
    if mains_only:
        candidates = [c for c in candidates if c.get("category") not in ("side", "salad", "dip")]
    by_id = {c["id"]: c for c in candidates}

    if not settings.xai_key or not candidates:
        locked = [dict(by_id[i]) for i in selected_ids if i in by_id]
        rest = _mock_curate(
            plan,
            [c for c in candidates if c["id"] not in selected_ids],
            limit - len(locked),
            mains_only=mains_only,
        )
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
    rest = _mock_curate(
        plan,
        [c for c in candidates if c["id"] not in selected_ids],
        limit - len(locked),
        mains_only=mains_only,
    )
    return (locked + rest)[:limit], True