from fastapi import APIRouter, HTTPException

from app.schemas import (
    ApprovedSubstitution,
    ChefProposal,
    CreationInsight,
    InspiredCookRequest,
    InspiredCookResponse,
    InspiredIngredientItem,
    InspiredProposalRequest,
    InspiredProposalResponse,
    InspiredSetupRequest,
    InspiredSetupResponse,
    InspiredSubstitutionsRequest,
    InspiredSubstitutionsResponse,
    MixElement,
    SimplifiedStep,
    SubstitutionItem,
)
from app.services.chef_proposal import generate_chef_proposal
from app.services.inspired_cook import (
    generate_inspired_steps,
    inspired_setup,
    suggest_substitutions,
)

router = APIRouter(prefix="/cook", tags=["cook"])


@router.post("/inspired/setup", response_model=InspiredSetupResponse)
async def inspired_setup_endpoint(body: InspiredSetupRequest):
    try:
        result, is_mock = await inspired_setup(
            body.recipe_ids,
            what_sounds_good=body.what_sounds_good,
            protein=body.protein,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    insight_raw = result.get("creation_insight")
    insight = CreationInsight(**insight_raw) if insight_raw else None
    return InspiredSetupResponse(
        meal_title=result["meal_title"],
        ingredients=[InspiredIngredientItem(**i) for i in result["ingredients"]],
        recipe_titles=result.get("recipe_titles") or [],
        creation_insight=insight,
        mock=is_mock or bool(result.get("mock")),
    )


@router.post("/inspired/substitutions", response_model=InspiredSubstitutionsResponse)
async def inspired_substitutions_endpoint(body: InspiredSubstitutionsRequest):
    try:
        result, is_mock = await suggest_substitutions(
            body.recipe_ids,
            body.available_keys,
            what_sounds_good=body.what_sounds_good,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return InspiredSubstitutionsResponse(
        substitutions=[SubstitutionItem(**s) for s in result["substitutions"]],
        mock=is_mock,
    )


@router.post("/inspired/proposal", response_model=InspiredProposalResponse)
async def inspired_proposal_endpoint(body: InspiredProposalRequest):
    try:
        approved = [s.model_dump() for s in body.approved_substitutions]
        result, is_mock = await generate_chef_proposal(
            body.recipe_ids,
            body.available_keys,
            approved_substitutions=approved,
            what_sounds_good=body.what_sounds_good,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return InspiredProposalResponse(
        proposal=ChefProposal(**result),
        mock=is_mock,
    )


@router.post("/inspired/steps", response_model=InspiredCookResponse)
async def inspired_steps_endpoint(body: InspiredCookRequest):
    try:
        approved = [s.model_dump() for s in body.approved_substitutions]
        proposal = body.chef_proposal.model_dump() if body.chef_proposal else None
        result, is_mock = await generate_inspired_steps(
            body.recipe_ids,
            body.available_keys,
            approved_substitutions=approved,
            explain_techniques=body.explain_techniques,
            what_sounds_good=body.what_sounds_good,
            chef_proposal=proposal,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    proposal_raw = result.get("chef_proposal")
    return InspiredCookResponse(
        meal_title=result["meal_title"],
        steps=[SimplifiedStep(**s) for s in result["steps"]],
        substitutions_applied=[
            ApprovedSubstitution(**s) for s in result.get("substitutions_applied") or []
        ],
        chef_proposal=ChefProposal(**proposal_raw) if proposal_raw else body.chef_proposal,
        mock=is_mock,
    )