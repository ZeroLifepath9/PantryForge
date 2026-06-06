"""Mock recipes and search logic — no Spoonacular API calls."""

from __future__ import annotations

import re
from typing import Any

DIET_OPTIONS = [
    {"value": "vegetarian", "label": "Vegetarian"},
    {"value": "vegan", "label": "Vegan"},
    {"value": "gluten-free", "label": "Gluten free"},
    {"value": "dairy-free", "label": "Dairy free"},
    {"value": "ketogenic", "label": "Keto"},
    {"value": "paleo", "label": "Paleo"},
    {"value": "pescetarian", "label": "Pescetarian"},
]

INTOLERANCE_OPTIONS = [
    {"value": "dairy", "label": "Dairy"},
    {"value": "egg", "label": "Egg"},
    {"value": "gluten", "label": "Gluten"},
    {"value": "grain", "label": "Grain"},
    {"value": "peanut", "label": "Peanut"},
    {"value": "seafood", "label": "Seafood"},
    {"value": "sesame", "label": "Sesame"},
    {"value": "shellfish", "label": "Shellfish"},
    {"value": "soy", "label": "Soy"},
    {"value": "tree-nut", "label": "Tree nut"},
    {"value": "wheat", "label": "Wheat"},
]

HEALTH_CONDITION_OPTIONS = [
    {"value": "cardiac", "label": "Heart-healthy / cardiac"},
    {"value": "diabetes", "label": "Diabetes-friendly"},
    {"value": "low-sodium", "label": "Low sodium"},
    {"value": "low-cholesterol", "label": "Low cholesterol"},
    {"value": "renal", "label": "Kidney-friendly / renal"},
    {"value": "gerd", "label": "Acid reflux / GERD"},
    {"value": "anti-inflammatory", "label": "Anti-inflammatory"},
]

