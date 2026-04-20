from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


DEFAULT_SOURCES = [
    "event_registry",
    "gdelt",
    "open_web",
    "x",
    "telegram",
    "guardian",
    "gnews",
    "media_cloud",
    "newsdata",
]


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    lookback_days: int = Field(default=7, ge=1, le=365)
    sources: list[str] = Field(default_factory=lambda: DEFAULT_SOURCES.copy())
    countries: list[str] = Field(default_factory=list)
    limit_per_source: int = Field(default=40, ge=10, le=200)


class SearchItemResponse(BaseModel):
    id: UUID
    provider: str
    source_type: str
    source_name: str
    source_country: str | None
    language: str | None
    title: str
    url: str
    summary: str
    pivot_summary: str
    pivot_language: str | None
    narrative: str
    emotion: str
    stance: str
    query_alignment: str
    originality: str
    weighted_score: int
    is_curated_source: bool
    analysis_method: str
    semantic_cluster: str | None
    cluster_label: str | None
    semantic_query_score: float | None = None
    source_profile: dict | None = None
    exact_quotes: list[str] = Field(default_factory=list)
    published_at: datetime
    ranking_score: int


class NarrativeGroupResponse(BaseModel):
    narrative: str
    emotion: str
    count: int
    weighted_count: float
    top_sources: list[str]


class QueryPlanResponse(BaseModel):
    original_query: str
    expanded_query: str
    keyword_query: str
    anchor_terms: list[str]
    entity_aliases: dict[str, list[str]]
    paraphrases: list[str] = Field(default_factory=list)
    multilingual_queries: dict[str, list[str]] = Field(default_factory=dict)


class ExecutiveSummaryResponse(BaseModel):
    overview: str
    main_narratives: list[str]
    cross_market_differences: list[str]
    notable_disputes: list[str]
    confidence_notes: list[str]


class ProviderStatusResponse(BaseModel):
    provider: str
    status: str
    message: str
    count: int = 0


class SearchSnapshotSummary(BaseModel):
    id: UUID
    query_text: str
    lookback_days: int
    requested_sources: list[str]
    requested_countries: list[str] = Field(default_factory=list)
    total_results: int
    status: str
    error_message: str | None = None
    created_at: datetime


class SearchResponse(BaseModel):
    snapshot: SearchSnapshotSummary
    query_plan: QueryPlanResponse
    analysis_mode: str
    provider_statuses: list[ProviderStatusResponse]
    items: list[SearchItemResponse]
    narrative_groups: list[NarrativeGroupResponse]
    executive_summary: ExecutiveSummaryResponse | None = None


class ReportQuoteResponse(BaseModel):
    topic: str
    quote: str
    source_name: str
    url: str | None = None
    source_type: str
    provider: str
    emotion: str
    stance: str | None = None
    query_alignment: str | None = None
    originality: str | None = None
    language: str | None = None
    source_country: str | None = None
    source_profile: dict | None = None


class TopicBriefResponse(BaseModel):
    topic: str
    mentions: int
    total_in_segment: int
    summary: str
    accents: list[str]
    positive_count: int
    negative_count: int
    neutral_count: int
    omitted_in_segments: list[str] = Field(default_factory=list)
    quotes: list[ReportQuoteResponse] = Field(default_factory=list)


class SegmentReportResponse(BaseModel):
    segment: str
    label: str
    item_count: int
    source_count: int
    source_examples: list[str] = Field(default_factory=list)
    source_types: list[str]
    countries: list[str]
    complementarity: str
    overview: str
    dominant_topics: list[TopicBriefResponse]
    omitted_topics: list[str] = Field(default_factory=list)


class RegistryCoverageResponse(BaseModel):
    total_items: int
    classified_items: int
    total_sources: int
    classified_sources: int
    uncovered_sources: list[str] = Field(default_factory=list)
    source_type_breakdown: dict[str, int] = Field(default_factory=dict)
    segment_breakdown: dict[str, int] = Field(default_factory=dict)
    country_breakdown: dict[str, int] = Field(default_factory=dict)
    segment_source_examples: dict[str, list[str]] = Field(default_factory=dict)
    segment_country_breakdown: dict[str, list[str]] = Field(default_factory=dict)


class SearchReportResponse(BaseModel):
    snapshot: SearchSnapshotSummary
    report_title: str
    overview: str
    registry_coverage: RegistryCoverageResponse
    segment_reports: list[SegmentReportResponse]
    cross_segment_gaps: list[str]
    key_quotes: list[ReportQuoteResponse]


class SearchSnapshotListResponse(BaseModel):
    items: list[SearchSnapshotSummary]


class TranslationPreviewRequest(BaseModel):
    text: str = Field(min_length=2, max_length=1200)
    source_language: str | None = None
    target_language: str = Field(default="ru", min_length=2, max_length=16)


class TranslationPreviewResponse(BaseModel):
    original_text: str
    translated_text: str | None = None
    source_language: str | None = None
    target_language: str
    provider: str
