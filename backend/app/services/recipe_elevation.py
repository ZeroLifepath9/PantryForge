"""Cook kit: instructor steps, elevation insights, and companion recipes."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.services.accent_side import pick_accent_side, pick_accent_side_from_allrecipes
from app.services.cooking_ai import simplify_recipe
from app.services.dish_families import detect_dish_anchor
from app.services.xai_client import chat_completion

CompanionTemplate = dict[str, Any]

ELEVATION_COMPANIONS: dict[str, list[CompanionTemplate]] = {
    "taco": [
        {
            "key": "pico",
            "title": "Quick Pico de Gallo",
            "why": "Bright acid and raw crunch cut rich taco fillings — taqueria essential.",
            "ingredients": [
                "2 Roma tomatoes, diced",
                "1/4 red onion, finely diced",
                "1 jalapeño, seeded and minced",
                "Juice of 1 lime",
                "1/4 cup cilantro, chopped",
                "Salt to taste",
            ],
            "steps": [
                {"step": 1, "text": "Dice tomatoes and onion; mince jalapeño.", "tip": "Drain excess tomato juice so pico stays crisp on tacos."},
                {"step": 2, "text": "Toss with lime juice, cilantro, and salt.", "tip": "Rest 10 minutes so lime mellows the onion bite."},
                {"step": 3, "text": "Spoon over tacos right before serving.", "tip": None},
            ],
        },
        {
            "key": "salsa_verde",
            "title": "Blistered Salsa Verde",
            "why": "Charred tomatillos add smoky tang that elevates any taco protein.",
            "ingredients": [
                "6 tomatillos, husked",
                "1 jalapeño",
                "2 garlic cloves",
                "1/4 white onion",
                "Cilantro, lime, salt",
            ],
            "steps": [
                {"step": 1, "text": "Dry-blister tomatillos, jalapeño, onion, and garlic in a hot skillet until charred.", "tip": "No oil needed — char = depth."},
                {"step": 2, "text": "Blend with cilantro, lime juice, and salt until saucy.", "tip": "Leave it slightly chunky for texture."},
                {"step": 3, "text": "Serve warm or room temp alongside tacos.", "tip": None},
            ],
        },
        {
            "key": "pickled_onions",
            "title": "Quick Pickled Red Onions",
            "why": "Pink acid crunch tames fat and heat — pro move on any taco plate.",
            "ingredients": ["1 red onion, thinly sliced", "1/2 cup vinegar", "1 tbsp sugar", "1 tsp salt", "Warm water to cover"],
            "steps": [
                {"step": 1, "text": "Slice onion paper-thin; pack into a jar.", "tip": None},
                {"step": 2, "text": "Heat vinegar, sugar, salt, and water; pour over onions.", "tip": "They are usable in 15 minutes; better after 1 hour."},
                {"step": 3, "text": "Drain lightly and pile on tacos.", "tip": None},
            ],
        },
    ],
    "pasta": [
        {
            "key": "garlic_bread",
            "title": "Skillet Garlic Bread",
            "why": "Buttery crisp bread soaks sauce — turns pasta night into a restaurant plate.",
            "ingredients": ["Baguette or ciabatta", "4 tbsp butter", "3 garlic cloves", "Parsley", "Parmesan"],
            "steps": [
                {"step": 1, "text": "Mash softened butter with minced garlic and parsley.", "tip": None},
                {"step": 2, "text": "Spread on split bread; griddle cut-side down until golden.", "tip": "Medium heat — butter burns fast."},
                {"step": 3, "text": "Finish with grated parmesan.", "tip": None},
            ],
        },
        {
            "key": "pepper_arugula",
            "title": "Lemon-Pepper Arugula",
            "why": "Peppery greens and acid cut creamy or heavy sauces.",
            "ingredients": ["Arugula", "Lemon juice", "Olive oil", "Salt", "Black pepper", "Shaved parmesan"],
            "steps": [
                {"step": 1, "text": "Toss arugula with lemon, oil, salt, and pepper.", "tip": "Dress right before serving so leaves stay perky."},
                {"step": 2, "text": "Pile beside pasta with parmesan shards.", "tip": None},
            ],
        },
    ],
    "burger": [
        {
            "key": "special_sauce",
            "title": "Burger Special Sauce",
            "why": "Creamy tang binds bun, patty, and pickles into one bite.",
            "ingredients": ["1/2 cup mayo", "2 tbsp ketchup", "1 tbsp mustard", "1 tbsp pickle brine", "Paprika"],
            "steps": [
                {"step": 1, "text": "Whisk all ingredients until smooth.", "tip": "Rest 30 minutes for flavor meld."},
                {"step": 2, "text": "Spread on both bun halves.", "tip": None},
            ],
        },
        {
            "key": "caramelized_onions",
            "title": "Caramelized Onions",
            "why": "Sweet depth balances salty beef — diner-level upgrade.",
            "ingredients": ["2 onions, sliced", "2 tbsp butter", "Salt", "Splash of water"],
            "steps": [
                {"step": 1, "text": "Cook onions in butter over medium-low 25–35 minutes, stirring.", "tip": "Add water if they stick; low heat prevents burn."},
                {"step": 2, "text": "Season and pile on burgers.", "tip": None},
            ],
        },
    ],
    "curry": [
        {
            "key": "raita",
            "title": "Cool Cucumber Raita",
            "why": "Yogurt cools spice and adds creamy contrast to bold curry.",
            "ingredients": ["1 cup yogurt", "1/2 cucumber, grated", "Cumin", "Mint", "Salt"],
            "steps": [
                {"step": 1, "text": "Drain grated cucumber; mix with yogurt and seasonings.", "tip": "Chill 20 minutes for best texture."},
                {"step": 2, "text": "Serve alongside curry and rice.", "tip": None},
            ],
        },
        {
            "key": "quick_chutney",
            "title": "Quick Mango Chutney",
            "why": "Sweet-acid pop brightens rich, spiced sauces.",
            "ingredients": ["Diced mango", "Lime", "Honey", "Red chili flakes", "Salt"],
            "steps": [
                {"step": 1, "text": "Fold mango with lime, honey, chili, and salt.", "tip": "Use frozen mango in a pinch."},
                {"step": 2, "text": "Spoon over curry or dip naan.", "tip": None},
            ],
        },
    ],
    "stir_fry": [
        {
            "key": "ginger_scallion",
            "title": "Ginger-Scallion Oil",
            "why": "Aromatic finish oil — restaurant trick over rice or noodles.",
            "ingredients": ["1/2 cup neutral oil", "Ginger, finely sliced", "Scallions, sliced", "Salt"],
            "steps": [
                {"step": 1, "text": "Heat oil to shimmering; pour over ginger and scallions in a heatproof bowl.", "tip": "Oil should sizzle — releases aroma."},
                {"step": 2, "text": "Drizzle over finished stir-fry.", "tip": None},
            ],
        },
        {
            "key": "cucumber_salad",
            "title": "Sesame Cucumber Salad",
            "why": "Cool crunch resets the palate between spicy wok bites.",
            "ingredients": ["Cucumber, sliced", "Rice vinegar", "Sesame oil", "Sesame seeds", "Salt"],
            "steps": [
                {"step": 1, "text": "Salt cucumbers 10 minutes; drain.", "tip": "Draws out water for crunch."},
                {"step": 2, "text": "Toss with vinegar, sesame oil, and seeds.", "tip": None},
            ],
        },
    ],
    "pizza": [
        {
            "key": "chili_honey",
            "title": "Chili-Honey Drizzle",
            "why": "Sweet heat on the crust edge — modern pizzeria signature.",
            "ingredients": ["3 tbsp honey", "1 tsp chili flakes", "Pinch of salt"],
            "steps": [
                {"step": 1, "text": "Warm honey with chili flakes 30 seconds.", "tip": None},
                {"step": 2, "text": "Drizzle over pizza after baking.", "tip": None},
            ],
        },
    ],
    "chili": [
        {
            "key": "cornbread",
            "title": "Skillet Cornbread",
            "why": "Sweet crumb soaks chili — classic bowl pairing.",
            "ingredients": ["Cornmeal", "Flour", "Buttermilk", "Egg", "Butter", "Honey", "Salt"],
            "steps": [
                {"step": 1, "text": "Mix batter; pour into hot buttered skillet.", "tip": "Preheated pan = crisp crust."},
                {"step": 2, "text": "Bake at 400°F until golden; brush with honey butter.", "tip": None},
            ],
        },
    ],
    "soup": [
        {
            "key": "herb_oil",
            "title": "Herb Finishing Oil",
            "why": "Fresh oil swirl adds brightness to rich broths.",
            "ingredients": ["Olive oil", "Parsley", "Lemon zest", "Garlic"],
            "steps": [
                {"step": 1, "text": "Blitz herbs, zest, and oil; season.", "tip": "Spoon on soup at the table."},
            ],
        },
    ],
}

ELEVATION_INSIGHTS: dict[str, list[dict[str, str]]] = {
    "taco": [
        {"heading": "Char your tortillas", "body": "Dry-heat corn tortillas 15 seconds per side until pliable with light char — doubles flavor."},
        {"heading": "Layer acid last", "body": "Add pico, salsa, and lime after protein so crunch and brightness stay vivid."},
        {"heading": "Double protein technique", "body": "Sear protein hard for fond, then finish with a splash of stock or beer to keep it juicy."},
    ],
    "pasta": [
        {"heading": "Finish in the pan", "body": "Toss pasta with sauce over heat, adding pasta water until glossy — emulsifies the plate."},
        {"heading": "Salt the water hard", "body": "Pasta water should taste like the sea; it's your only chance to season the noodle itself."},
    ],
    "burger": [
        {"heading": "Smash for crust", "body": "Press patty flat in a ripping-hot pan once — max crust, juicy center if you do not overwork."},
        {"heading": "Butter the bun", "body": "Toast cut sides in butter on the griddle; texture contrast is half the experience."},
    ],
    "curry": [
        {"heading": "Bloom your spices", "body": "Toast ground spices in oil 30–60 seconds before liquid — wakes up aroma."},
        {"heading": "Balance at the end", "body": "Finish with acid (lime) or fat (coconut cream) until the bowl tastes round, not flat."},
    ],
    "stir_fry": [
        {"heading": "Heat wok first", "body": "Pan must smoke slightly before oil — wok hei comes from high heat and fast movement."},
        {"heading": "Prep everything", "body": "Stir-fry waits for no one; ingredients lined up by cook order."},
    ],
    "pizza": [
        {"heading": "Hot oven, thin stretch", "body": "Less dough = crisper crust; preheat stone or steel 45+ minutes if you can."},
    ],
    "chili": [
        {"heading": "Low simmer, long time", "body": "Chili improves as spices hydrate — 45 minutes minimum for depth."},
    ],
    "soup": [
        {"heading": "Season in layers", "body": "Salt aromatics, salt after liquid, adjust at serve — builds depth without oversalting."},
    ],
}

GENERIC_INSIGHTS = [
    {"heading": "Taste as you go", "body": "Adjust salt and acid at every stage — pros fix flavor continuously, not only at the end."},
    {"heading": "Rest proteins", "body": "Let cooked meat rest 5–10 minutes before slicing so juices stay in the plate."},
    {"heading": "One bold garnish", "body": "A single fresh herb, crunch, or acid element on top signals 'restaurant' instantly."},
]

GENERIC_COMPANIONS: list[CompanionTemplate] = [
    {
        "key": "quick_pickles",
        "title": "5-Minute Quick Pickles",
        "why": "Acid crunch elevates almost any main — chef's universal upgrade.",
        "ingredients": ["Cucumber or onion, thinly sliced", "Vinegar", "Sugar", "Salt"],
        "steps": [
            {"step": 1, "text": "Cover sliced veg with hot vinegar, sugar, and salt.", "tip": None},
            {"step": 2, "text": "Use after 10 minutes as a bright topping.", "tip": None},
        ],
    },
    {
        "key": "herb_salad",
        "title": "Simple Herb Salad",
        "why": "Fresh herbs and lemon cut richness on any heavy main.",
        "ingredients": ["Parsley", "Cilantro or mint", "Lemon", "Olive oil", "Salt"],
        "steps": [
            {"step": 1, "text": "Chop herbs; dress with lemon, oil, and salt.", "tip": None},
            {"step": 2, "text": "Pile on the plate beside your main.", "tip": None},
        ],
    },
]

COOK_KIT_SYSTEM = """You are an executive chef teaching a home cook.
Given a main dish, return instructor steps PLUS elevation insights and 2-3 companion mini-recipes that take the plate to the next level (pico for tacos, salsa, finishing oils, etc.).

