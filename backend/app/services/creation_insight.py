"""Grok insight: mix selected dishes into a scratch-the-urge inspired meal."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.recipe_search import get_recipe_detail
from app.services.xai_client import chat_completion

INSIGHT_SYSTEM = """You are briefing a competition chef before they pitch the judge.
The judge selected inspiration dishes — the chef will NOT copy them, but steal ideas to scratch one urge at home.

Output ONLY valid JSON:
{
  "headline": "short title for the inspire dash",
  "urge_summary": "1-2 sentences on the craving these picks unlock",
  "fusion_idea": "one paragraph: how a contestant would fuse these ideas into one original plate",
  "mix_elements": [
    {
      "from_recipe": "recipe title from selection",
      "borrow": "technique, flavor, or component to steal",
      "use_it": "how the chef uses it in a scratch version"
    }
  ],
  "scratch_meal": "2-3 sentences previewing the dish the chef will pitch once pantry is known"
}

Be practical. Reference the protein when given. Competition energy, still warm and home-kitchen realistic."""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _mock_insight(
    *,
    recipe_titles: list[str],
    protein: str | None,
    what_sounds_good: str | None,
) -> dict[str, Any]:
    protein_note = f" featuring {protein}" if protein else ""
    titles = recipe_titles[:4]
    mix = []
    for title in titles:
        borrow = "cooking method and seasoning approach"
        if "salad" in title.lower():
            borrow = "fresh acid and herbs for contrast"
        elif "soup" in title.lower() or "stew" in title.lower():
            borrow = "simmered base and aromatics"
        elif "skillet" in title.lower() or "pan" in title.lower():
            borrow = "high-heat sear and pan sauce"
        mix.append({
            "from_recipe": title,
            "borrow": borrow,
            "use_it": f"Lift the {borrow} into your scratch plate — same vibe, your proportions.",
        })

    scratch = (
        f"Build one plate{protein_note}: cook the protein using the boldest technique from your mains, "
        f"then add a side element borrowed from the salads or sides you picked. "
        "Season once at the end so flavors stay clear."
    )
    if what_sounds_good:
        scratch += f" Aim for what you described: {what_sounds_good[:120]}."

    return {
        "headline": "Scratch the urge — your way",
        "urge_summary": (
            f"You wanted something{protein_note} — these picks show different ways to hit that same craving."
            if protein
            else "These picks share a flavor thread — mix their best parts into something yours."
        ),
        "fusion_idea": (
            f"Don't cook all {len(titles)} recipes separately. Take the protein prep from one main, "
            "the brightness from any salad, and the comfort element from a side or starch dish. "
            "Plate them as one composed meal or fold into a single bowl — you're chasing the feeling, not the photo."
        ),
        "mix_elements": mix[:5],
        "scratch_meal": scratch,
    }


async def generate_creation_insight(
    recipe_ids: list[int],
    *,
    what_sounds_good: str | None = None,
    protein: str | None = None,
) -> tuple[dict[str, Any], bool]:
    recipes = []
    for rid in recipe_ids:
        detail, _ = await get_recipe_detail(rid)
        if detail:
            recipes.append(detail)

    if not recipes:
        raise ValueError("No recipes found for selection")

    titles = [r["title"] for r in recipes]
    if not settings.xai_key:
        return _mock_insight(
            recipe_titles=titles,
            protein=protein,
            what_sounds_good=what_sounds_good,
        ), True

    payload = {
        "what_sounds_good": what_sounds_good,
        "protein": protein,
        "selected": [
            {
                "title": r["title"],
                "summary": (r.get("summary") or "")[:300],
                "ingredients": [i.get("name") for i in (r.get("ingredients") or [])[:12]],
            }
            for r in recipes
        ],
    }
    try:
        text = await chat_completion(
            system=INSIGHT_SYSTEM,
            user_content=json.dumps(payload, ensure_ascii=False),
            temperature=0.55,
        )
        raw = _extract_json(text)
        mix = raw.get("mix_elements") or []
        return {
            "headline": str(raw.get("headline") or "Your inspired mix"),
            "urge_summary": str(raw.get("urge_summary") or ""),
            "fusion_idea": str(raw.get("fusion_idea") or ""),
            "mix_elements": [
                {
                    "from_recipe": str(m.get("from_recipe") or ""),
                    "borrow": str(m.get("borrow") or ""),
                    "use_it": str(m.get("use_it") or ""),
                }
                for m in mix
                if m.get("from_recipe")
            ],
            "scratch_meal": str(raw.get("scratch_meal") or ""),
        }, False
    except Exception:
        return _mock_insight(
            recipe_titles=titles,
            protein=protein,
            what_sounds_good=what_sounds_good,
        ), True