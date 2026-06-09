from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from sqlalchemy import text

    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.execute(
                text(
                    "ALTER TABLE user_preferences "
                    "ADD COLUMN health_conditions_json TEXT DEFAULT '[]'"
                )
            )
        except Exception:
            pass
        for col, default in [
            ("flavor_profile_json", "'{}'"),
            ("craving_history_json", "'[]'"),
        ]:
            try:
                await conn.execute(
                    text(
                        f"ALTER TABLE user_preferences "
                        f"ADD COLUMN {col} TEXT DEFAULT {default}"
                    )
                )
            except Exception:
                pass  # column exists or other error, tolerant for sqlite dev/prod