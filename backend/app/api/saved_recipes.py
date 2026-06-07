import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_member_user
from app.models import SavedRecipe, User
from app.schemas import (
    ApprovedSubstitution,
    ChefProposal,
    SaveRecipeRequest,
    SaveRecipeResponse,
    SavedRecipeDetail,
    SavedRecipeSummary,
    SimplifiedStep,
)

router = APIRouter(prefix="/saved-recipes", tags=["saved-recipes"])


def _iso(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.isoformat()


@router.get("", response_model=list[SavedRecipeSummary])
async def list_saved_recipes(
    current_user: User = Depends(get_current_member_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedRecipe)
        .where(SavedRecipe.user_id == current_user.id)
        .order_by(SavedRecipe.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        SavedRecipeSummary(
            id=r.id,
            title=r.title,
            what_sounds_good=r.what_sounds_good,
            recipe_count=len(r.recipe_ids()),
            step_count=len(r.steps()),
            created_at=_iso(r.created_at),
        )
        for r in rows
    ]


@router.get("/{recipe_id}", response_model=SavedRecipeDetail)
async def get_saved_recipe(
    recipe_id: str,
    current_user: User = Depends(get_current_member_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedRecipe).where(
            SavedRecipe.id == recipe_id,
            SavedRecipe.user_id == current_user.id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Saved recipe not found")
    proposal_raw = row.proposal()
    proposal = ChefProposal(**proposal_raw) if proposal_raw else None
    return SavedRecipeDetail(
        id=row.id,
        title=row.title,
        what_sounds_good=row.what_sounds_good,
        recipe_ids=row.recipe_ids(),
        steps=[SimplifiedStep(**s) for s in row.steps()],
        substitutions_applied=[
            ApprovedSubstitution(**s) for s in row.substitutions()
        ],
        chef_proposal=proposal,
        created_at=_iso(row.created_at),
    )


@router.post("", response_model=SaveRecipeResponse)
async def save_recipe(
    body: SaveRecipeRequest,
    current_user: User = Depends(get_current_member_user),
    db: AsyncSession = Depends(get_db),
):
    row = SavedRecipe(
        user_id=current_user.id,
        title=body.title.strip(),
        what_sounds_good=body.what_sounds_good,
        recipe_ids_json=json.dumps(body.recipe_ids),
        steps_json=json.dumps([s.model_dump() for s in body.steps]),
        substitutions_json=json.dumps(
            [s.model_dump() for s in body.substitutions_applied]
        ),
        proposal_json=json.dumps(body.chef_proposal.model_dump())
        if body.chef_proposal
        else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SaveRecipeResponse(id=row.id)