from datetime import datetime

from pydantic import BaseModel, Field


class DeepResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)


class ResearchAnnotationResponse(BaseModel):
    title: str | None = None
    url: str
    start_index: int | None = None
    end_index: int | None = None


class ResearchSourceResponse(BaseModel):
    title: str
    url: str
    domain: str
    citation_count: int = 0


class DeepResearchResponse(BaseModel):
    id: str
    query: str | None = None
    model: str
    status: str
    answer: str | None = None
    annotations: list[ResearchAnnotationResponse] = Field(default_factory=list)
    sources: list[ResearchSourceResponse] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime | None = None
