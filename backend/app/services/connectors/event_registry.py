from __future__ import annotations

import re
from dataclasses import dataclass
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse

from eventregistry import (
    ArticleInfoFlags,
    EventRegistry,
    QueryArticlesIter,
    QueryItems,
    ReturnInfo,
)

from app.core.config import get_settings
from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult
from app.services.translation_preview import get_translation_preview_service


MIN_DIVERSITY_COVERAGE = 10
DEFAULT_LANGUAGE_TARGETS = (
    "en",
    "ru",
    "ar",
    "fa",
    "tr",
    "zh",
    "es",
    "fr",
    "de",
    "hi",
    "pt",
)
TRANSLATION_TO_EVENT_REGISTRY_LANGUAGE = {
    "en": "eng",
    "ru": "rus",
    "ar": "ara",
    "fa": "fas",
    "tr": "tur",
    "zh": "zho",
    "zh-cn": "zho",
    "es": "spa",
    "fr": "fra",
    "de": "deu",
    "hi": "hin",
    "pt": "por",
    "it": "ita",
    "ja": "jpn",
    "ko": "kor",
}
COUNTRY_BY_TLD: dict[str, str] = {
    "ae": "AE",
    "am": "AM",
    "ar": "AR",
    "at": "AT",
    "au": "AU",
    "az": "AZ",
    "be": "BE",
    "bg": "BG",
    "br": "BR",
    "ca": "CA",
    "ch": "CH",
    "cl": "CL",
    "cn": "CN",
    "co.uk": "GB",
    "cz": "CZ",
    "de": "DE",
    "eg": "EG",
    "es": "ES",
    "fr": "FR",
    "ge": "GE",
    "gr": "GR",
    "hu": "HU",
    "id": "ID",
    "ie": "IE",
    "il": "IL",
    "in": "IN",
    "ir": "IR",
    "it": "IT",
    "jp": "JP",
    "kg": "KG",
    "kr": "KR",
    "kz": "KZ",
    "lt": "LT",
    "lv": "LV",
    "mx": "MX",
    "my": "MY",
    "ng": "NG",
    "nl": "NL",
    "no": "NO",
    "nz": "NZ",
    "ph": "PH",
    "pk": "PK",
    "pl": "PL",
    "pt": "PT",
    "ro": "RO",
    "ru": "RU",
    "sa": "SA",
    "se": "SE",
    "sg": "SG",
    "th": "TH",
    "tr": "TR",
    "tw": "TW",
    "ua": "UA",
    "uk": "GB",
    "us": "US",
    "uz": "UZ",
    "vn": "VN",
    "za": "ZA",
}


@dataclass(frozen=True, slots=True)
class QueryVariant:
    text: str
    language: str | None
    is_global: bool = False


