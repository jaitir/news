export type ProviderStatus = {
  provider: string;
  status: string;
  message: string;
  count: number;
};

export type SnapshotSummary = {
  id: string;
  query_text: string;
  lookback_days: number;
  requested_sources: string[];
  requested_countries?: string[];
  total_results: number;
  status: string;
  error_message?: string | null;
  created_at: string;
};

export type SearchItem = {
  id: string;
  provider: string;
  source_type: string;
  source_name: string;
  source_country: string | null;
  language: string | null;
  title: string;
  url: string;
  summary: string;
  pivot_summary: string;
  pivot_language: string | null;
  narrative: string;
  emotion: string;
  stance: string;
  query_alignment: string;
  originality: string;
  weighted_score: number;
  is_curated_source: boolean;
  analysis_method: string;
  semantic_cluster: string | null;
  cluster_label: string | null;
  semantic_query_score?: number | null;
  source_profile?: SourceProfile | null;
  exact_quotes?: string[];
  published_at: string;
  ranking_score: number;
};

export type SourceProfile = {
  canonical_name?: string;
  country?: string | null;
  source_type?: string | null;
  state_affinity?: string | null;
  geopolitical_alignment?: string | null;
  ownership?: string | null;
  region?: string | null;
  primary_segment?: string | null;
  segment_tags?: string[] | null;
};

export type NarrativeGroup = {
  narrative: string;
  emotion: string;
  count: number;
  weighted_count: number;
  top_sources: string[];
};

export type QueryPlan = {
  original_query: string;
  expanded_query: string;
  keyword_query: string;
  anchor_terms: string[];
  entity_aliases: Record<string, string[]>;
  paraphrases: string[];
  multilingual_queries: Record<string, string[]>;
};

export type ExecutiveSummary = {
  overview: string;
  main_narratives: string[];
  cross_market_differences: string[];
  notable_disputes: string[];
  confidence_notes: string[];
};

export type SearchResponse = {
  snapshot: SnapshotSummary;
  query_plan: QueryPlan;
  analysis_mode: string;
  provider_statuses: ProviderStatus[];
  items: SearchItem[];
  narrative_groups: NarrativeGroup[];
  executive_summary: ExecutiveSummary | null;
};

export type SearchHistoryResponse = {
  items: SnapshotSummary[];
};

export type ReportQuote = {
  topic: string;
  quote: string;
  source_name: string;
  url?: string | null;
  source_type: string;
  provider: string;
  emotion: string;
  stance?: string | null;
  query_alignment?: string | null;
  originality?: string | null;
  language?: string | null;
  source_country: string | null;
  source_profile: SourceProfile | null;
};

export type TopicBrief = {
  topic: string;
  mentions: number;
  total_in_segment: number;
  summary: string;
  accents: string[];
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  omitted_in_segments: string[];
  quotes: ReportQuote[];
};

export type SegmentReport = {
  segment: string;
  label: string;
  item_count: number;
  source_count: number;
  source_examples: string[];
  source_types: string[];
  countries: string[];
  complementarity: string;
  overview: string;
  dominant_topics: TopicBrief[];
  omitted_topics: string[];
};

export type RegistryCoverage = {
  total_items: number;
  classified_items: number;
  total_sources: number;
  classified_sources: number;
  uncovered_sources: string[];
  source_type_breakdown: Record<string, number>;
  segment_breakdown: Record<string, number>;
  country_breakdown: Record<string, number>;
  segment_source_examples: Record<string, string[]>;
  segment_country_breakdown: Record<string, string[]>;
};

export type SearchReport = {
  snapshot: SnapshotSummary;
  report_title: string;
  overview: string;
  registry_coverage: RegistryCoverage;
  segment_reports: SegmentReport[];
  cross_segment_gaps: string[];
  key_quotes: ReportQuote[];
};

export type SearchPayload = {
  query: string;
  lookback_days: number;
  sources: string[];
  countries: string[];
  limit_per_source: number;
};

export type TranslationPreview = {
  original_text: string;
  translated_text: string | null;
  source_language: string | null;
  target_language: string;
  provider: string;
};

export type EventRegistrySortBy = "relevance" | "date";

export type EventRegistrySearchRequest = {
  query: string;
  lookback_days: number;
  limit: number;
  sort_by: EventRegistrySortBy;
};

export type EventRegistryArticle = {
  title: string;
  url: string;
  domain: string;
  summary: string;
  full_text: string | null;
  source_name: string;
  source_country: string | null;
  language: string | null;
  published_at: string;
  relevance_score: number | null;
  sentiment: number | null;
  tone_score: number | null;
  narrative_type: string | null;
  similarity_score: number | null;
  social_score: number | null;
  image_url: string | null;
};

export type EventRegistryCoverage = {
  total_results: number;
  unique_sources: number;
  countries: string[];
  languages: string[];
  top_sources: string[];
  average_sentiment: number | null;
  earliest_published_at: string | null;
  latest_published_at: string | null;
};

export type EventRegistrySearchResponse = {
  status: string;
  message: string;
  query: string;
  lookback_days: number;
  limit: number;
  sort_by: EventRegistrySortBy;
  executed_at: string;
  coverage: EventRegistryCoverage;
  items: EventRegistryArticle[];
};

export type EventRegistryNarrativeEvidence = {
  article_title: string;
  article_url: string;
  source_name: string | null;
  language: string | null;
  quote: string;
  quote_ru: string | null;
};

export type EventRegistryNarrative = {
  narrative: string;
  stance: "support" | "dispute" | "mixed" | "neutral";
  article_count: number;
  article_urls: string[];
  counter_to: string | null;
  geo_focus: string[];
  evidences: EventRegistryNarrativeEvidence[];
};

export type EventRegistryNarrativesRequest = {
  query: string;
  articles: Array<{
    title: string;
    url: string;
    summary: string | null;
    full_text?: string | null;
    language: string | null;
    source_name: string;
    published_at: string;
    relevance_score: number | null;
  }>;
};

export type EventRegistryNarrativesResponse = {
  status: "ok" | "error";
  model: string;
  analyzed_articles: number;
  narratives: EventRegistryNarrative[];
  message: string | null;
};
