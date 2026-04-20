from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import httpx

from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult


class GDELTConnector(BaseConnector):
    provider = "gdelt"

    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": min(limit, 250),
            "sort": "datedesc",
            "timespan": f"{lookback_days}days",
        }
        url = "https://api.gdeltproject.org/api/v2/doc/doc"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)
            if response.status_code == 429:
                return ConnectorResult(
                    provider=self.provider,
                    status="rate_limited",
                    message="GDELT rate-limited this request. Retry shortly or use cached/saved snapshots.",
                    items=[],
                )
            response.raise_for_status()
            try:
                payload = response.json()
            except json.JSONDecodeError:
                return ConnectorResult(
                    provider=self.provider,
                    status="rate_limited",
                    message="GDELT returned a non-JSON throttle response. Retry shortly or use cached/saved snapshots.",
                    items=[],
                )

        articles = payload.get("articles", [])
        items: list[ConnectorItem] = []
        for article in articles:
            published_at = _parse_gdelt_date(article.get("seendate"))
            domain = article.get("domain", "Unknown source")
            items.append(
                ConnectorItem(
                    provider=self.provider,
                    source_type="news",
                    source_name=domain,
                    source_country=article.get("sourcecountry"),
                    language=article.get("language"),
                    title=article.get("title") or article.get("url") or "Untitled article",
                    url=article.get("url") or "",
                    summary=(article.get("snippet") or "").strip()[:900],
                    published_at=published_at,
                    ranking_score=0,
                    raw_payload=article,
                )
            )

        return ConnectorResult(
            provider=self.provider,
            status="ok",
            message="Coverage loaded from GDELT DOC API.",
            items=items,
        )


def _parse_gdelt_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc) - timedelta(minutes=5)