class EventRegistryConnector(BaseConnector):
    provider = "event_registry"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(
        self,
        query: str,
        lookback_days: int,
        limit: int,
        *,
        sort_by: Literal["date", "relevance"] = "date",
    ) -> ConnectorResult:
        api_key = self.settings.event_registry_api_key
        if not api_key:
            return ConnectorResult(
                provider=self.provider,
                status="unconfigured",
                message="Event Registry API key is missing.",
                items=[],
            )

        er = EventRegistry(apiKey=api_key)
        query_variants = _build_query_variants(query, self.settings.query_expansion_languages)
        return_info = ReturnInfo(
            articleInfo=ArticleInfoFlags(
                bodyLen=-1,
                sentiment=True,
                socialScore=True,
                eventUri=True,
                sourceTitle=True,
                sourceLocation=True,
            )
        )

        items: list[ConnectorItem] = []
        for article in self._run_queries(
            er,
            query_variants,
            lookback_days,
            limit,
            return_info,
            sort_by=sort_by,
        ):
            source = article.get("source", {}) or {}
            body = (article.get("body") or "").strip()
            sentiment = article.get("sentiment")
            items.append(
                ConnectorItem(
                    provider=self.provider,
                    source_type="news",
                    source_name=source.get("title") or source.get("uri") or "Unknown source",
                    source_country=(source.get("location") or {}).get("country"),
                    language=article.get("lang"),
                    title=article.get("title") or "Untitled article",
                    url=article.get("url") or "",
                    summary=(body[:900] if body else article.get("title") or ""),
                    published_at=_parse_event_registry_date(article.get("dateTimePub")),
                    ranking_score=int((sentiment or 0) * 100),
                    raw_payload=article,
                )
            )

        return ConnectorResult(
            provider=self.provider,
            status="ok",
            message="Articles loaded from Event Registry.",
            items=items,
        )

    def _run_queries(
        self,
        er: EventRegistry,
        query_variants: list[QueryVariant],
        lookback_days: int,
        limit: int,
        return_info: ReturnInfo,
        *,
        sort_by: Literal["date", "relevance"],
    ) -> list[dict]:
        date_start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        date_end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        global_fetch_limit = min(max(limit * 6, 140), 600)
        localized_fetch_limit = min(max(limit * 3, 90), 240)
        strategies: list[tuple[QueryArticlesIter, int]] = []
        for variant in query_variants:
            query = variant.text
            lang = variant.language
            fetch_limit = global_fetch_limit if variant.is_global else localized_fetch_limit
            strategies.append(
                (
                QueryArticlesIter(
                    keywords=query,
                    keywordsLoc="body,title",
                    keywordSearchMode="phrase",
                    lang=lang,
                    dateStart=date_start,
                    dateEnd=date_end,
                ),
                    fetch_limit,
                ),
            )

            keyword_tokens = _extract_keywords(query)
            if len(keyword_tokens) >= 2 and (variant.is_global or lang in {"eng", "rus", "ara", "spa", "fra"}):
                strategies.append(
                    (
                        QueryArticlesIter(
                        keywords=QueryItems.AND(keyword_tokens[:4]),
                        keywordsLoc="body,title",
                        keywordSearchMode="simple",
                        lang=lang,
                        dateStart=date_start,
                        dateEnd=date_end,
                        ),
                        fetch_limit,
                    )
                )

            strategies.append(
                (
                    QueryArticlesIter(
                    keywords=query,
                    keywordsLoc="body,title",
                    keywordSearchMode="simple",
                    lang=lang,
                    dateStart=date_start,
                    dateEnd=date_end,
                    ),
                    fetch_limit,
                )
            )

        collected: list[dict] = []
        for strategy, fetch_limit in strategies:
            collected.extend(
                list(
                    strategy.execQuery(
                        er,
                        sortBy="date" if sort_by == "date" else "rel",
                        maxItems=fetch_limit,
                        returnInfo=return_info,
                    )
                )
            )

        deduped = _dedupe_articles(collected)
        sorted_articles = sorted(
            deduped,
            key=lambda article: _article_sort_key(article, sort_by),
            reverse=True,
        )
        return _diversify_articles(sorted_articles, limit, min_country_coverage=MIN_DIVERSITY_COVERAGE, min_language_coverage=MIN_DIVERSITY_COVERAGE)


def _parse_event_registry_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _extract_keywords(query: str) -> list[str]:
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "with",
        "for",
        "in",
        "on",
        "at",
        "from",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "that",
        "this",
        "as",
    }
    tokens = re.findall(r"\b[\w-]{3,}\b", query.lower())
    deduped: list[str] = []
    for token in tokens:
        if token in stopwords or token in deduped:
            continue
        deduped.append(token)
    return deduped


