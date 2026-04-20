from __future__ import annotations

import asyncio
import html
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.services.analytics import infer_emotion_score, infer_stance_to_query
from app.services.query_planner import build_search_plan
from app.schemas.event_registry import (
    EventRegistryArticleInput,
    EventRegistryArticleResponse,
    EventRegistryCoverageResponse,
    EventRegistryNarrativesRequest,
    EventRegistryNarrativesResponse,
    EventRegistrySearchRequest,
    EventRegistrySearchResponse,
    NarrativeEvidenceResponse,
    NarrativeResponse,
)
from app.services.connectors.event_registry import EventRegistryConnector
from app.services.openai_api import OpenAIAPIClient

COUNTRY_BY_TLD: dict[str, str] = {
    "ae": "AE",
    "am": "AM",
    "az": "AZ",
    "ca": "CA",
    "cn": "CN",
    "co.uk": "GB",
    "de": "DE",
    "fr": "FR",
    "ge": "GE",
    "il": "IL",
    "in": "IN",
    "ir": "IR",
    "it": "IT",
    "jp": "JP",
    "kg": "KG",
    "kz": "KZ",
    "pl": "PL",
    "ru": "RU",
    "tr": "TR",
    "ua": "UA",
    "uk": "GB",
    "us": "US",
    "uz": "UZ",
}


class EventRegistryNewsService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.connector = EventRegistryConnector()
        self.openai = OpenAIAPIClient()

    async def search(self, payload: EventRegistrySearchRequest) -> EventRegistrySearchResponse:
        search_plan = build_search_plan(payload.query)
        result = await self.connector.search(
            payload.query,
            payload.lookback_days,
            payload.limit,
            sort_by=payload.sort_by,
        )

        items = [
            EventRegistryArticleResponse(
                title=item.title,
                url=item.url,
                domain=_read_domain(item.url),
                summary=item.summary,
                full_text=_read_full_text(item.raw_payload.get("body")),
                source_name=item.source_name,
                source_country=_read_country(item.source_country, item.url),
                language=item.language,
                published_at=item.published_at,
                relevance_score=_read_numeric(item.raw_payload.get("relevance")),
                sentiment=_read_numeric(item.raw_payload.get("sentiment")),
                tone_score=_derive_tone_score(
                    title=item.title,
                    summary=item.summary,
                    sentiment=_read_numeric(item.raw_payload.get("sentiment")),
                ),
                narrative_type=_derive_narrative_type(
                    title=item.title,
                    summary=item.summary,
                    search_plan=search_plan,
                ),
                similarity_score=_read_numeric(item.raw_payload.get("sim")),
                social_score=_read_numeric(item.raw_payload.get("socialScore")),
                image_url=_read_image_url(item.raw_payload.get("image")),
            )
            for item in result.items
        ]

        return EventRegistrySearchResponse(
            status=result.status,
            message=result.message,
            query=payload.query,
            lookback_days=payload.lookback_days,
            limit=payload.limit,
            sort_by=payload.sort_by,
            executed_at=datetime.now(timezone.utc),
            coverage=_build_coverage(items),
            items=items,
        )

    async def analyze_narratives(self, payload: EventRegistryNarrativesRequest) -> EventRegistryNarrativesResponse:
        selected_articles = _select_articles_for_narratives(
            payload.articles,
            limit=max(5, self.settings.event_registry_narrative_max_articles),
        )
        if not selected_articles:
            return EventRegistryNarrativesResponse(
                status="error",
                model=self.settings.event_registry_narrative_model,
                analyzed_articles=0,
                narratives=[],
                message="Недостаточно данных для AI-аналитики.",
            )

        selected_articles = await self._fill_missing_article_texts(selected_articles)
        user_prompt = _build_narrative_prompt(payload.query, selected_articles)
        model_output = await self.openai.chat_json(
            model=self.settings.event_registry_narrative_model,
            system_prompt=NARRATIVE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema_name="event_registry_narratives",
            schema=NARRATIVE_SCHEMA,
        )
        narratives = _parse_narrative_rows(model_output)
        return EventRegistryNarrativesResponse(
            status="ok",
            model=self.settings.event_registry_narrative_model,
            analyzed_articles=len(selected_articles),
            narratives=narratives,
            message=None if narratives else "AI не выявил устойчивых нарративов по текущей выборке.",
        )

    async def _fill_missing_article_texts(
        self,
        articles: list[EventRegistryArticleInput],
    ) -> list[EventRegistryArticleInput]:
        timeout_seconds = max(self.settings.event_registry_narrative_fetch_timeout_seconds, 3)
        concurrency = max(self.settings.event_registry_narrative_fetch_concurrency, 1)
        semaphore = asyncio.Semaphore(concurrency)
        timeout = httpx.Timeout(timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            tasks = [
                self._enrich_article_text(article, client=client, semaphore=semaphore)
                for article in articles
            ]
            return await asyncio.gather(*tasks)

    async def _enrich_article_text(
        self,
        article: EventRegistryArticleInput,
        *,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
    ) -> EventRegistryArticleInput:
        if article.full_text and article.full_text.strip():
            return article

        fetched_text: str | None = None
        async with semaphore:
            try:
                response = await client.get(
                    article.url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (compatible; MediaAggregatorBot/1.0; +https://localhost)"
                        )
                    },
                )
                if response.status_code < 400 and "text/html" in response.headers.get("content-type", ""):
                    fetched_text = _extract_main_text_from_html(response.text)
            except Exception:
                fetched_text = None

        if fetched_text:
            return article.model_copy(update={"full_text": fetched_text})
        return article


