from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.deep_research import DeepResearchRequest, DeepResearchResponse
from app.services.deep_research_service import DeepResearchService
from app.services.openai_api import OpenAIAPIError

router = APIRouter(prefix="/deep-research", tags=["deep-research"])


@lru_cache
def get_deep_research_service() -> DeepResearchService:
    return DeepResearchService()


@router.post("", response_model=DeepResearchResponse)
async def create_deep_research(
    payload: DeepResearchRequest,
    service: DeepResearchService = Depends(get_deep_research_service),
) -> DeepResearchResponse:
    try:
        return await service.create(payload)
    except OpenAIAPIError as exc:
        status_code = 503 if "OPENAI_API_KEY is not configured" in str(exc) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/{response_id}", response_model=DeepResearchResponse)
async def get_deep_research(
    response_id: str,
    service: DeepResearchService = Depends(get_deep_research_service),
) -> DeepResearchResponse:
    try:
        return await service.get(response_id)
    except OpenAIAPIError as exc:
        status_code = 503 if "OPENAI_API_KEY is not configured" in str(exc) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
