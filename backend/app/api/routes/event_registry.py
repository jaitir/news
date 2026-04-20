from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.event_registry import (
    EventRegistryNarrativesRequest,
    EventRegistryNarrativesResponse,
    EventRegistrySearchRequest,
    EventRegistrySearchResponse,
)
from app.services.event_registry_news_service import EventRegistryNewsService
from app.services.openai_api import OpenAIAPIError

router = APIRouter(prefix="/event-registry", tags=["event-registry"])


@lru_cache
def get_event_registry_service() -> EventRegistryNewsService:
    return EventRegistryNewsService()


@router.post("/search", response_model=EventRegistrySearchResponse)
async def search_event_registry_news(
    payload: EventRegistrySearchRequest,
    service: EventRegistryNewsService = Depends(get_event_registry_service),
) -> EventRegistrySearchResponse:
    return await service.search(payload)


@router.post("/narratives", response_model=EventRegistryNarrativesResponse)
async def analyze_event_registry_narratives(
    payload: EventRegistryNarrativesRequest,
    service: EventRegistryNewsService = Depends(get_event_registry_service),
) -> EventRegistryNarrativesResponse:
    try:
        return await service.analyze_narratives(payload)
    except OpenAIAPIError as exc:
        status_code = 503 if "OPENAI_API_KEY is not configured" in str(exc) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
