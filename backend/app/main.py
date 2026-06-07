import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.api import advisor_router, auth_router, cook_router, preferences_router, recipes_router, search_router
from app.config import settings, validate_production_settings
from app.database import init_db


def _static_dir() -> Path:
    app_dir = Path(__file__).resolve().parent
    for candidate in (
        app_dir.parent / "frontend" / "public",
        app_dir.parent.parent / "frontend" / "public",
        app_dir.parent.parent.parent / "frontend" / "public",
    ):
        if candidate.is_dir():
            return candidate
    return app_dir.parent.parent / "frontend" / "public"


STATIC_DIR = _static_dir()

# Bump when shipping UI changes — breaks browser cache for static assets.
APP_VERSION = os.environ.get("APP_VERSION", "20250606-grok-chef")


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_production_settings()
    await init_db()
    yield


app = FastAPI(
    title="AlchemyPantry",
    description="What are we working with? I'll show you what you can make.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

_origins = settings.cors_origin_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(preferences_router)
app.include_router(search_router)
app.include_router(recipes_router)
app.include_router(advisor_router)
app.include_router(cook_router)


def _health_payload() -> dict:
    from app.config import _spoonacular_env_name, _xai_env_name

    return {
        "status": "ok",
        "app": "alchemy-pantry",
        "version": APP_VERSION,
        "mock_mode": settings.mock_mode,
        "xai_configured": bool(settings.xai_key),
        "spoonacular_configured": bool(settings.spoonacular_key),
        "spoonacular_env": _spoonacular_env_name(),
        "xai_env": _xai_env_name(),
        "env": settings.env,
    }


def _no_cache_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }


@app.get("/health")
async def health():
    return _health_payload()


@app.get("/healthz")
async def healthz():
    return _health_payload()


if STATIC_DIR.exists():

    @app.get("/static/{asset_path:path}")
    async def static_asset(asset_path: str):
        file_path = STATIC_DIR / asset_path
        if not file_path.is_file():
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(file_path, headers=_no_cache_headers())

    @app.get("/")
    async def index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file, headers=_no_cache_headers())
        return {"message": "AlchemyPantry API"}