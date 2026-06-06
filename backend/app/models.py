import json
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), primary_key=True
    )
    diets_json: Mapped[str] = mapped_column(Text, default="[]")
    intolerances_json: Mapped[str] = mapped_column(Text, default="[]")
    health_conditions_json: Mapped[str] = mapped_column(Text, default="[]")
    skill_level: Mapped[str] = mapped_column(String(32), default="beginner")
    explain_techniques: Mapped[bool] = mapped_column(Boolean, default=True)
    include_pantry_staples: Mapped[bool] = mapped_column(Boolean, default=True)
    pantry_staples_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def diets(self) -> list[str]:
        return json.loads(self.diets_json or "[]")

    def intolerances(self) -> list[str]:
        return json.loads(self.intolerances_json or "[]")

    def health_conditions(self) -> list[str]:
        return json.loads(self.health_conditions_json or "[]")

    def pantry_staples(self) -> list[str]:
        raw = json.loads(self.pantry_staples_json or "[]")
        return raw if raw else []