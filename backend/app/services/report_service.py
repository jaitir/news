from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from math import ceil
from typing import Any

from app.core.config import get_settings
from app.core.countries import normalize_country_label_ru
from app.core.source_registry import resolve_source_profile
from app.schemas.search import (
    RegistryCoverageResponse,
    ReportQuoteResponse,
    SearchReportResponse,
    SearchResponse,
    SegmentReportResponse,
    TopicBriefResponse,
)
from app.services.openai_api import OpenAIAPIClient, OpenAIAPIError
from app.services.ollama_api import OllamaAPIClient, OllamaAPIError


SEGMENT_LABELS = {
    "state_aligned": "Проправительственные",
    "critical_non_state": "Оппозиционные / независимые / прозападные",
    "opposition": "Оппозиционные",
    "independent": "Независимые",
    "western_aligned": "Прозападные",
    "unknown": "Не классифицировано",
}

SOURCE_TYPE_LABELS = {
    "news": "digital_media",
    "telegram": "telegram",
    "social": "x",
}

TOPIC_LABELS_RU = {
    "general framing": "Основной контекст",
    "diplomatic": "Дипломатия",
    "economic": "Экономика",
    "security": "Безопасность",
    "governance": "Госуправление",
    "social reaction": "Общественная реакция",
    "u.s.-mexico policy dispute": "Спор по политике США и Мексики",
    "markets and dollar": "Рынки и доллар",
    "tariff restoration": "Восстановление пошлин",
    "trade tariffs": "Торговые пошлины",
}

EMOTION_LABELS_RU = {
    "positive": "позитивный",
    "negative": "негативный",
    "neutral": "нейтральный",
}

STANCE_LABELS_RU = {
    "supports": "поддерживает",
    "disputes": "оспаривает",
    "mixed": "смешанная",
    "unclear": "неясная",
}

REPORT_SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "overview": {"type": "string"},
        "cross_segment_gaps": {"type": "array", "items": {"type": "string"}},
        "segment_summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "segment": {"type": "string"},
                    "overview": {"type": "string"},
                    "complementarity": {"type": "string"},
                    "topic_briefs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "topic": {"type": "string"},
                                "summary": {"type": "string"},
                                "accents": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["topic", "summary", "accents"],
                        },
                    },
                },
                "required": ["segment", "overview", "complementarity", "topic_briefs"],
            },
        },
    },
    "required": ["overview", "cross_segment_gaps", "segment_summaries"],
}

REPORT_QUOTE_SELECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "segment_topics": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "segment": {"type": "string"},
                    "topics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "topic": {"type": "string"},
                                "candidate_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["topic", "candidate_ids"],
                        },
                    },
                },
                "required": ["segment", "topics"],
            },
        }
    },
    "required": ["segment_topics"],
}

LOCAL_GAP_REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "cross_segment_gaps": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["cross_segment_gaps"],
}