def _dedupe_articles(articles: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []

    for article in articles:
        key = (
            (article.get("url") or article.get("uri") or article.get("title") or "")
            .strip()
            .lower()
        )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(article)

    return deduped


def _article_sort_key(article: dict, sort_by: Literal["date", "relevance"]) -> float:
    if sort_by == "relevance":
        relevance = article.get("relevance")
        if isinstance(relevance, (int, float)):
            return float(relevance)
        weight = article.get("wgt")
        if isinstance(weight, (int, float)):
            return float(weight)
        return 0.0

    published_at = _parse_event_registry_date(article.get("dateTimePub"))
    return published_at.timestamp()


def _build_query_variants(query: str, configured_languages: list[str]) -> list[QueryVariant]:
    normalized_query = " ".join(query.split()).strip()
    if not normalized_query:
        return []

    variants = [QueryVariant(text=normalized_query, language=None, is_global=True)]
    translator = get_translation_preview_service()
    seen = {(normalized_query.lower(), None)}

    for language_code in _resolve_target_languages(configured_languages):
        translation_target = _translation_target_for(language_code)
        translated, detected_source, _ = translator.translate_preview(
            text=normalized_query,
            target_language=translation_target,
        )

        candidate_text: str | None = None
        if detected_source == translation_target:
            candidate_text = normalized_query
        elif translated:
            candidate_text = " ".join(translated.split()).strip()

        normalized_candidate = " ".join((candidate_text or "").split()).strip()
        if not normalized_candidate:
            continue

        key = (normalized_candidate.lower(), language_code)
        if key in seen:
            continue
        seen.add(key)
        variants.append(QueryVariant(text=normalized_candidate, language=language_code))

    return variants


def _diversify_articles(
    articles: list[dict],
    limit: int,
    *,
    min_country_coverage: int,
    min_language_coverage: int,
) -> list[dict]:
    remaining = list(articles)
    selected: list[dict] = []
    source_counts: Counter[str] = Counter()
    country_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    target_country_coverage = min(limit, min_country_coverage)
    target_language_coverage = min(limit, min_language_coverage)

    while remaining and len(selected) < limit:
        window = remaining[: min(500, len(remaining))]
        best_index = 0
        best_score: float | None = None

        for index, article in enumerate(window):
            base_score = max(0.0, 1200.0 - index)
            source = _article_source(article)
            country = _article_country(article)
            language = _article_language(article)

            needs_country = len(country_counts) < target_country_coverage
            needs_language = len(language_counts) < target_language_coverage
            adds_country = bool(country and country_counts[country] == 0)
            adds_language = bool(language and language_counts[language] == 0)
            adds_source = bool(source and source_counts[source] == 0)

            bonus = 0.0
            if needs_country and adds_country:
                bonus += 1800.0
            if needs_language and adds_language:
                bonus += 1700.0
            if adds_country and adds_language:
                bonus += 320.0
            if adds_source:
                bonus += 120.0
            if needs_country and not country:
                bonus -= 120.0
            if needs_language and not language:
                bonus -= 100.0

            penalty = (
                source_counts[source] * 180.0
                + country_counts[country] * 150.0
                + language_counts[language] * 140.0
            )
            score = base_score + bonus - penalty
            if best_score is None or score > best_score:
                best_score = score
                best_index = index

        chosen = remaining.pop(best_index)
        selected.append(chosen)

        source = _article_source(chosen)
        country = _article_country(chosen)
        language = _article_language(chosen)
        if source:
            source_counts[source] += 1
        if country:
            country_counts[country] += 1
        if language:
            language_counts[language] += 1

    return selected


def _resolve_target_languages(configured_languages: list[str]) -> list[str]:
    resolved: list[str] = []
    for value in [*configured_languages, *DEFAULT_LANGUAGE_TARGETS]:
        normalized = value.strip().lower()
        if not normalized:
            continue
        event_registry_code = TRANSLATION_TO_EVENT_REGISTRY_LANGUAGE.get(normalized)
        if not event_registry_code or event_registry_code in resolved:
            continue
        resolved.append(event_registry_code)
        if len(resolved) >= max(MIN_DIVERSITY_COVERAGE, len(DEFAULT_LANGUAGE_TARGETS)):
            break
    return resolved


def _translation_target_for(event_registry_language: str) -> str:
    mapping = {
        "eng": "en",
        "rus": "ru",
        "ara": "ar",
        "fas": "fa",
        "tur": "tr",
        "zho": "zh-CN",
        "spa": "es",
        "fra": "fr",
        "deu": "de",
        "hin": "hi",
        "por": "pt",
        "ita": "it",
        "jpn": "ja",
        "kor": "ko",
    }
    return mapping.get(event_registry_language, "en")


def _article_source(article: dict) -> str:
    return str(((article.get("source") or {}).get("title") or "")).strip().lower()


def _article_language(article: dict) -> str:
    return str(article.get("lang") or "").strip().lower()


def _article_country(article: dict) -> str:
    source = article.get("source") or {}
    location = source.get("location") or {}
    country = str(location.get("country") or "").strip()
    if country:
        return country.lower()

    domain = _article_domain(article)
    for suffix, code in COUNTRY_BY_TLD.items():
        if domain.endswith(f".{suffix}") or domain == suffix:
            return code.lower()
    return ""


def _article_domain(article: dict) -> str:
    parsed = urlparse(str(article.get("url") or ""))
    return parsed.netloc.replace("www.", "").lower()