MOCK_RECIPES: list[dict[str, Any]] = [
    {
        "id": 1001,
        "title": "Basil Tomato Egg Scramble",
        "image": "https://images.unsplash.com/photo-1525351484163-7529414344d8?w=400",
        "summary": "A quick skillet scramble using eggs, fresh tomato, and basil.",
        "ready_in_minutes": 15,
        "servings": 2,
        "diets": ["vegetarian", "gluten-free"],
        "intolerance_conflicts": ["dairy", "egg"],
        "health_friendly": ["diabetes", "gerd", "anti-inflammatory"],
        "required": ["egg", "tomato", "basil", "butter", "salt", "pepper"],
        "source_url": "https://example.com/basil-tomato-egg-scramble",
        "video_url": "https://www.youtube.com/watch?v=mock-scramble",
        "instructions": [
            "Beat eggs in a bowl with a pinch of salt and pepper.",
            "Warm butter in a nonstick pan over medium heat.",
            "Add diced tomato and cook 2 minutes until softened.",
            "Pour in eggs and stir gently until just set.",
            "Fold in torn basil leaves and serve warm.",
        ],
    },
    {
        "id": 1002,
        "title": "Cheddar Basil Omelette",
        "image": "https://images.unsplash.com/photo-1510693209232-c4c4837e9917?w=400",
        "summary": "Fluffy omelette with melted cheddar and fresh basil.",
        "ready_in_minutes": 12,
        "servings": 1,
        "diets": ["vegetarian", "gluten-free"],
        "intolerance_conflicts": ["dairy", "egg"],
        "health_friendly": ["gerd"],
        "required": ["egg", "cheese", "basil", "butter", "salt"],
        "source_url": "https://example.com/cheddar-basil-omelette",
        "video_url": None,
        "instructions": [
            "Whisk eggs with a pinch of salt.",
            "Melt butter in a pan over medium-low heat.",
            "Pour eggs and let set briefly, then lift edges to let raw egg flow under.",
            "Add grated cheese and basil, fold in half, finish 1 minute.",
        ],
    },
    {
        "id": 1003,
        "title": "Simple Tomato Pasta",
        "image": "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=400",
        "summary": "Weeknight pasta with tomato, garlic, and olive oil.",
        "ready_in_minutes": 25,
        "servings": 3,
        "diets": ["vegetarian", "vegan"],
        "intolerance_conflicts": ["gluten", "wheat", "grain"],
        "health_friendly": [
            "cardiac", "diabetes", "low-cholesterol", "renal", "gerd", "anti-inflammatory",
        ],
        "required": ["pasta", "tomato", "garlic", "olive oil", "salt", "basil"],
        "source_url": "https://example.com/simple-tomato-pasta",
        "video_url": "https://www.youtube.com/watch?v=mock-pasta",
        "instructions": [
            "Boil pasta in salted water until al dente.",
            "Sauté minced garlic in olive oil until fragrant, not brown.",
            "Add chopped tomato and simmer 8 minutes.",
            "Toss drained pasta with sauce and fresh basil.",
        ],
    },
    {
        "id": 1004,
        "title": "Cheesy Garlic Pasta",
        "image": "https://images.unsplash.com/photo-1563379926898-05f4575a2d88?w=400",
        "summary": "Comfort pasta with cheese, garlic, and butter.",
        "ready_in_minutes": 20,
        "servings": 2,
        "diets": ["vegetarian"],
        "intolerance_conflicts": ["dairy", "gluten", "wheat", "grain"],
        "health_friendly": [],
        "required": ["pasta", "cheese", "garlic", "butter", "salt", "pepper"],
        "source_url": "https://example.com/cheesy-garlic-pasta",
        "video_url": None,
        "instructions": [
            "Cook pasta until al dente; reserve 1/2 cup pasta water.",
            "Melt butter, sauté garlic 30 seconds.",
            "Add pasta, cheese, and splash of pasta water; toss until creamy.",
        ],
    },
    {
        "id": 1005,
        "title": "Mushroom Onion Stir-Fry",
        "image": "https://images.unsplash.com/photo-1512058564366-7f0d4a4a409f?w=400",
        "summary": "Savory stir-fry — needs mushrooms you don't have yet.",
        "ready_in_minutes": 18,
        "servings": 2,
        "diets": ["vegan", "dairy-free", "gluten-free"],
        "intolerance_conflicts": ["soy"],
        "health_friendly": [
            "cardiac", "diabetes", "low-cholesterol", "renal", "anti-inflammatory",
        ],
        "required": ["mushroom", "onion", "garlic", "olive oil", "soy sauce", "pepper"],
        "source_url": "https://example.com/mushroom-onion-stirfry",
        "video_url": "https://www.youtube.com/watch?v=mock-stirfry",
        "instructions": [
            "Slice mushrooms and onion.",
            "Heat oil in a hot pan; add onion, cook 3 minutes.",
            "Add mushrooms and garlic; cook until browned.",
            "Splash soy sauce and pepper; serve immediately.",
        ],
    },
    {
        "id": 1006,
        "title": "Garlic Tomato Fried Rice",
        "image": "https://images.unsplash.com/photo-1603133872877-684f208fb84b?w=400",
        "summary": "Skillet rice with tomato, garlic, and a fried egg on top.",
        "ready_in_minutes": 20,
        "servings": 2,
        "diets": ["vegetarian", "gluten-free"],
        "intolerance_conflicts": ["egg"],
        "health_friendly": ["diabetes", "anti-inflammatory"],
        "required": ["rice", "tomato", "garlic", "egg", "olive oil", "soy sauce"],
        "source_url": "https://example.com/garlic-tomato-fried-rice",
        "video_url": None,
        "instructions": ["Cook rice and cool slightly.", "Sauté garlic and tomato.", "Stir-fry rice, top with fried egg."],
    },
    {
        "id": 1007,
        "title": "Lemon Herb Chicken Skillet",
        "image": "https://images.unsplash.com/photo-1598103442097-8b74394b95c6?w=400",
        "summary": "One-pan chicken with lemon, garlic, and herbs.",
        "ready_in_minutes": 30,
        "servings": 3,
        "diets": ["gluten-free", "dairy-free", "paleo"],
        "intolerance_conflicts": [],
        "health_friendly": ["cardiac", "diabetes", "low-cholesterol", "anti-inflammatory"],
        "required": ["chicken", "lemon", "garlic", "olive oil", "basil", "salt", "pepper"],
        "source_url": "https://example.com/lemon-herb-chicken",
        "video_url": None,
        "instructions": ["Season chicken.", "Sear in olive oil.", "Add lemon and herbs, finish in pan."],
    },
    {
        "id": 1008,
        "title": "White Bean Tomato Stew",
        "image": "https://images.unsplash.com/photo-1547592160-23ac45744acd?w=400",
        "summary": "Hearty beans simmered with tomato and garlic.",
        "ready_in_minutes": 35,
        "servings": 4,
        "diets": ["vegetarian", "vegan", "gluten-free", "dairy-free"],
        "intolerance_conflicts": [],
        "health_friendly": ["cardiac", "diabetes", "renal", "gerd", "anti-inflammatory", "low-cholesterol"],
        "required": ["beans", "tomato", "garlic", "onion", "olive oil", "basil"],
        "source_url": "https://example.com/white-bean-tomato-stew",
        "video_url": None,
        "instructions": ["Sauté onion and garlic.", "Add tomato and beans.", "Simmer 20 minutes, finish with basil."],
    },
    {
        "id": 1009,
        "title": "Spinach Egg Breakfast Bowl",
        "image": "https://images.unsplash.com/photo-1482049016688-2d792e49b8bd?w=400",
        "summary": "Soft eggs over wilted spinach with tomato.",
        "ready_in_minutes": 12,
        "servings": 1,
        "diets": ["vegetarian", "gluten-free", "ketogenic"],
        "intolerance_conflicts": ["egg"],
        "health_friendly": ["diabetes", "anti-inflammatory"],
        "required": ["egg", "spinach", "tomato", "olive oil", "salt", "pepper"],
        "source_url": "https://example.com/spinach-egg-bowl",
        "video_url": None,
        "instructions": ["Wilt spinach in oil.", "Add diced tomato.", "Crack eggs on top, cover until set."],
    },
    {
        "id": 1010,
        "title": "Caprese Salad Plate",
        "image": "https://images.unsplash.com/photo-1608897010294-4dd98ee472b0?w=400",
        "summary": "Fresh tomato, basil, and mozzarella with olive oil.",
        "ready_in_minutes": 10,
        "servings": 2,
        "diets": ["vegetarian", "gluten-free"],
        "intolerance_conflicts": ["dairy"],
        "health_friendly": ["cardiac", "gerd", "anti-inflammatory", "low-sodium"],
        "required": ["tomato", "basil", "cheese", "olive oil", "salt", "pepper"],
        "source_url": "https://example.com/caprese-salad",
        "video_url": None,
        "instructions": ["Slice tomato and cheese.", "Layer with basil.", "Drizzle oil, season lightly."],
    },
    {
        "id": 1011,
        "title": "Ginger Garlic Veggie Stir-Fry",
        "image": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=400",
        "summary": "Colorful vegetables in a ginger-garlic sauce.",
        "ready_in_minutes": 16,
        "servings": 2,
        "diets": ["vegan", "dairy-free", "gluten-free"],
        "intolerance_conflicts": ["soy"],
        "health_friendly": ["cardiac", "diabetes", "renal", "anti-inflammatory", "low-cholesterol"],
        "required": ["broccoli", "carrot", "onion", "garlic", "ginger", "olive oil", "soy sauce"],
        "source_url": "https://example.com/ginger-garlic-stirfry",
        "video_url": None,
        "instructions": ["Prep vegetables.", "Stir-fry aromatics.", "Add veg and sauce, cook until crisp-tender."],
    },
    {
        "id": 1012,
        "title": "Avocado Tomato Toast",
        "image": "https://images.unsplash.com/photo-1541519227359-08fa5d50c44b?w=400",
        "summary": "Mashed avocado on toast with tomato and basil.",
        "ready_in_minutes": 8,
        "servings": 1,
        "diets": ["vegetarian"],
        "intolerance_conflicts": ["gluten", "wheat", "grain"],
        "health_friendly": ["cardiac", "diabetes", "gerd", "anti-inflammatory"],
        "required": ["bread", "avocado", "tomato", "basil", "lemon", "salt", "pepper"],
        "source_url": "https://example.com/avocado-tomato-toast",
        "video_url": None,
        "instructions": ["Toast bread.", "Mash avocado with lemon.", "Top with tomato and basil."],
    },
    {
        "id": 1013,
        "title": "Tuna Tomato Pasta Salad",
        "image": "https://images.unsplash.com/photo-1473093290898-2d92aaa7700c?w=400",
        "summary": "Cold pasta with tuna, tomato, and herbs.",
        "ready_in_minutes": 22,
        "servings": 3,
        "diets": ["pescetarian", "dairy-free"],
        "intolerance_conflicts": ["gluten", "seafood", "wheat"],
        "health_friendly": ["diabetes", "low-cholesterol"],
        "required": ["pasta", "tuna", "tomato", "olive oil", "basil", "lemon"],
        "source_url": "https://example.com/tuna-tomato-pasta-salad",
        "video_url": None,
        "instructions": ["Cook and cool pasta.", "Flake tuna with tomato.", "Toss with oil, lemon, basil."],
    },
    {
        "id": 1014,
        "title": "Potato Onion Hash",
        "image": "https://images.unsplash.com/photo-1598866594230-a7c1c1f9c9f8?w=400",
        "summary": "Crispy skillet potatoes with onion and pepper.",
        "ready_in_minutes": 28,
        "servings": 3,
        "diets": ["vegan", "vegetarian", "gluten-free", "dairy-free"],
        "intolerance_conflicts": [],
        "health_friendly": ["renal", "gerd", "anti-inflammatory"],
        "required": ["potato", "onion", "olive oil", "garlic", "salt", "pepper"],
        "source_url": "https://example.com/potato-onion-hash",
        "video_url": None,
        "instructions": ["Dice potatoes small.", "Pan-fry with onion until golden.", "Season and serve hot."],
    },
    {
        "id": 1015,
        "title": "Shakshuka",
        "image": "https://images.unsplash.com/photo-1645112411341-6c4fd023314a?w=400",
        "summary": "Eggs poached in spiced tomato sauce.",
        "ready_in_minutes": 25,
        "servings": 2,
        "diets": ["vegetarian", "gluten-free"],
        "intolerance_conflicts": ["egg"],
        "health_friendly": ["diabetes", "gerd", "anti-inflammatory"],
        "required": ["egg", "tomato", "onion", "garlic", "olive oil", "cumin", "paprika"],
        "source_url": "https://example.com/shakshuka",
        "video_url": None,
        "instructions": ["Cook onion, garlic, and spices.", "Simmer tomato sauce.", "Nestle eggs, cover until set."],
    },
    {
        "id": 1016,
        "title": "Greek Yogurt Herb Dip",
        "image": "https://images.unsplash.com/photo-1623428187963-223da2d7fb48?w=400",
        "summary": "Quick dip with yogurt, garlic, and cucumber.",
        "ready_in_minutes": 8,
        "servings": 4,
        "diets": ["vegetarian", "gluten-free"],
        "intolerance_conflicts": ["dairy"],
        "health_friendly": ["cardiac", "gerd", "anti-inflammatory", "low-sodium"],
        "required": ["yogurt", "cucumber", "garlic", "lemon", "dill", "salt"],
        "source_url": "https://example.com/greek-yogurt-dip",
        "video_url": None,
        "instructions": ["Grate cucumber and drain.", "Mix with yogurt and garlic.", "Chill and serve."],
    },
    {
        "id": 1017,
        "title": "Lentil Tomato Soup",
        "image": "https://images.unsplash.com/photo-1547592160-23ac45744acd?w=400",
        "summary": "Protein-rich soup with lentils and tomato.",
        "ready_in_minutes": 40,
        "servings": 4,
        "diets": ["vegan", "vegetarian", "dairy-free", "gluten-free"],
        "intolerance_conflicts": [],
        "health_friendly": ["cardiac", "diabetes", "renal", "low-cholesterol", "anti-inflammatory"],
        "required": ["lentils", "tomato", "onion", "garlic", "carrot", "olive oil", "cumin"],
        "source_url": "https://example.com/lentil-tomato-soup",
        "video_url": None,
        "instructions": ["Sauté aromatics.", "Add lentils, tomato, water.", "Simmer until tender."],
    },
    {
        "id": 1018,
        "title": "Peanut Butter Banana Oats",
        "image": "https://images.unsplash.com/photo-1517673400267-025144a127e0?w=400",
        "summary": "Warm oats with banana and peanut butter.",
        "ready_in_minutes": 10,
        "servings": 1,
        "diets": ["vegetarian"],
        "intolerance_conflicts": ["peanut", "tree-nut"],
        "health_friendly": ["cardiac", "diabetes"],
        "required": ["oats", "banana", "peanut butter", "milk", "honey"],
        "source_url": "https://example.com/peanut-butter-banana-oats",
        "video_url": None,
        "instructions": ["Cook oats in milk.", "Slice banana on top.", "Swirl peanut butter and honey."],
    },
    {
        "id": 1019,
        "title": "Salmon Lemon Sheet Pan",
        "image": "https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=400",
        "summary": "Roasted salmon with lemon and asparagus.",
        "ready_in_minutes": 22,
        "servings": 2,
        "diets": ["pescetarian", "gluten-free", "dairy-free", "paleo"],
        "intolerance_conflicts": ["seafood"],
        "health_friendly": ["cardiac", "diabetes", "low-cholesterol", "anti-inflammatory"],
        "required": ["salmon", "lemon", "asparagus", "olive oil", "garlic", "dill"],
        "source_url": "https://example.com/salmon-lemon-sheet-pan",
        "video_url": None,
        "instructions": ["Place salmon and asparagus on pan.", "Drizzle oil, lemon, garlic.", "Roast until flaky."],
    },
    {
        "id": 1020,
        "title": "Black Bean Tacos",
        "image": "https://images.unsplash.com/photo-1565299585323-38d6b0865b47?w=400",
        "summary": "Quick tacos with seasoned black beans and tomato.",
        "ready_in_minutes": 15,
        "servings": 2,
        "diets": ["vegetarian", "vegan"],
        "intolerance_conflicts": ["gluten", "grain"],
        "health_friendly": ["diabetes", "renal", "anti-inflammatory"],
        "required": ["tortilla", "beans", "tomato", "onion", "cumin", "lime", "cilantro"],
        "source_url": "https://example.com/black-bean-tacos",
        "video_url": None,
        "instructions": ["Warm beans with cumin.", "Fill tortillas with beans and tomato.", "Squeeze lime, add cilantro."],
    },
    {
        "id": 1021,
        "title": "Cucumber Tomato Salad",
        "image": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=400",
        "summary": "Cool salad with cucumber, tomato, and red onion.",
        "ready_in_minutes": 10,
        "servings": 3,
        "diets": ["vegan", "vegetarian", "gluten-free", "dairy-free"],
        "intolerance_conflicts": [],
        "health_friendly": ["cardiac", "diabetes", "renal", "gerd", "low-sodium", "anti-inflammatory", "low-cholesterol"],
        "required": ["cucumber", "tomato", "onion", "olive oil", "vinegar", "basil"],
        "source_url": "https://example.com/cucumber-tomato-salad",
        "video_url": None,
        "instructions": ["Slice vegetables.", "Toss with oil and vinegar.", "Rest 5 minutes, add basil."],
    },
    {
        "id": 1022,
        "title": "Chicken Tomato Soup",
        "image": "https://images.unsplash.com/photo-1547592160-23ac45744acd?w=400",
        "summary": "Light soup with shredded chicken and tomato.",
        "ready_in_minutes": 35,
        "servings": 4,
        "diets": ["gluten-free", "dairy-free"],
        "intolerance_conflicts": [],
        "health_friendly": ["cardiac", "gerd", "anti-inflammatory", "low-cholesterol"],
        "required": ["chicken", "tomato", "onion", "garlic", "carrot", "celery", "basil"],
        "source_url": "https://example.com/chicken-tomato-soup",
        "video_url": None,
        "instructions": ["Simmer chicken with aromatics.", "Shred chicken, add tomato.", "Finish with basil."],
    },
    {
        "id": 1023,
        "title": "Egg Fried Noodles",
        "image": "https://images.unsplash.com/photo-1569718212165-3a8278d5f624?w=400",
        "summary": "Pan-fried noodles with egg and vegetables.",
        "ready_in_minutes": 18,
        "servings": 2,
        "diets": ["vegetarian"],
        "intolerance_conflicts": ["egg", "gluten", "soy", "wheat"],
        "health_friendly": ["diabetes"],
        "required": ["noodles", "egg", "cabbage", "carrot", "soy sauce", "garlic", "oil"],
        "source_url": "https://example.com/egg-fried-noodles",
        "video_url": None,
        "instructions": ["Cook noodles.", "Scramble egg in hot pan.", "Toss noodles, veg, and sauce."],
    },
    {
        "id": 1024,
        "title": "Stuffed Bell Peppers",
        "image": "https://images.unsplash.com/photo-1606787366850-de6330128bfc?w=400",
        "summary": "Peppers filled with rice, tomato, and herbs.",
        "ready_in_minutes": 45,
        "servings": 4,
        "diets": ["vegetarian", "gluten-free"],
        "intolerance_conflicts": [],
        "health_friendly": ["cardiac", "diabetes", "renal", "anti-inflammatory", "low-cholesterol"],
        "required": ["bell pepper", "rice", "tomato", "onion", "garlic", "cheese", "basil"],
        "source_url": "https://example.com/stuffed-bell-peppers",
        "video_url": None,
        "instructions": ["Cook rice filling with tomato.", "Stuff peppers.", "Bake until peppers soften."],
    },
    {
        "id": 1025,
        "title": "Tomato Basil Bruschetta",
        "image": "https://images.unsplash.com/photo-1572441713132-51c75654db73?w=400",
        "summary": "Toasted bread topped with fresh tomato and basil.",
        "ready_in_minutes": 12,
        "servings": 4,
        "diets": ["vegetarian", "vegan"],
        "intolerance_conflicts": ["gluten", "wheat", "grain"],
        "health_friendly": ["cardiac", "gerd", "anti-inflammatory", "low-cholesterol"],
        "required": ["bread", "tomato", "basil", "garlic", "olive oil", "balsamic"],
        "source_url": "https://example.com/tomato-basil-bruschetta",
        "video_url": None,
        "instructions": ["Dice tomato with basil and garlic.", "Toast bread.", "Spoon mixture over bread, drizzle oil."],
    },
]

