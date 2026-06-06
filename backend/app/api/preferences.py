import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserPreferences
from app.schemas import PreferencesResponse, PreferencesUpdate

router = APIRouter(prefix="/preferences", tags=["preferences"])


def _to_response(prefs: UserPreferences) -> PreferencesResponse:
    staples = prefs.pantry_staples()
    if not staples:
        staples = settings.pantry_staple_list()
    return PreferencesResponse(
        diets=prefs.diets(),
        intolerances=prefs.intolerances(),
        skill_level=prefs.skill_level,
        explain_techniques=prefs.explain_techniques,
        include_pantry_staples=prefs.include_pantry_staples,
        pantry_staples=staples,
    )


async def _get_or_create_prefs(user_id: str, db: AsyncSession) -> UserPreferences:
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    if prefs:
        return prefs
    prefs = UserPreferences(user_id=user_id)
    db.add(prefs)
    await db.commit()
    await db.refresh(prefs)
    return prefs


@router.get("/me", response_model=PreferencesResponse)
async def get_my_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await _get_or_create_prefs(current_user.id, db)
    return _to_response(prefs)


@router.put("/me", response_model=PreferencesResponse)
async def update_my_preferences(
    body: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await _get_or_create_prefs(current_user.id, db)
    if body.diets is not None:
        prefs.diets_json = json.dumps(body.diets)
    if body.intolerances is not None:
        prefs.intolerances_json = json.dumps(body.intolerances)
    if body.skill_level is not None:
        prefs.skill_level = body.skill_level
    if body.explain_techniques is not None:
        prefs.explain_techniques = body.explain_techniques
    if body.include_pantry_staples is not None:
        prefs.include_pantry_staples = body.include_pantry_staples
    if body.pantry_staples is not None:
        prefs.pantry_staples_json = json.dumps(body.pantry_staples)
    await db.commit()
    await db.refresh(prefs)
    return _to_response(prefs)