async def build_search_report(search: SearchResponse) -> SearchReportResponse:
    items = [_refresh_report_item(item.model_dump()) for item in search.items]
    registry_coverage = _build_registry_coverage(items)
    segment_items = _bucket_items_by_segment(items)
    global_topics = _topic_mentions(items)

    segment_reports: list[SegmentReportResponse] = []
    for segment in ["state_aligned", "critical_non_state", "opposition", "independent", "western_aligned", "unknown"]:
        rows = segment_items.get(segment, [])
        if not rows:
            continue
        segment_reports.append(
            SegmentReportResponse(
                segment=segment,
                label=SEGMENT_LABELS.get(segment, segment),
                item_count=len(rows),
                source_count=len({row["source_name"] for row in rows}),
                source_examples=list(dict.fromkeys(row["source_name"] for row in rows))[:8],
                source_types=sorted({_report_source_type(row) for row in rows}),
                countries=sorted(
                    {
                        country
                        for country in (country for row in rows for country in _normalized_country_values(row))
                        if country
                    }
                ),
                complementarity=_complementarity(rows),
                overview=_heuristic_segment_overview(rows),
                dominant_topics=_build_topic_briefs(rows, global_topics),
                omitted_topics=_find_omitted_topics(rows, global_topics),
            )
        )

    quote_refinement_task = asyncio.create_task(_maybe_refine_topic_quotes(search, segment_reports, segment_items))
    synthesis_task = asyncio.create_task(_maybe_synthesize_report(search, segment_reports, registry_coverage))

    try:
        segment_reports = await quote_refinement_task
    except Exception:
        pass
    key_quotes = _build_key_quotes(segment_reports)
    overview = _heuristic_overview(search, registry_coverage, segment_reports)
    cross_segment_gaps = _cross_segment_gaps(segment_reports)

    try:
        synthesis = await synthesis_task
    except Exception:
        synthesis = None
    if synthesis:
        overview = synthesis.get("overview") or overview
        cross_segment_gaps = synthesis.get("cross_segment_gaps") or cross_segment_gaps
        segment_reports = _merge_synthesis(segment_reports, synthesis.get("segment_summaries") or [])

    try:
        cross_segment_gaps = await _maybe_local_refine_cross_segment_gaps(
            search,
            segment_reports,
            cross_segment_gaps,
        )
    except Exception:
        pass

    return SearchReportResponse(
        snapshot=search.snapshot,
        report_title=_report_title(search, items),
        overview=overview,
        registry_coverage=registry_coverage,
        segment_reports=segment_reports,
        cross_segment_gaps=cross_segment_gaps,
        key_quotes=key_quotes,
    )


async def _maybe_local_refine_cross_segment_gaps(
    search: SearchResponse,
    segment_reports: list[SegmentReportResponse],
    cross_segment_gaps: list[str],
) -> list[str]:
    settings = get_settings()
    if not (settings.ollama_enabled and cross_segment_gaps):
        return cross_segment_gaps

    try:
        client = OllamaAPIClient()
        if not client.is_configured:
            return cross_segment_gaps
    except Exception:
        return cross_segment_gaps

    compact_segments = [
        {
            "segment": report.segment,
            "label": report.label,
            "omitted_topics": report.omitted_topics,
            "dominant_topics": [topic.topic for topic in report.dominant_topics[:4]],
        }
        for report in segment_reports
    ]

    try:
        payload = await client.chat_json(
            model=settings.ollama_model,
            system_prompt=(
                "Ты редактор аналитического отчета по медиа. Переформулируй пробелы покрытия по-русски кратко и ясно. "
                "Используй только уже вычисленные omitted_topics и темы сегментов. Не придумывай новых тем."
            ),
            user_prompt=(
                "{\n"
                f'  "query": {search.query_plan.original_query!r},\n'
                f'  "segments": {compact_segments!r},\n'
                f'  "current_cross_segment_gaps": {cross_segment_gaps!r}\n'
                "}"
            ),
            schema=LOCAL_GAP_REVIEW_SCHEMA,
        )
    except (OllamaAPIError, RuntimeError, ValueError):
        return cross_segment_gaps

    revised = [str(row).strip() for row in payload.get("cross_segment_gaps", []) if str(row).strip()]
    return revised[:8] or cross_segment_gaps


def _refresh_report_item(item: dict) -> dict:
    if item.get("source_profile"):
        return item
    refreshed = resolve_source_profile(
        source_name=item.get("source_name"),
        url=item.get("url"),
        country_hint=item.get("source_country"),
    )
    if refreshed:
        item["source_profile"] = refreshed
    return item


