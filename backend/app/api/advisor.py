from fastapi import APIRouter

from app.config import settings
from app.schemas import AdvisorInsightsRequest, AdvisorInsightsResponse
from app.services.meal_advisor import generate_meal_insights

router = APIRouter(prefix="/advisor", tags=["advisor"])


@router.post("/insights", response_model=AdvisorInsightsResponse)
async def advisor_insights(body: AdvisorInsightsRequest):
    recipe_dicts = [r.model_dump() for r in body.recipes]
    result = await generate_meal_insights(
        ingredients=body.ingredients,
        diets=body.diets,
        intolerances=body.intolerances,
        health_conditions=body.health_conditions,
        recipes=recipe_dicts,
        what_sounds_good=body.what_sounds_good,
    )
    return AdvisorInsightsResponse(**result)


@router.get("/status")
async def advisor_status():
    return {
        "xai_configured": bool(settings.xai_api_key),
        "model": settings.xai_model if settings.xai_api_key else None,
    }