MOCK_RESULT_LIMIT = 25


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _matches_ingredient(required: str, available: set[str]) -> bool:
    req = _normalize(required)
    for item in available:
        if req in item or item in req:
            return True
        # egg/eggs
        if req.rstrip("s") == item.rstrip("s"):
            return True
    return False


def mock_parse_ingredients(text: str) -> list[str]:
    """Simple mock parser — splits on commas/newlines; real AI later."""
    parts = re.split(r"[,;\n]+", text.lower())
    cleaned: list[str] = []
    for part in parts:
        part = re.sub(r"^\d+\s*", "", part.strip())
        part = re.sub(
            r"\b(some|a few|old|fresh|leftover|about|roughly)\b", "", part
        ).strip()
        if part and len(part) > 1:
            cleaned.append(part)
    return cleaned or ["egg", "tomato"]


def _recipe_matches_diets(recipe: dict[str, Any], diets: list[str]) -> bool:
    if not diets:
        return True
    recipe_diets = set(recipe.get("diets", []))
    return all(d in recipe_diets for d in diets)


def _recipe_matches_intolerances(recipe: dict[str, Any], intolerances: list[str]) -> bool:
    if not intolerances:
        return True
    conflicts = set(recipe.get("intolerance_conflicts", []))
    return not conflicts.intersection(intolerances)


