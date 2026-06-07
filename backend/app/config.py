import os
import re
import secrets
import sys
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT = "dev-only-change-in-production"

# Env names users actually set on Render / local .env
SPOONACULAR_ENV_NAMES = (
    "SPOONACULAR_API_KEY",
    "SPOONACULAR_KEY",
    "SPOONACULARKEY",
    "spoonacular_API_KEY",
    "spoonacular_api_key",
    "SPOONACULAR_API",
)

XAI_ENV_NAMES = (
    "XAI_API_KEY",
    "XAI_KEY",
    "xai_API_KEY",
    "xai_api_key",
    "XAI_API",
    "GROK_API_KEY",
    "GROK_KEY",
)


def _env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _scan_env_by_pattern(pattern: re.Pattern[str]) -> tuple[str, str]:
    """Return (env_var_name, value) for first matching non-empty key."""
    for key, value in os.environ.items():
        if not value or not value.strip():
            continue
        if pattern.search(key):
            return key, value.strip()
    return "", ""


def _resolved_spoonacular_key() -> str:
    direct = _env_value(*SPOONACULAR_ENV_NAMES)
    if direct:
        return direct
    _, scanned = _scan_env_by_pattern(re.compile(r"spoonacular", re.I))
    return scanned


def _resolved_xai_key() -> str:
    direct = _env_value(*XAI_ENV_NAMES)
    if direct:
        return direct
    _, scanned = _scan_env_by_pattern(re.compile(r"(xai|grok)", re.I))
    return scanned


def _spoonacular_env_name() -> str | None:
    for name in SPOONACULAR_ENV_NAMES:
        if os.environ.get(name, "").strip():
            return name
    key, val = _scan_env_by_pattern(re.compile(r"spoonacular", re.I))
    return key if val else None


def _xai_env_name() -> str | None:
    for name in XAI_ENV_NAMES:
        if os.environ.get(name, "").strip():
            return name
    key, val = _scan_env_by_pattern(re.compile(r"(xai|grok)", re.I))
    return key if val else None


def _valid_jwt(secret: str) -> bool:
    return bool(secret) and secret != _DEV_JWT and len(secret) >= 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    env: str = Field(default="development", validation_alias="ENV")
    database_url: str = "sqlite+aiosqlite:///./pantry_forge.db"

    use_mock_data: bool = Field(default=True, validation_alias="USE_MOCK_DATA")
    spoonacular_api_key: str = Field(default="", validation_alias="SPOONACULAR_API_KEY")

    xai_api_key: str = Field(default="", validation_alias="XAI_API_KEY")
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-3-mini-fast"

    jwt_secret: str = Field(default=_DEV_JWT, validation_alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    cors_origins: str = Field(default="", validation_alias="CORS_ORIGINS")

    default_pantry_staples: str = (
        "pasta,spaghetti,olive oil,vegetable oil,cheese,parmesan,salt,pepper,garlic,onion,butter"
    )

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() in ("production", "prod")

    @property
    def spoonacular_key(self) -> str:
        return _resolved_spoonacular_key() or self.spoonacular_api_key.strip()

    @property
    def xai_key(self) -> str:
        return _resolved_xai_key() or self.xai_api_key.strip()

    @property
    def mock_mode(self) -> bool:
        """Live chef mode when XAI_API_KEY is set (AllRecipes + Grok)."""
        if self.xai_key:
            return False
        explicit = _env_value("USE_MOCK_DATA").lower()
        if explicit in ("1", "true", "yes"):
            return True
        return True

    def cors_origin_list(self) -> list[str]:
        raw = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if raw:
            return raw
        if self.is_production:
            render_url = _env_value("RENDER_EXTERNAL_URL").rstrip("/")
            if render_url:
                return [render_url]
            return []
        return ["*"]

    def pantry_staple_list(self) -> list[str]:
        return [s.strip().lower() for s in self.default_pantry_staples.split(",") if s.strip()]

    @model_validator(mode="after")
    def apply_process_env(self) -> "Settings":
        env = _env_value("ENV")
        if env:
            self.env = env
        jwt = _env_value("JWT_SECRET")
        if jwt:
            self.jwt_secret = jwt
        spoon = _resolved_spoonacular_key()
        if spoon:
            self.spoonacular_api_key = spoon
        xai = _resolved_xai_key()
        if xai:
            self.xai_api_key = xai
        db_url = _env_value("DATABASE_URL")
        if db_url:
            self.database_url = db_url
        mock = _env_value("USE_MOCK_DATA")
        if mock.lower() in ("0", "false", "no"):
            self.use_mock_data = False
        elif mock.lower() in ("1", "true", "yes"):
            self.use_mock_data = True
        return self


settings = Settings()


def validate_production_settings() -> None:
    if not settings.is_production:
        return

    jwt = _env_value("JWT_SECRET") or settings.jwt_secret
    if not _valid_jwt(jwt):
        if _env_value("RENDER") or _env_value("ENV").lower() in ("production", "prod"):
            jwt = secrets.token_urlsafe(48)
            settings.jwt_secret = jwt
            print(
                "[pantry-forge] WARNING: JWT_SECRET missing; using ephemeral secret for this deploy.",
                file=sys.stderr,
                flush=True,
            )

    if not settings.cors_origin_list():
        render_url = _env_value("RENDER_EXTERNAL_URL").rstrip("/")
        if render_url:
            settings.cors_origins = render_url

    spoon_var = _spoonacular_env_name()
    xai_var = _xai_env_name()
    print(
        f"[pantry-forge] startup: env={settings.env} mock_mode={settings.mock_mode} "
        f"spoonacular={'set' if settings.spoonacular_key else 'MISSING'}"
        f"{f' ({spoon_var})' if spoon_var else ''} "
        f"xai={'set' if settings.xai_key else 'MISSING'}"
        f"{f' ({xai_var})' if xai_var else ''}",
        flush=True,
    )
    if settings.is_production and not settings.xai_key:
        print(
            "[pantry-forge] WARNING: XAI_API_KEY not found. "
            "AllRecipes scrape works; set XAI_API_KEY for chef-judge curation and instructor steps.",
            file=sys.stderr,
            flush=True,
        )