def _build_registry_coverage(items: list[dict]) -> RegistryCoverageResponse:
    profiles = [item.get("source_profile") for item in items if item.get("source_profile")]
    classified_sources = {profile["canonical_name"] for profile in profiles}
    source_type_breakdown = Counter(_report_source_type(item) for item in items)
    segment_breakdown = Counter(
        (item.get("source_profile") or {}).get("primary_segment", "unknown") for item in items
    )
    country_breakdown = Counter(
        country
        for country in (country for item in items for country in _normalized_country_values(item))
        if country
    )

    uncovered_sources = sorted(
        {
            item["source_name"]
            for item in items
            if not item.get("source_profile")
        }
    )[:20]
    segment_source_examples: dict[str, list[str]] = {}
    segment_country_breakdown: dict[str, list[str]] = {}
    grouped_sources: dict[str, set[str]] = defaultdict(set)
    grouped_countries: dict[str, set[str]] = defaultdict(set)
    for item in items:
        profile = item.get("source_profile") or {}
        segment = profile.get("primary_segment", "unknown")
        grouped_sources[segment].add(item["source_name"])
        for country in _normalized_country_values(item):
            grouped_countries[segment].add(country)

    for segment, names in grouped_sources.items():
        segment_source_examples[segment] = sorted(names)[:12]
    for segment, countries in grouped_countries.items():
        segment_country_breakdown[segment] = sorted(countries)

    return RegistryCoverageResponse(
        total_items=len(items),
        classified_items=len(profiles),
        total_sources=len({item["source_name"] for item in items}),
        classified_sources=len(classified_sources),
        uncovered_sources=uncovered_sources,
        source_type_breakdown=dict(source_type_breakdown),
        segment_breakdown=dict(segment_breakdown),
        country_breakdown=dict(country_breakdown),
        segment_source_examples=segment_source_examples,
        segment_country_breakdown=segment_country_breakdown,
    )


