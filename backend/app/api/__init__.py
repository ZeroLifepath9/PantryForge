from app.api.advisor import router as advisor_router
from app.api.auth import router as auth_router
from app.api.preferences import router as preferences_router
from app.api.search import router as search_router
from app.api.recipes import router as recipes_router

__all__ = [
    "advisor_router",
    "auth_router",
    "preferences_router",
    "search_router",
    "recipes_router",
]