NARRATIVE_SYSTEM_PROMPT = """
You are a senior geopolitical media analyst specializing in the South Caucasus region.
Identify recurring narratives in multilingual news coverage, with analytical priority given
to narratives that are geopolitically significant for Azerbaijan.

Prioritization rules
- HIGH PRIORITY: narratives touching Azerbaijan's territorial integrity, energy/transit corridors,
  relations with Armenia/Russia/Turkey/Iran/EU/US, normalization process, diaspora, international
  recognition, or hybrid warfare / information operations.
- LOW PRIORITY: surface-level, ceremonial, or purely domestic human-interest narratives.
  Include LOW only if needed to reach minimum narrative count.
- Return narratives sorted by priority: HIGH first, LOW last.

Output rules
- Narrative labels: concise (max 10 words), neutral, de-duplicated, written in Russian.
- Capture both supporting AND disputing narratives where present.
- Use ONLY the provided article snippets and metadata.
- Evidence quotes must be exact substrings from provided snippets.
- If quote is not in Russian, keep original in quote and provide a Russian translation in quote_ru.
- For each narrative include one evidence quote per article listed in article_urls.
- Return 5-10 narratives (fewer only if source material is genuinely sparse).

Counter-narrative rule
- For every HIGH PRIORITY narrative, attempt to identify a counter-narrative present in the
  source material.
- If found, add it as a separate narrative object with counter_to equal to primary narrative label.
- If no counter-narrative is found in the sources, omit counter_to.

Geographic attribution
- For each narrative include geo_focus as array of countries or regions
  (e.g. Azerbaijan, Armenia, EU, Russia, South Caucasus) based on snippets and metadata.
""".strip()


NARRATIVE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["narratives"],
    "properties": {
        "narratives": {
            "type": "array",
            "minItems": 0,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "narrative",
                    "stance",
                    "article_count",
                    "counter_to",
                    "article_urls",
                    "geo_focus",
                    "evidences",
                ],
                "properties": {
                    "narrative": {"type": "string", "minLength": 3, "maxLength": 180},
                    "stance": {
                        "type": "string",
                        "enum": ["support", "dispute", "mixed", "neutral"],
                    },
                    "article_count": {"type": "integer", "minimum": 1, "maximum": 200},
                    "counter_to": {"type": ["string", "null"], "maxLength": 180},
                    "article_urls": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 200,
                        "items": {"type": "string", "minLength": 3, "maxLength": 2000},
                    },
                    "geo_focus": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 10,
                        "items": {"type": "string", "minLength": 2, "maxLength": 80},
                    },
                    "evidences": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 200,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "article_title",
                                "article_url",
                                "source_name",
                                "language",
                                "quote",
                                "quote_ru",
                            ],
                            "properties": {
                                "article_title": {"type": "string", "minLength": 1, "maxLength": 400},
                                "article_url": {"type": "string", "minLength": 3, "maxLength": 2000},
                                "source_name": {"type": ["string", "null"], "maxLength": 240},
                                "language": {"type": ["string", "null"], "maxLength": 20},
                                "quote": {"type": "string", "minLength": 10, "maxLength": 1200},
                                "quote_ru": {"type": ["string", "null"], "maxLength": 1200},
                            },
                        },
                    },
                },
            },
        }
    },
}


