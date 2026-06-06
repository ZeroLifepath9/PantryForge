import os
import secrets
import sys
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT = "dev-only-change-in-production"


def _env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _resolved_spoonacular_key() -> str:
    return _env_value(
        "SPOONACULAR_API_KEY",
        "spoonacular_API_KEY",
        "SPOONACULAR_KEY",
    )


def _resolved_xai_key() -> str:
    return _env_value(
        "XAI_API_KEY",
        "xai_API_KEY",
        "XAI_KEY",
    )


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
        return _resolved_spoonacular_key() or self.spoonacular_api_key

    @property
    def xai_key(self) -> str:
        return _resolved_xai_key() or self.xai_api_key

    @property
    def mock_mode(self) -> bool:
        explicit = _env_value("USE_MOCK_DATA").lower()
        if explicit in ("0", "false", "no"):
            return False
        # Live APIs when keys are present (even if USE_MOCK_DATA defaulted true).
        if self.spoonacular_key or self.xai_key:
            return False
        if explicit in ("1", "true", "yes"):
            return True
        return self.use_mock_data

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

    print(
        f"[pantry-forge] startup: env={settings.env} mock_mode={settings.mock_mode} "
        f"spoonacular={'set' if settings.spoonacular_key else 'off'} "
        f"xai={'set' if settings.xai_key else 'off'}",
        flush=True,
    )