from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EventRegistrySearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    lookback_days: int = Field(default=7, ge=1, le=360)
    limit: int = Field(default=25, ge=10, le=200)
    sort_by: Literal["relevance", "date"] = "relevance"


class EventRegistryNarrativesRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    articles: list["EventRegistryArticleInput"] = Field(min_length=3, max_length=200)


class EventRegistryArticleInput(BaseModel):
    title: str
    url: str
    summary: str | None = None
    full_text: str | None = None
    language: str | None = None
    source_name: str | None = None
    published_at: datetime | None = None
    relevance_score: float | None = None


class EventRegistryArticleResponse(BaseModel):
    title: str
    url: str
    domain: str
    summary: str
    full_text: str | None = None
    source_name: str
    source_country: str | None = None
    language: str | None = None
    published_at: datetime
    relevance_score: float | None = None
    sentiment: float | None = None
    tone_score: int | None = None
    narrative_type: str | None = None
    similarity_score: float | None = None
    social_score: float | None = None
    image_url: str | None = None


class EventRegistryCoverageResponse(BaseModel):
    total_results: int
    unique_sources: int
    countries: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    top_sources: list[str] = Field(default_factory=list)
    average_sentiment: float | None = None
    earliest_published_at: datetime | None = None
    latest_published_at: datetime | None = None


class EventRegistrySearchResponse(BaseModel):
    status: str
    message: str
    query: str
    lookback_days: int
    limit: int
    sort_by: Literal["relevance", "date"]
    executed_at: datetime
    coverage: EventRegistryCoverageResponse
    items: list[EventRegistryArticleResponse]


class NarrativeEvidenceResponse(BaseModel):
    article_title: str
    article_url: str
    source_name: str | None = None
    language: str | None = None
    quote: str
    quote_ru: str | None = None


class NarrativeResponse(BaseModel):
    narrative: str
    stance: Literal["support", "dispute", "mixed", "neutral"] = "neutral"
    article_count: int = 0
    article_urls: list[str] = Field(default_factory=list)
    evidences: list[NarrativeEvidenceResponse] = Field(default_factory=list)


class EventRegistryNarrativesResponse(BaseModel):
    status: Literal["ok", "error"] = "ok"
    model: str
    analyzed_articles: int = 0
    narratives: list[NarrativeResponse] = Field(default_factory=list)
    message: str | None = None