def _build_coverage(items: list[EventRegistryArticleResponse]) -> EventRegistryCoverageResponse:
    sentiments = [item.sentiment for item in items if item.sentiment is not None]
    published = [item.published_at for item in items]
    source_counts = Counter(item.source_name for item in items if item.source_name)

    return EventRegistryCoverageResponse(
        total_results=len(items),
        unique_sources=len({item.source_name for item in items if item.source_name}),
        countries=sorted({item.source_country for item in items if item.source_country}),
        languages=sorted({item.language for item in items if item.language}),
        top_sources=[name for name, _ in source_counts.most_common(8)],
        average_sentiment=round(sum(sentiments) / len(sentiments), 3) if sentiments else None,
        earliest_published_at=min(published) if published else None,
        latest_published_at=max(published) if published else None,
    )


def _read_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.replace("www.", "") or "unknown"


def _read_numeric(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _read_image_url(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _read_full_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip()
    if not text:
        return None
    return text


def _read_country(value: str | None, url: str) -> str | None:
    if value:
        return value.upper() if len(value) <= 3 else value

    domain = _read_domain(url)
    for suffix, country in COUNTRY_BY_TLD.items():
        if domain.endswith(f".{suffix}") or domain == suffix:
            return country
    return None


def _derive_tone_score(*, title: str, summary: str, sentiment: float | None) -> int:
    heuristic_score = infer_emotion_score(title, summary)

    if sentiment is not None:
        api_score = max(-100, min(100, round(sentiment * 100)))
        if abs(api_score) >= 12:
            return api_score

        blended_score = round(api_score * 0.65 + heuristic_score * 0.35)
        if blended_score == 0 and heuristic_score != 0:
            return 8 if heuristic_score > 0 else -8
        return max(-100, min(100, blended_score))

    return heuristic_score


def _derive_narrative_type(*, title: str, summary: str, search_plan) -> str:
    analysis_text = f"{title} {summary}".lower()
    stance = infer_stance_to_query(analysis_text, search_plan)
    if stance == "supports":
        return "support"
    if stance == "disputes":
        return "dispute"
    if stance == "mixed":
        return "mixed"
    return "analysis"


def _select_articles_for_narratives(
    articles: list[EventRegistryArticleInput],
    *,
    limit: int,
) -> list[EventRegistryArticleInput]:
    deduped: list[EventRegistryArticleInput] = []
    seen: set[str] = set()
    ranked = sorted(
        articles,
        key=lambda item: item.relevance_score if item.relevance_score is not None else -1e9,
        reverse=True,
    )
    for row in ranked:
        key = row.url.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= limit:
            break
    return deduped


def _build_narrative_prompt(query: str, articles: list[EventRegistryArticleInput]) -> str:
    chunks: list[str] = [f"Query: {query}", "", "Articles:"]
    total_chars_used = 0
    soft_max_total_chars = max(get_settings().event_registry_narrative_soft_max_total_chars, 120000)
    soft_max_article_chars = max(get_settings().event_registry_narrative_soft_max_article_chars, 20000)
    for index, article in enumerate(articles, start=1):
        text_payload = (article.full_text or article.summary or "").strip()
        snippet = _apply_soft_safeguard(
            text_payload=text_payload,
            soft_max_article_chars=soft_max_article_chars,
            soft_max_total_chars=max(0, soft_max_total_chars - total_chars_used),
        )
        total_chars_used += len(snippet)
        chunks.extend(
            [
                f"[{index}] title: {article.title}",
                f"[{index}] url: {article.url}",
                f"[{index}] source_name: {article.source_name or 'unknown'}",
                f"[{index}] language: {article.language or 'unknown'}",
                f"[{index}] published_at: {article.published_at.isoformat() if article.published_at else 'unknown'}",
                f"[{index}] relevance: {article.relevance_score if article.relevance_score is not None else 'n/a'}",
                f"[{index}] text_snippet: {snippet or article.title}",
                "",
            ]
        )
    return "\n".join(chunks)


def _parse_narrative_rows(payload: dict) -> list[NarrativeResponse]:
    rows = payload.get("narratives")
    if not isinstance(rows, list):
        return []

    parsed: list[NarrativeResponse] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        evidence_rows = row.get("evidences")
        if not isinstance(evidence_rows, list):
            evidence_rows = []
        evidences: list[NarrativeEvidenceResponse] = []
        for evidence in evidence_rows:
            if not isinstance(evidence, dict):
                continue
            article_url = str(evidence.get("article_url") or "").strip()
            article_title = str(evidence.get("article_title") or "").strip()
            quote = str(evidence.get("quote") or "").strip()
            if not article_url or not article_title or not quote:
                continue
            evidences.append(
                NarrativeEvidenceResponse(
                    article_url=article_url,
                    article_title=article_title,
                    source_name=_optional_text(evidence.get("source_name")),
                    language=_optional_text(evidence.get("language")),
                    quote=quote,
                    quote_ru=_optional_text(evidence.get("quote_ru")),
                )
            )
        narrative = str(row.get("narrative") or "").strip()
        article_count = row.get("article_count")
        raw_urls = row.get("article_urls")
        article_urls = _normalize_url_list(raw_urls)
        if not article_urls:
            article_urls = list({evidence.article_url for evidence in evidences if evidence.article_url})
        geo_focus = _normalize_string_list(row.get("geo_focus"), limit=10)

        if not narrative or not evidences or not isinstance(article_count, int) or article_count <= 0:
            continue
        stance = str(row.get("stance") or "neutral").strip()
        if stance not in {"support", "dispute", "mixed", "neutral"}:
            stance = "neutral"
        parsed.append(
            NarrativeResponse(
                narrative=narrative,
                stance=stance,
                article_count=max(article_count, len(article_urls)),
                article_urls=article_urls,
                counter_to=_optional_text(row.get("counter_to")),
                geo_focus=geo_focus,
                evidences=evidences,
            )
        )
    parsed.sort(key=lambda item: item.article_count, reverse=True)
    return parsed


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _normalize_url_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        url = item.strip()
        if not url:
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(url)
    return normalized


def _normalize_string_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _extract_main_text_from_html(raw_html: str) -> str | None:
    if not raw_html:
        return None
    cleaned = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw_html)
    cleaned = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", cleaned)
    cleaned = re.sub(r"(?is)<svg[^>]*>.*?</svg>", " ", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 600:
        return None
    return cleaned


def _apply_soft_safeguard(
    *,
    text_payload: str,
    soft_max_article_chars: int,
    soft_max_total_chars: int,
) -> str:
    if not text_payload:
        return ""
    candidate = text_payload
    if len(candidate) > soft_max_article_chars:
        head_size = int(soft_max_article_chars * 0.7)
        tail_size = max(soft_max_article_chars - head_size, 0)
        candidate = (
            f"{candidate[:head_size]}\n\n[...soft-truncated...]\n\n{candidate[-tail_size:]}"
            if tail_size
            else candidate[:soft_max_article_chars]
        )
    if soft_max_total_chars <= 0:
        return ""
    if len(candidate) > soft_max_total_chars:
        if soft_max_total_chars < 2000:
            return candidate[:soft_max_total_chars]
        head_size = int(soft_max_total_chars * 0.75)
        tail_size = soft_max_total_chars - head_size
        return f"{candidate[:head_size]}\n\n[...context-budget-truncated...]\n\n{candidate[-tail_size:]}"
    return candidate
