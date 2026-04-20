from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings
from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult


class GuardianConnector(BaseConnector):
    provider = "guardian"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        api_key = self.settings.guardian_open_platform_key
        if not api_key:
            return ConnectorResult(
                provider=self.provider,
                status="unconfigured",
                message="Guardian Open Platform key is missing.",
                items=[],
            )

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=lookback_days)
        params = {
            "api-key": api_key,
            "q": query,
            "page-size": min(limit, 50),
            "from-date": start_date.isoformat(),
            "to-date": end_date.isoformat(),
            "show-fields": "headline,trailText,bodyText",
            "order-by": "newest",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://content.guardianapis.com/search",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        results = payload.get("response", {}).get("results", [])
        items: list[ConnectorItem] = []
        for article in results:
            fields = article.get("fields", {}) or {}
            items.append(
                ConnectorItem(
                    provider=self.provider,
                    source_type="news",
                    source_name="The Guardian",
                    source_country="GB",
                    language="eng",
                    title=fields.get("headline") or article.get("webTitle") or "Untitled article",
                    url=article.get("webUrl") or "",
                    summary=(fields.get("trailText") or fields.get("bodyText") or "")[:900],
                    published_at=_parse_guardian_date(article.get("webPublicationDate")),
                    ranking_score=0,
                    raw_payload=article,
                )
            )

        return ConnectorResult(
            provider=self.provider,
            status="ok",
            message="Articles loaded from the Guardian Open Platform.",
            items=items,
        )


def _parse_guardian_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
