from functools import lru_cache

from pydantic import Field
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.curated_sources import DEFAULT_TELEGRAM_CURATED_CHANNELS, DEFAULT_X_CURATED_ACCOUNTS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    project_name: str = "Global Media Intelligence"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://media_aggregator:media_aggregator@localhost:5432/media_aggregator"
    backend_cors_origins_raw: str = Field(default="http://localhost:3000", alias="BACKEND_CORS_ORIGINS")
    enable_demo_data: bool = True
    event_registry_api_key: str | None = None
    x_bearer_token: str | None = None
    telegram_api_id: str | None = None
    telegram_api_hash: str | None = None
    telegram_session_string: str | None = None
    telegram_use_global_search: bool = True
    telegram_allow_paid_stars: int = 0
    telegram_curated_channels_raw: str = Field(default="", alias="TELEGRAM_CURATED_CHANNELS")
    guardian_open_platform_key: str | None = None
    gnews_api_key: str | None = None
    media_cloud_api_key: str | None = None
    newsdata_api_key: str | None = None
    x_curated_accounts_raw: str = Field(default="", alias="X_CURATED_ACCOUNTS")
    enable_pivot_translation: bool = True
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    analysis_mode: str = "hybrid"
    openai_enable_query_expansion: bool = True
    openai_query_expansion_model: str = "gpt-5.4-mini"
    query_expansion_languages_raw: str = Field(default="en,ru,ar,fa,tr,zh,es,fr,de,hi,pt", alias="QUERY_EXPANSION_LANGUAGES")
    openai_enrichment_model: str = "gpt-5.4-mini"
    openai_synthesis_model: str = "gpt-5.4"
    openai_deep_research_model: str = "gpt-5.4-pro"
    openai_deep_research_reasoning_effort: str = "high"
    openai_deep_research_max_tool_calls: int = 24
    openai_embedding_model: str = "text-embedding-3-large"
    event_registry_narrative_model: str = "gpt-5.4-mini"
    event_registry_narrative_max_articles: int = 40
    event_registry_narrative_fetch_timeout_seconds: int = 12
    event_registry_narrative_fetch_concurrency: int = 4
    event_registry_narrative_soft_max_article_chars: int = 120000
    event_registry_narrative_soft_max_total_chars: int = 900000
    openai_llm_item_limit: int = 0
    openai_batch_chunk_size: int = 6
    openai_enrichment_concurrency: int = 4
    openai_enable_synthesis: bool = True
    openai_enable_semantic_clustering: bool = True
    openai_enable_semantic_reranking: bool = True
    openai_embedding_dimensions: int | None = 1024
    search_query_expansion_timeout_seconds: int = 60
    search_connector_timeout_seconds: int = 120
    search_llm_timeout_seconds: int = 900
    ollama_enabled: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:27b"
    ollama_timeout_seconds: int = 120
    ollama_enable_quote_review: bool = True
    translation_preview_enabled: bool = True
    translation_preview_provider: str = "mymemory"
    translation_preview_endpoint: str | None = None
    translation_preview_api_key: str | None = None
    translation_preview_cache_ttl_seconds: int = 86400
    report_docx_template_path: str | None = Field(default=None, alias="REPORT_DOCX_TEMPLATE_PATH")

    @computed_field
    @property
    def backend_cors_origins(self) -> list[str]:
        return [item.strip() for item in self.backend_cors_origins_raw.split(",") if item.strip()]

    @computed_field
    @property
    def telegram_curated_channels(self) -> list[str]:
        if self.telegram_curated_channels_raw.strip():
            return [item.strip().lower().lstrip("@") for item in self.telegram_curated_channels_raw.split(",") if item.strip()]
        return DEFAULT_TELEGRAM_CURATED_CHANNELS.copy()

    @computed_field
    @property
    def x_curated_accounts(self) -> list[str]:
        if self.x_curated_accounts_raw.strip():
            return [item.strip().lower().lstrip("@") for item in self.x_curated_accounts_raw.split(",") if item.strip()]
        return [item.lower().lstrip("@") for item in DEFAULT_X_CURATED_ACCOUNTS]

    @computed_field
    @property
    def query_expansion_languages(self) -> list[str]:
        values = [item.strip().lower() for item in self.query_expansion_languages_raw.split(",") if item.strip()]
        return values or ["en", "ru", "ar", "fa", "tr", "zh", "es", "fr", "de", "hi", "pt"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
