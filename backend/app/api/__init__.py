from app.api.advisor import router as advisor_router
from app.api.auth import router as auth_router
from app.api.cook import router as cook_router
from app.api.preferences import router as preferences_router
from app.api.search import router as search_router
from app.api.recipes import router as recipes_router
from app.api.saved_recipes import router as saved_recipes_router

__all__ = [
    "advisor_router",
    "auth_router",
    "cook_router",
    "preferences_router",
    "search_router",
    "recipes_router",
    "saved_recipes_router",
]