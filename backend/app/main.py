import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth_router, preferences_router, recipes_router, search_router
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_production_settings()
    await init_db()
    yield


app = FastAPI(
    title="Pantry Forge",
    description="What can I make with what I have?",
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


def _health_payload() -> dict:
    return {
        "status": "ok",
        "app": "pantry-forge",
        "mock_mode": settings.mock_mode,
        "env": settings.env,
    }


@app.get("/health")
async def health():
    return _health_payload()


@app.get("/healthz")
async def healthz():
    return _health_payload()


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Pantry Forge API"}