from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.schemas.deep_research import (
    DeepResearchRequest,
    DeepResearchResponse,
    ResearchAnnotationResponse,
    ResearchSourceResponse,
)
from app.services.openai_api import OpenAIAPIClient


RESEARCH_INSTRUCTIONS = """
You are a senior research analyst with live web access.

Research the topic globally across multiple regions and languages whenever possible.
Write the final answer in Russian.

Return a concise analyst brief with these sections:
1. Главный вывод
2. Что происходит по регионам мира
3. Где позиции расходятся
4. Что читать дальше

Requirements:
- Use live web search.
- Prefer a geographically diverse mix of reliable publications, research institutions, and official sources.
- Cite factual claims inline.
- Mention concrete articles, reports, or pages that are worth reading next.
- Keep the answer dense, practical, and readable inside a dashboard.
""".strip()


class DeepResearchService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAIAPIClient()

    async def create(self, payload: DeepResearchRequest) -> DeepResearchResponse:
        response = await self.client.create_response(
            model=self.settings.openai_deep_research_model,
            instructions=RESEARCH_INSTRUCTIONS,
            input_text=payload.query,
            background=True,
            reasoning={
                "effort": self.settings.openai_deep_research_reasoning_effort,
            },
            max_tool_calls=self.settings.openai_deep_research_max_tool_calls,
            tools=[
                {
                    "type": "web_search",
                    "external_web_access": True,
                }
            ],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
        )
        return self._serialize_response(response, fallback_query=payload.query)

    async def get(self, response_id: str) -> DeepResearchResponse:
        response = await self.client.retrieve_response(response_id=response_id)
        return self._serialize_response(response)

    def _serialize_response(
        self,
        payload: dict[str, Any],
        *,
        fallback_query: str | None = None,
    ) -> DeepResearchResponse:
        answer, annotations = _extract_message_content(payload)
        source_rows = _collect_sources(payload, annotations)
        error_message = _extract_error_message(payload)

        return DeepResearchResponse(
            id=payload.get("id", ""),
            query=_extract_query(payload) or fallback_query,
            model=payload.get("model") or self.settings.openai_deep_research_model,
            status=payload.get("status") or "unknown",
            answer=answer,
            annotations=annotations,
            sources=source_rows,
            error_message=error_message,
            created_at=_parse_timestamp(payload.get("created_at")),
        )


def _extract_message_content(payload: dict[str, Any]) -> tuple[str | None, list[ResearchAnnotationResponse]]:
    output = payload.get("output") or []
    collected_text: list[str] = []
    annotations: list[ResearchAnnotationResponse] = []

    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") != "output_text":
                continue
            text = (content.get("text") or "").strip()
            if text:
                collected_text.append(text)
            for annotation in content.get("annotations") or []:
                url = annotation.get("url")
                if not url:
                    continue
                annotations.append(
                    ResearchAnnotationResponse(
                        title=annotation.get("title"),
                        url=url,
                        start_index=annotation.get("start_index"),
                        end_index=annotation.get("end_index"),
                    )
                )

    answer = "\n\n".join(part for part in collected_text if part).strip() or None
    if not answer:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            answer = output_text.strip()
    return answer, annotations


def _collect_sources(
    payload: dict[str, Any],
    annotations: list[ResearchAnnotationResponse],
) -> list[ResearchSourceResponse]:
    citation_counts: dict[str, int] = defaultdict(int)
    titles: dict[str, str] = {}

    for annotation in annotations:
        citation_counts[annotation.url] += 1
        if annotation.title and annotation.url not in titles:
            titles[annotation.url] = annotation.title

    for item in payload.get("output") or []:
        if item.get("type") != "web_search_call":
            continue
        action = item.get("action") or {}
        for source in action.get("sources") or []:
            url = source.get("url")
            if not url:
                continue
            citation_counts.setdefault(url, 0)
            if source.get("title") and url not in titles:
                titles[url] = source.get("title")

    source_rows: list[ResearchSourceResponse] = []
    for url, count in citation_counts.items():
        domain = urlparse(url).netloc or url
        title = titles.get(url) or domain
        source_rows.append(
            ResearchSourceResponse(
                title=title,
                url=url,
                domain=domain,
                citation_count=count,
            )
        )

    source_rows.sort(key=lambda item: (-item.citation_count, item.domain, item.title))
    return source_rows


def _extract_query(payload: dict[str, Any]) -> str | None:
    input_value = payload.get("input")
    if isinstance(input_value, str):
        return input_value.strip() or None

    if not isinstance(input_value, list):
        return None

    chunks: list[str] = []
    for item in input_value:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for content in item.get("content") or []:
                if isinstance(content, dict) and content.get("type") == "input_text":
                    text = (content.get("text") or "").strip()
                    if text:
                        chunks.append(text)
    return "\n".join(chunks).strip() or None


def _extract_error_message(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

    incomplete = payload.get("incomplete_details")
    if isinstance(incomplete, dict):
        reason = incomplete.get("reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    return None
