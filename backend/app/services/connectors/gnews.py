from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings
from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult


class GNewsConnector(BaseConnector):
    provider = "gnews"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        api_key = self.settings.gnews_api_key
        if not api_key:
            return ConnectorResult(
                provider=self.provider,
                status="unconfigured",
                message="GNews API key is missing.",
                items=[],
            )

        end_date = datetime.now(timezone.utc).replace(microsecond=0)
        start_date = end_date - timedelta(days=lookback_days)
        params = {
            "q": query,
            "max": min(limit, 100),
            "from": start_date.isoformat().replace("+00:00", "Z"),
            "to": end_date.isoformat().replace("+00:00", "Z"),
            "in": "title,description,content",
            "nullable": "description,content,image",
            "apikey": api_key,
        }

        payload: dict = {}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://gnews.io/api/v4/search",
                params=params,
            )
            if response.status_code == 401:
                return ConnectorResult(
                    provider=self.provider,
                    status="unauthorized",
                    message="GNews rejected the API key.",
                    items=[],
                )
            if response.status_code == 403:
                return ConnectorResult(
                    provider=self.provider,
                    status="quota_reached",
                    message="GNews quota is exhausted for the current plan.",
                    items=[],
                )
            if response.status_code == 429:
                return ConnectorResult(
                    provider=self.provider,
                    status="rate_limited",
                    message="GNews rate-limited this request. Retry shortly.",
                    items=[],
                )
            response.raise_for_status()
            payload = response.json()

        items: list[ConnectorItem] = []
        for article in payload.get("articles", []):
            source = article.get("source", {}) or {}
            summary = " ".join(
                value for value in [article.get("description"), article.get("content")] if value
            ).strip()
            items.append(
                ConnectorItem(
                    provider=self.provider,
                    source_type="news",
                    source_name=source.get("name") or "Unknown source",
                    source_country=None,
                    language=None,
                    title=article.get("title") or "Untitled article",
                    url=article.get("url") or "",
                    summary=summary[:900],
                    published_at=_parse_gnews_date(article.get("publishedAt")),
                    ranking_score=0,
                    raw_payload=article,
                )
            )

        return ConnectorResult(
            provider=self.provider,
            status="ok",
            message="Articles loaded from GNews.",
            items=items,
        )


def _parse_gnews_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