Output ONLY valid JSON:
{
  "elevation_insights": [{"heading": "short title", "body": "actionable pro tip"}],
  "companions": [
    {
      "key": "slug",
      "title": "Companion name",
      "why": "why this elevates the main",
      "ingredients": ["item with amount"],
      "steps": [{"step": 1, "text": "instruction", "tip": "tip or null"}]
    }
  ]
}
2-3 companions max. Each companion must be a real, cookable mini-recipe. Insights must be specific to THIS dish."""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)


def _detect_anchor(title: str, what_sounds_good: str | None) -> str | None:
    anchor, _ = detect_dish_anchor(f"{what_sounds_good or ''} {title}")
    return anchor


def _mock_companions(anchor: str | None) -> list[dict[str, Any]]:
    pool = list(ELEVATION_COMPANIONS.get(anchor or "", []))
    if len(pool) < 2:
        pool.extend(GENERIC_COMPANIONS)
    return pool[:3]


def _mock_insights(anchor: str | None, title: str) -> list[dict[str, str]]:
    specific = list(ELEVATION_INSIGHTS.get(anchor or "", []))
    if len(specific) < 2:
        specific.extend(GENERIC_INSIGHTS[: 3 - len(specific)])
    return specific[:3]


async def build_cook_kit(
    recipe_id: int,
    *,
    explain_techniques: bool = True,
    skill_level: str = "beginner",
    what_sounds_good: str | None = None,
    dish_anchor: str | None = None,
    protein_filters: list[str] | None = None,
    side_filters: list[str] | None = None,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    steps_result, steps_mock = await simplify_recipe(
        recipe_id,
        explain_techniques=explain_techniques,
        skill_level=skill_level,
        what_sounds_good=what_sounds_good,
        protein_filters=protein_filters,
        side_filters=side_filters,
        diets=diets,
        intolerances=intolerances,
        health_conditions=health_conditions,
    )
    if not steps_result:
        return None, True

    title = steps_result["title"]
    anchor = dish_anchor or _detect_anchor(title, what_sounds_good)
    plan_stub = {"dish_anchor": anchor, "pairing_cites": {}, "what_sounds_good": what_sounds_good or ""}
    accent = await pick_accent_side_from_allrecipes(
        dish_anchor=anchor,
        main_title=title,
        what_sounds_good=what_sounds_good or "",
        side_filters=side_filters,
        diets=diets,
        intolerances=intolerances,
        health_conditions=health_conditions,
        plan=plan_stub,
    )
    if not accent:
        accent = pick_accent_side(
            dish_anchor=anchor,
            side_filters=side_filters,
            diets=diets,
            intolerances=intolerances,
            health_conditions=health_conditions,
            plan=plan_stub,
        )

    if not settings.xai_key or steps_mock:
        return {
            "recipe_id": recipe_id,
            "title": title,
            "mode": steps_result["mode"],
            "steps": steps_result["steps"],
            "elevation_insights": _mock_insights(anchor, title)[:2],
            "accent_side": accent,
            "companions": [],
            "dish_anchor": anchor,
        }, True

    payload = {
        "title": title,
        "what_sounds_good": what_sounds_good,
        "dish_anchor": anchor,
        "steps": steps_result["steps"],
    }
    try:
        raw = await chat_completion(
            system=COOK_KIT_SYSTEM,
            user_content=json.dumps(payload, ensure_ascii=False),
            temperature=0.4,
        )
        data = _extract_json(raw)
        insights = data.get("elevation_insights") or _mock_insights(anchor, title)
        return {
            "recipe_id": recipe_id,
            "title": title,
            "mode": steps_result["mode"],
            "steps": steps_result["steps"],
            "elevation_insights": insights[:2],
            "accent_side": accent,
            "companions": [],
            "dish_anchor": anchor,
        }, False
    except Exception:
        return {
            "recipe_id": recipe_id,
            "title": title,
            "mode": steps_result["mode"],
            "steps": steps_result["steps"],
            "elevation_insights": _mock_insights(anchor, title)[:2],
            "accent_side": accent,
            "companions": [],
            "dish_anchor": anchor,
        }, True