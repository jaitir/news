from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings
from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult


class NewsDataConnector(BaseConnector):
    provider = "newsdata"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        api_key = self.settings.newsdata_api_key
        if not api_key:
            return ConnectorResult(
                provider=self.provider,
                status="unconfigured",
                message="NewsData.io API key is missing.",
                items=[],
            )

        latest_window_hours = max(1, min(lookback_days * 24, 48))
        max_supported_size = min(limit, 10)
        attempt_sequence = [
            (
                {
                    "apikey": api_key,
                    "q": query,
                    "size": max_supported_size,
                    "timeframe": latest_window_hours,
                    "removeduplicate": 1,
                    "timezone": "UTC",
                },
                f"Lookback is capped to the most recent {latest_window_hours}h on this connector.",
            ),
            (
                {
                    "apikey": api_key,
                    "q": query,
                    "size": max_supported_size,
                    "removeduplicate": 1,
                    "timezone": "UTC",
                },
                "This plan does not allow timeframe filtering on NewsData.io latest endpoint, so the connector is using the provider's default recent window.",
            ),
            (
                {
                    "apikey": api_key,
                    "q": query,
                    "size": max_supported_size,
                },
                "NewsData.io required a simplified latest-endpoint request for this plan.",
            ),
        ]

        response: httpx.Response | None = None
        payload: dict = {}
        lookback_note = attempt_sequence[0][1]
        last_message = "NewsData.io rejected this request."

        async with httpx.AsyncClient(timeout=30) as client:
            for params, note in attempt_sequence:
                response = await client.get("https://newsdata.io/api/1/latest", params=params)
                payload = _safe_json(response)
                if response.status_code == 200:
                    lookback_note = note
                    break
                if response.status_code == 401:
                    return ConnectorResult(
                        provider=self.provider,
                        status="unauthorized",
                        message="NewsData.io rejected the API key.",
                        items=[],
                    )
                if response.status_code == 403:
                    return ConnectorResult(
                        provider=self.provider,
                        status="limited_plan",
                        message=_extract_message(payload) or "NewsData.io denied this request.",
                        items=[],
                    )
                if response.status_code == 429:
                    return ConnectorResult(
                        provider=self.provider,
                        status="rate_limited",
                        message="NewsData.io rate-limited this request. Retry shortly.",
                        items=[],
                    )
                if response.status_code in {400, 422}:
                    last_message = _extract_message(payload) or last_message
                    continue
                response.raise_for_status()

        if response is None:
            return ConnectorResult(
                provider=self.provider,
                status="error",
                message="NewsData.io returned no response.",
                items=[],
            )
        if response.status_code != 200:
            return ConnectorResult(
                provider=self.provider,
                status="limited_plan",
                message=last_message,
                items=[],
            )

        items: list[ConnectorItem] = []
        for article in payload.get("results", []):
            summary = _build_summary(article)
            items.append(
                ConnectorItem(
                    provider=self.provider,
                    source_type="news",
                    source_name=article.get("source_name") or article.get("source_id") or "Unknown source",
                    source_country=", ".join(article.get("country") or []) or None,
                    language=article.get("language"),
                    title=article.get("title") or "Untitled article",
                    url=article.get("link") or "",
                    summary=summary[:900],
                    published_at=_parse_newsdata_date(article.get("pubDate")),
                    ranking_score=int(article.get("source_priority") or 0),
                    raw_payload=article,
                )
            )

        return ConnectorResult(
            provider=self.provider,
            status="ok",
            message=f"Coverage loaded from NewsData.io latest endpoint. {lookback_note}",
            items=items,
        )


def _build_summary(article: dict) -> str:
    parts = [article.get("description"), article.get("content")]
    text = " ".join(part for part in parts if part and "ONLY AVAILABLE" not in part).strip()
    return text or article.get("title") or ""


def _parse_newsdata_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace(" ", "T") + "+00:00")
    except ValueError:
        return datetime.now(timezone.utc) - timedelta(minutes=5)


def _safe_json(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_message(payload: dict) -> str | None:
    result = payload.get("results")
    if isinstance(result, dict):
        message = result.get("message")
        if isinstance(message, str):
            return message
    message = payload.get("message")
    if isinstance(message, str):
        return message
    return None