def _recipe_matches_health_conditions(
    recipe: dict[str, Any], health_conditions: list[str]
) -> bool:
    if not health_conditions:
        return True
    friendly = set(recipe.get("health_friendly", []))
    return all(h in friendly for h in health_conditions)


def _classify_tier(
    missed: list[str],
    pantry: set[str],
    allow_pantry: bool,
) -> tuple[str, str]:
    if not missed:
        return "exact", "You can make this now"
    pantry_misses = [m for m in missed if _normalize(m) in pantry or any(
        _normalize(m) in _normalize(p) or _normalize(p) in _normalize(m) for p in pantry
    )]
    if allow_pantry and len(missed) == len(pantry_misses):
        return "stretch", "Add a few pantry basics"
    if len(missed) <= 3:
        return "almost", "Almost — you need a little more"
    return "almost", "Close match — missing several items"


def mock_search_recipes(
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
    default_pantry = {
        "pasta", "spaghetti", "olive oil", "vegetable oil", "cheese", "parmesan",
        "salt", "pepper", "garlic", "onion", "butter",
    }
    effective = set(user_set)
    if include_pantry_staples:
        effective |= pantry | default_pantry

    results: list[dict[str, Any]] = []
    for recipe in MOCK_RECIPES:
        if not _recipe_matches_diets(recipe, diets):
            continue
        if not _recipe_matches_intolerances(recipe, intolerances):
            continue
        if not _recipe_matches_health_conditions(recipe, health_conditions):
            continue

        required = recipe["required"]
        used: list[dict[str, str]] = []
        missed: list[dict[str, str]] = []
        unused = set(user_set)

        for req in required:
            if _matches_ingredient(req, effective):
                used.append({"name": req, "amount": None})
                for u in list(unused):
                    if _matches_ingredient(req, {u}):
                        unused.discard(u)
            elif _matches_ingredient(req, user_set):
                used.append({"name": req, "amount": None})
            else:
                missed.append({"name": req, "amount": None})

        missed_names = [m["name"] for m in missed]
        tier, label = _classify_tier(missed_names, effective, include_pantry_staples)

        # Skip recipes that need too many non-pantry items unless almost/stretch
        non_pantry_misses = [
            m for m in missed_names
            if not _matches_ingredient(m, default_pantry | pantry)
        ]
        if len(non_pantry_misses) > 4 and tier == "almost":
            continue
        if not used:
            continue

        results.append({
            "id": recipe["id"],
            "title": recipe["title"],
            "image": recipe.get("image"),
            "match_tier": tier,
            "match_label": label,
            "used_ingredients": used,
            "missed_ingredients": missed,
            "unused_ingredients": [{"name": u, "amount": None} for u in sorted(unused)],
            "diets": recipe.get("diets", []),
            "ready_in_minutes": recipe.get("ready_in_minutes"),
            "servings": recipe.get("servings"),
            "source_url": recipe.get("source_url"),
            "video_url": recipe.get("video_url"),
            "summary": recipe.get("summary"),
        })

    tier_order = {"exact": 0, "stretch": 1, "almost": 2}
    results.sort(key=lambda r: tier_order.get(r["match_tier"], 9))
    results = results[:MOCK_RESULT_LIMIT]

    message = None
    if not results:
        message = (
            "No strong matches yet. Try adding pantry staples like pasta, oil, or cheese, "
            "or broaden your diet filters."
        )
    elif not any(r["match_tier"] == "exact" for r in results):
        message = (
            "Nothing exact with only what you listed — here are the closest options "
            "and what you'd still need."
        )
    if results:
        shown = len(results)
        message = (message + " " if message else "") + f"Showing {shown} recipe{'s' if shown != 1 else ''}."

    return {
        "query_ingredients": ingredients,
        "effective_ingredients": sorted(effective),
        "results": results,
        "message": message,
    }


def mock_recipe_detail(recipe_id: int) -> dict[str, Any] | None:
    for recipe in MOCK_RECIPES:
        if recipe["id"] == recipe_id:
            return {
                "id": recipe["id"],
                "title": recipe["title"],
                "image": recipe.get("image"),
                "summary": recipe.get("summary"),
                "ready_in_minutes": recipe.get("ready_in_minutes"),
                "servings": recipe.get("servings"),
                "source_url": recipe.get("source_url"),
                "video_url": recipe.get("video_url"),
                "ingredients": [
                    {"name": r, "amount": None} for r in recipe["required"]
                ],
                "instructions": recipe["instructions"],
                "diets": recipe.get("diets", []),
            }
    return None


SIDE_KEYWORDS = ("salad", "bruschetta", "greens", "dip", "beans", "stew", "rice", "bread")
MAIN_PROTEINS = (
    "chicken", "beef", "pork", "fish", "egg", "shrimp", "salmon", "turkey", "lamb", "sausage",
)


def _mock_recipe_category(recipe: dict[str, Any]) -> str:
    title = recipe.get("title", "").lower()
    required = " ".join(recipe.get("required", [])).lower()
    if "salad" in title:
        return "salad"
    if "dip" in title or "bruschetta" in title:
        return "dip"
    if any(k in title for k in ("stew", "beans", "rice", "pasta", "spinach", "tomato pasta")):
        if not any(p in title or p in required for p in MAIN_PROTEINS):
            return "side"
    if any(p in title or p in required for p in MAIN_PROTEINS):
        return "main"
    if any(k in title for k in SIDE_KEYWORDS):
        return "side"
    return "main"


def _mock_card(recipe: dict[str, Any], category: str) -> dict[str, Any]:
    return {
        "id": recipe["id"],
        "title": recipe["title"],
        "category": category,
        "image": recipe.get("image"),
        "summary": recipe.get("summary"),
        "ready_in_minutes": recipe.get("ready_in_minutes"),
        "servings": recipe.get("servings"),
        "source_url": recipe.get("source_url"),
        "diets": recipe.get("diets", []),
    }


def mock_craving_search(
    parsed: dict[str, Any],
    *,
    diets: list[str] | None = None,
    intolerances: list[str] | None = None,
    health_conditions: list[str] | None = None,
) -> dict[str, Any]:
    diets = diets or []
    intolerances = intolerances or []
    health_conditions = health_conditions or []
    protein = (parsed.get("protein") or "").lower()
    starches = [s.lower() for s in parsed.get("starches") or []]
    terms = set(parsed.get("search_terms") or [])

    candidates: list[tuple[str, dict[str, Any], int]] = []
    for recipe in MOCK_RECIPES:
        if not _recipe_matches_diets(recipe, diets):
            continue
        if not _recipe_matches_intolerances(recipe, intolerances):
            continue
        if not _recipe_matches_health_conditions(recipe, health_conditions):
            continue
        category = _mock_recipe_category(recipe)
        title = recipe["title"].lower()
        required = " ".join(recipe.get("required", [])).lower()
        score = 0
        if protein and (protein in title or protein in required):
            score += 10
        for s in starches:
            if s.rstrip("s") in title or s.rstrip("s") in required:
                score += 4
        for t in terms:
            if t in title or t in required:
                score += 2
        if category == "main" and protein:
            score += 3
        candidates.append((category, recipe, score))

    mains_pool = [(r, s) for c, r, s in candidates if c == "main"]
    mains_pool.sort(key=lambda x: x[1], reverse=True)
    mains = [_mock_card(r, "main") for r, _ in mains_pool[:5]]

    if len(mains) < 5:
        extra = [(r, s) for c, r, s in candidates if c == "main"]
        extra.sort(key=lambda x: x[1], reverse=True)
        seen = {m["id"] for m in mains}
        for r, _ in extra:
            if r["id"] not in seen:
                mains.append(_mock_card(r, "main"))
                seen.add(r["id"])
            if len(mains) >= 5:
                break

    pair_pool = [(r, s) for c, r, s in candidates if c in ("side", "salad", "dip")]
    pair_pool.sort(key=lambda x: x[1], reverse=True)
    pairings: list[dict[str, Any]] = []
    seen_ids = {m["id"] for m in mains}
    for r, _ in pair_pool:
        if r["id"] in seen_ids:
            continue
        pairings.append(_mock_card(r, _mock_recipe_category(r)))
        seen_ids.add(r["id"])
        if len(pairings) >= 20:
            break

    message = None
    if not mains:
        message = "No main courses matched your craving — try naming a protein or starch."
    elif pairings:
        message = f"Found {len(mains)} mains and {len(pairings)} sides, salads, and dips."

    return {"mains": mains, "pairings": pairings, "message": message}


def mock_simplify_steps(
    recipe_id: int,
    *,
    explain_techniques: bool = True,
    skill_level: str = "beginner",
) -> dict[str, Any] | None:
    detail = mock_recipe_detail(recipe_id)
    if not detail:
        return None

    direct = skill_level == "direct" or not explain_techniques
    steps: list[dict[str, Any]] = []
    for i, instruction in enumerate(detail["instructions"], start=1):
        tip = None
        if not direct:
            if "sauté" in instruction.lower() or "sauté" in instruction.lower():
                tip = "Sauté means cook in a little hot fat, stirring, over medium heat."
            elif "al dente" in instruction.lower():
                tip = "Al dente means firm to the bite — not mushy."
            elif "whisk" in instruction.lower():
                tip = "Whisk means beat quickly with a fork until smooth and slightly frothy."
        steps.append({"step": i, "text": instruction, "tip": tip})

    mode = "direct" if direct else "beginner"
    return {
        "recipe_id": recipe_id,
        "title": detail["title"],
        "mode": mode,
        "steps": steps,
    }