def _bucket_items_by_segment(items: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        profile = item.get("source_profile") or {}
        primary = profile.get("primary_segment", "unknown")
        buckets[primary].append(item)
        tags = set(profile.get("segment_tags") or [])
        if primary in {"opposition", "independent", "western_aligned"} or "critical_non_state" in tags:
            buckets["critical_non_state"].append(item)
    return buckets


def _topic_mentions(items: list[dict]) -> Counter[str]:
    return Counter((item.get("cluster_label") or item.get("narrative") or "general framing") for item in items)


def _build_topic_briefs(items: list[dict], global_topics: Counter[str]) -> list[TopicBriefResponse]:
    topics: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        topics[item.get("cluster_label") or item.get("narrative") or "general framing"].append(item)

    briefs: list[TopicBriefResponse] = []
    total_in_segment = len(items)
    for topic, rows in sorted(
        topics.items(),
        key=lambda pair: (
            sum(row.get("weighted_score", 0) for row in pair[1]),
            len(pair[1]),
        ),
        reverse=True,
    )[:4]:
        positive_count = sum(1 for row in rows if row.get("emotion") == "positive")
        negative_count = sum(1 for row in rows if row.get("emotion") == "negative")
        neutral_count = sum(1 for row in rows if row.get("emotion") == "neutral")
        briefs.append(
            TopicBriefResponse(
                topic=topic,
                mentions=len(rows),
                total_in_segment=total_in_segment,
                summary=_heuristic_topic_summary(rows),
                accents=_topic_accents(rows),
                positive_count=positive_count,
                negative_count=negative_count,
                neutral_count=neutral_count,
                omitted_in_segments=[],
                quotes=_topic_quotes(topic, rows),
            )
        )

    overall_top_topics = [
        topic
        for topic, count in global_topics.most_common(6)
        if count >= 2
    ]
    for brief in briefs:
        brief.omitted_in_segments = [
            label
            for label in overall_top_topics
            if label != brief.topic and label not in {b.topic for b in briefs}
        ][:3]
    return briefs


def _heuristic_topic_summary(rows: list[dict]) -> str:
    lead = rows[0]
    sources = ", ".join(dict.fromkeys(row["source_name"] for row in rows[:3]))
    return f"{lead['pivot_summary'][:220]} Источники с наибольшим вкладом: {sources}."


def _topic_accents(rows: list[dict]) -> list[str]:
    accents: list[str] = []
    countries = [
        country
        for country in (country for row in rows for country in _normalized_country_values(row))
        if country
    ]
    if countries:
        top_country = Counter(countries).most_common(1)[0][0]
        accents.append(f"Наиболее заметна подача из {top_country}.")

    emotions = Counter(row.get("emotion", "neutral") for row in rows)
    if emotions:
        dominant_emotion, count = emotions.most_common(1)[0]
        accents.append(f"Преобладающий тон: {_emotion_label_ru(dominant_emotion)} ({count}).")

    stances = Counter(row.get("stance", "unclear") for row in rows)
    if stances:
        dominant_stance, count = stances.most_common(1)[0]
        accents.append(f"Преобладающая позиция: {_stance_label_ru(dominant_stance)} ({count}).")
    return accents[:3]


def _topic_quotes(topic: str, rows: list[dict]) -> list[ReportQuoteResponse]:
    quotes: list[ReportQuoteResponse] = []
    seen_sources: set[str] = set()
    for row in sorted(rows, key=lambda item: item.get("weighted_score", 0), reverse=True):
        if row["source_name"] in seen_sources:
            continue
        quote_candidates = row.get("exact_quotes", []) or [_quote_excerpt(row)]
        for quote in quote_candidates:
            if not _quote_quality_ok(quote):
                continue
            quotes.append(
                ReportQuoteResponse(
                    topic=topic,
                    quote=quote,
                    source_name=row["source_name"],
                    url=row.get("url"),
                    source_type=_report_source_type(row),
                    provider=row["provider"],
                    emotion=row["emotion"],
                    stance=row.get("stance"),
                    query_alignment=row.get("query_alignment"),
                    originality=row.get("originality"),
                    language=row.get("language"),
                    source_country=next(iter(_normalized_country_values(row)), None),
                    source_profile=row.get("source_profile"),
                )
            )
            seen_sources.add(row["source_name"])
            break
        if len(quotes) >= 5:
            break
    return quotes


def _find_omitted_topics(items: list[dict], global_topics: Counter[str]) -> list[str]:
    present_topics = {item.get("cluster_label") or item.get("narrative") or "general framing" for item in items}
    total_mentions = sum(global_topics.values()) or 1
    threshold = max(3, ceil(total_mentions * 0.08))
    return [
        topic
        for topic, count in global_topics.most_common(8)
        if count >= threshold and topic not in present_topics
    ][:4]


def _complementarity(rows: list[dict]) -> str:
    positive = sum(1 for row in rows if row.get("emotion") == "positive")
    negative = sum(1 for row in rows if row.get("emotion") == "negative")
    if positive >= negative * 1.35 and positive >= 2:
        return "комплиментарная"
    if negative >= positive * 1.35 and negative >= 2:
        return "критическая"
    if positive == 0 and negative == 0:
        return "нейтральная"
    return "смешанная"


def _heuristic_segment_overview(rows: list[dict]) -> str:
    topics = Counter(row.get("cluster_label") or row.get("narrative") or "general framing" for row in rows)
    top_topics = ", ".join(_topic_label_ru(topic) for topic, _ in topics.most_common(3))
    if not top_topics:
        return "Выраженных тематических паттернов пока не выявлено."
    return f"Наиболее обсуждаемые темы: {top_topics}."


def _topic_label_ru(topic: str) -> str:
    normalized = str(topic or "").strip().lower()
    return TOPIC_LABELS_RU.get(normalized, str(topic))


def _emotion_label_ru(value: str) -> str:
    return EMOTION_LABELS_RU.get(str(value or "").strip().lower(), str(value))


def _stance_label_ru(value: str) -> str:
    return STANCE_LABELS_RU.get(str(value or "").strip().lower(), str(value))


def _report_title(search: SearchResponse, items: list[dict]) -> str:
    countries = sorted(
        {
            country
            for country in (country for item in items for country in _normalized_country_values(item))
            if country
        }
    )
    geography = ", ".join(countries[:3]) if countries else "глобальных медиа"
    return f"Реакция медиа {geography} на {search.query_plan.original_query}"


def _normalized_country_values(item: dict) -> list[str]:
    profile = item.get("source_profile") or {}
    profile_country = normalize_country_label_ru(profile.get("country"))
    if profile_country:
        return [profile_country]
    raw_country = item.get("source_country")
    if not raw_country:
        return []
    values = []
    for chunk in str(raw_country).split(","):
        normalized = normalize_country_label_ru(chunk)
        if normalized and normalized not in values:
            values.append(normalized)
    return values


def _heuristic_overview(
    search: SearchResponse,
    coverage: RegistryCoverageResponse,
    segment_reports: list[SegmentReportResponse],
) -> str:
    source_types = ", ".join(
        f"{source_type}: {count}"
        for source_type, count in sorted(coverage.source_type_breakdown.items())
    )
    segments = ", ".join(
        f"{report.label} — {report.item_count}"
        for report in segment_reports[:4]
    )
    return (
        f"По инфоповоду «{search.query_plan.original_query}» проанализировано {search.snapshot.total_results} материалов. "
        f"Классификация источников покрывает {coverage.classified_items}/{coverage.total_items} материалов. "
        f"Типы источников: {source_types}. Сегменты медиа: {segments}."
    )


def _cross_segment_gaps(segment_reports: list[SegmentReportResponse]) -> list[str]:
    gaps: list[str] = []
    for report in segment_reports:
        if report.omitted_topics:
            gaps.append(f"{report.label}: мало или нет внимания к темам — {', '.join(report.omitted_topics)}.")
    return gaps[:8]


def _build_key_quotes(segment_reports: list[SegmentReportResponse]) -> list[ReportQuoteResponse]:
    quotes: list[ReportQuoteResponse] = []
    seen: set[tuple[str, str]] = set()
    for report in segment_reports:
        for topic in report.dominant_topics:
            for quote in topic.quotes:
                fingerprint = (quote.source_name, quote.quote)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                quotes.append(quote)
    return quotes[:16]


async def _maybe_refine_topic_quotes(
    search: SearchResponse,
    segment_reports: list[SegmentReportResponse],
    segment_items: dict[str, list[dict]],
) -> list[SegmentReportResponse]:
    settings = get_settings()
    candidate_map: dict[str, ReportQuoteResponse] = {}
    request_segments: list[dict[str, Any]] = []

    for report in segment_reports:
        topic_rows: dict[str, list[dict]] = defaultdict(list)
        for row in segment_items.get(report.segment, []):
            topic_label = row.get("cluster_label") or row.get("narrative") or "general framing"
            topic_rows[topic_label].append(row)

        request_topics: list[dict[str, Any]] = []
        for topic in report.dominant_topics:
            rows = sorted(
                topic_rows.get(topic.topic, []),
                key=lambda item: item.get("weighted_score", 0),
                reverse=True,
            )[:6]
            topic_candidates: list[dict[str, Any]] = []
            source_candidate_counts: Counter[str] = Counter()
            for row in rows:
                for quote in _quote_candidates_for_llm(row):
                    if source_candidate_counts[row["source_name"]] >= 2:
                        continue
                    candidate_id = f"{report.segment}:{topic.topic}:{len(candidate_map) + 1}"
                    response_row = ReportQuoteResponse(
                        topic=topic.topic,
                        quote=quote,
                        source_name=row["source_name"],
                        url=row.get("url"),
                        source_type=_report_source_type(row),
                        provider=row["provider"],
                        emotion=row["emotion"],
                        stance=row.get("stance"),
                        query_alignment=row.get("query_alignment"),
                        originality=row.get("originality"),
                        language=row.get("language"),
                        source_country=next(iter(_normalized_country_values(row)), None),
                        source_profile=row.get("source_profile"),
                    )
                    candidate_map[candidate_id] = response_row
                    topic_candidates.append(
                        {
                            "candidate_id": candidate_id,
                            "source_name": row["source_name"],
                            "title": row.get("title"),
                            "pivot_summary": row.get("pivot_summary"),
                            "quote": quote,
                            "emotion": row.get("emotion"),
                            "stance": row.get("stance"),
                            "query_alignment": row.get("query_alignment"),
                            "originality": row.get("originality"),
                        }
                    )
                    source_candidate_counts[row["source_name"]] += 1
                    if len(topic_candidates) >= 10:
                        break
                if len(topic_candidates) >= 10:
                    break

            if topic_candidates:
                request_topics.append(
                    {
                        "topic": topic.topic,
                        "summary": topic.summary,
                        "candidates": topic_candidates,
                    }
                )

        if request_topics:
            request_segments.append(
                {
                    "segment": report.segment,
                    "label": report.label,
                    "topics": request_topics,
                }
            )

    if not request_segments:
        return segment_reports

    payload = await _quote_selection_payload(search, request_segments)
    if not payload:
        return segment_reports

    selected_ids_by_topic: dict[tuple[str, str], list[str]] = {}
    for row in payload.get("segment_topics", []):
        segment = row.get("segment")
        for topic in row.get("topics", []):
            topic_label = topic.get("topic")
            candidate_ids = [
                candidate_id
                for candidate_id in topic.get("candidate_ids", [])
                if candidate_id in candidate_map
            ][:3]
            if segment and topic_label and candidate_ids:
                selected_ids_by_topic[(segment, topic_label)] = candidate_ids

    merged_reports: list[SegmentReportResponse] = []
    for report in segment_reports:
        merged_topics: list[TopicBriefResponse] = []
        for topic in report.dominant_topics:
            selected_ids = selected_ids_by_topic.get((report.segment, topic.topic), [])
            selected_quotes = [candidate_map[candidate_id] for candidate_id in selected_ids]
            merged_topics.append(
                TopicBriefResponse(
                    **{
                        **topic.model_dump(),
                        "quotes": selected_quotes or topic.quotes,
                    }
                )
            )
        merged_reports.append(
            SegmentReportResponse(
                **{
                    **report.model_dump(),
                    "dominant_topics": merged_topics,
                }
            )
        )
    return merged_reports


async def _quote_selection_payload(search: SearchResponse, request_segments: list[dict[str, Any]]) -> dict[str, Any] | None:
    settings = get_settings()
    user_prompt = (
        "{\n"
        f'  "query": {search.query_plan.original_query!r},\n'
        f'  "segment_topics": {request_segments!r}\n'
        "}"
    )
    system_prompt = (
        "Ты редактор media-intelligence отчета. Для каждой темы выбери до 3 лучших candidate_id. "
        "Нужны цитаты или фрагменты, которые прямо иллюстрируют связь материала с инфоповодом и темой. "
        "Избегай протокольных фраз, общих приветствий, пустых дипломатических любезностей, "
        "однословных оценок и фрагментов без содержательной связи с запросом."
    )

    if settings.ollama_enabled and settings.ollama_enable_quote_review:
        try:
            local_client = OllamaAPIClient()
            if local_client.is_configured:
                local_payload = await local_client.chat_json(
                    model=settings.ollama_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=REPORT_QUOTE_SELECTION_SCHEMA,
                )
                if settings.openai_api_key:
                    narrowed_segments = _narrow_quote_request_segments(request_segments, local_payload)
                    if narrowed_segments:
                        request_segments = narrowed_segments
                        user_prompt = (
                            "{\n"
                            f'  "query": {search.query_plan.original_query!r},\n'
                            f'  "segment_topics": {request_segments!r}\n'
                            "}"
                        )
                else:
                    return local_payload
        except (OllamaAPIError, RuntimeError, ValueError):
            pass

    if not settings.openai_api_key:
        return None

    try:
        client = OpenAIAPIClient()
        if not client.is_configured:
            return None
    except Exception:
        return None

    try:
        return await client.chat_json(
            model=settings.openai_enrichment_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name="report_quote_selection",
            schema=REPORT_QUOTE_SELECTION_SCHEMA,
        )
    except (OpenAIAPIError, RuntimeError, ValueError):
        return None


def _narrow_quote_request_segments(
    request_segments: list[dict[str, Any]],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_by_topic: dict[tuple[str, str], set[str]] = {}
    for row in payload.get("segment_topics", []):
        segment = row.get("segment")
        for topic in row.get("topics", []):
            topic_label = topic.get("topic")
            candidate_ids = set(topic.get("candidate_ids", [])[:4])
            if segment and topic_label and candidate_ids:
                selected_by_topic[(segment, topic_label)] = candidate_ids

    if not selected_by_topic:
        return request_segments

    narrowed: list[dict[str, Any]] = []
    for segment_row in request_segments:
        narrowed_topics: list[dict[str, Any]] = []
        segment = segment_row.get("segment")
        for topic_row in segment_row.get("topics", []):
            topic_label = topic_row.get("topic")
            selected_ids = selected_by_topic.get((segment, topic_label))
            candidates = topic_row.get("candidates", [])
            if selected_ids:
                candidates = [candidate for candidate in candidates if candidate.get("candidate_id") in selected_ids]
            narrowed_topics.append(
                {
                    **topic_row,
                    "candidates": candidates[:6],
                }
            )
        narrowed.append({**segment_row, "topics": narrowed_topics})
    return narrowed


def _report_source_type(item: dict) -> str:
    if item.get("provider") == "telegram":
        return "telegram"
    if item.get("provider") == "x":
        return "x"
    return SOURCE_TYPE_LABELS.get(item.get("source_type") or "news", item.get("source_type") or "news")


async def _maybe_synthesize_report(
    search: SearchResponse,
    segment_reports: list[SegmentReportResponse],
    coverage: RegistryCoverageResponse,
) -> dict[str, Any] | None:
    if not segment_reports:
        return None

    settings = get_settings()
    if not settings.openai_enable_synthesis:
        return None

    try:
        client = OpenAIAPIClient()
        if not client.is_configured:
            return None
    except Exception:
        return None

    compact_segments = [
        {
            "segment": report.segment,
            "label": report.label,
            "item_count": report.item_count,
            "source_count": report.source_count,
            "complementarity": report.complementarity,
            "omitted_topics": report.omitted_topics,
            "topics": [
                {
                    "topic": topic.topic,
                    "mentions": topic.mentions,
                    "summary": topic.summary,
                    "accents": topic.accents,
                }
                for topic in report.dominant_topics[:4]
            ],
        }
        for report in segment_reports
    ]

    try:
        return await client.chat_json(
            model=settings.openai_synthesis_model,
            system_prompt=(
                "You are a senior media-intelligence analyst. Produce a concise structured report in Russian. "
                "Do not invent facts. Use only the provided data. Segment overviews should explain how the media segment framed the event. "
                "Complementarity should be one of: комплиментарная, критическая, смешанная, нейтральная. "
                "Cross-segment gaps must explicitly explain which globally visible themes were weak or absent in a segment and why that matters analytically."
            ),
            user_prompt=(
                "{\n"
                f'  "query": {search.query_plan.original_query!r},\n'
                f'  "coverage": {coverage.model_dump()!r},\n'
                f'  "segments": {compact_segments!r}\n'
                "}"
            ),
            schema_name="search_report_synthesis",
            schema=REPORT_SYNTHESIS_SCHEMA,
        )
    except (OpenAIAPIError, RuntimeError, ValueError):
        return None


def _merge_synthesis(
    segment_reports: list[SegmentReportResponse],
    synthesized_segments: list[dict[str, Any]],
) -> list[SegmentReportResponse]:
    synthesized_map = {row.get("segment"): row for row in synthesized_segments}
    merged: list[SegmentReportResponse] = []
    for report in segment_reports:
        synthesized = synthesized_map.get(report.segment)
        if not synthesized:
            merged.append(report)
            continue

        topic_map = {row["topic"]: row for row in synthesized.get("topic_briefs", []) if row.get("topic")}
        merged_topics: list[TopicBriefResponse] = []
        for topic in report.dominant_topics:
            override = topic_map.get(topic.topic, {})
            merged_topics.append(
                TopicBriefResponse(
                    **{
                        **topic.model_dump(),
                        "summary": override.get("summary") or topic.summary,
                        "accents": override.get("accents") or topic.accents,
                    }
                )
            )

        merged.append(
            SegmentReportResponse(
                **{
                    **report.model_dump(),
                    "overview": synthesized.get("overview") or report.overview,
                    "complementarity": synthesized.get("complementarity") or report.complementarity,
                    "dominant_topics": merged_topics,
                }
            )
        )
    return merged


def _quote_excerpt(row: dict) -> str | None:
    text = row.get("summary") or row.get("pivot_summary") or row.get("title") or ""
    sentences = [
        sentence.strip(" -\u2014")
        for sentence in text.replace("\n", " ").split(".")
        if len(sentence.strip()) >= 24
    ]
    if not sentences:
        return None
    excerpt = sentences[0]
    return excerpt[:240].strip()


def _quote_quality_ok(value: str | None) -> bool:
    if not value:
        return False
    normalized = " ".join(value.split()).strip().strip("“”\"'.,:;!?-—")
    if len(normalized) < 18:
        return False
    word_like_parts = [part for part in normalized.split() if any(char.isalpha() for char in part)]
    return len(word_like_parts) >= 3


def _quote_candidates_for_llm(row: dict) -> list[str]:
    ranked_candidates: list[tuple[int, str]] = []
    seen: set[str] = set()
    for quote in row.get("exact_quotes", []) or []:
        if not _quote_quality_ok(quote):
            continue
        normalized = " ".join(quote.split()).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        score = _quote_candidate_score(row, normalized)
        if score > 0:
            ranked_candidates.append((score, normalized))

    excerpt = _quote_excerpt(row)
    if _quote_quality_ok(excerpt):
        normalized_excerpt = " ".join((excerpt or "").split()).strip()
        if normalized_excerpt and normalized_excerpt not in seen:
            score = _quote_candidate_score(row, normalized_excerpt)
            if score > 0:
                ranked_candidates.append((score, normalized_excerpt))

    ranked_candidates.sort(key=lambda pair: (pair[0], len(pair[1])), reverse=True)
    return [quote for _, quote in ranked_candidates[:4]]


def _quote_candidate_score(row: dict, candidate: str) -> int:
    normalized = candidate.lower()
    low_signal_patterns = {
        "honored to host",
        "pleased to host",
        "honoured to host",
        "glad to welcome",
        "at india house today",
        "today,",
    }
    if any(pattern in normalized for pattern in low_signal_patterns):
        return -4

    anchor_text = " ".join(
        str(part or "")
        for part in [
            row.get("title"),
            row.get("pivot_summary"),
            row.get("summary"),
            row.get("cluster_label"),
            row.get("narrative"),
        ]
    ).lower()
    anchor_tokens = set(part for part in anchor_text.split() if any(char.isalpha() for char in part) and len(part) >= 4)
    candidate_tokens = [part for part in normalized.split() if any(char.isalpha() for char in part) and len(part) >= 4]
    overlap = sum(1 for token in candidate_tokens if token in anchor_tokens)
    has_digits = any(char.isdigit() for char in candidate)
    return overlap * 4 + min(len(candidate_tokens), 8) + (1 if has_digits else 0)
