from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult


class MockConnector(BaseConnector):
    provider = "demo"

    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        now = datetime.now(timezone.utc)
        prototypes = [
            (
                "Global Wire",
                "US",
                "eng",
                f"{query}: officials frame it as a strategic de-escalation",
                "The article emphasizes diplomatic signaling, official statements, and the broader strategic calculus behind the move.",
            ),
            (
                "Asia Business Daily",
                "CN",
                "zho",
                f"{query}: markets react to trade and supply-chain implications",
                "Coverage focuses on exporters, tariff exposure, and whether investors see the announcement as durable or tactical.",
            ),
            (
                "Euro Policy Review",
                "DE",
                "deu",
                f"{query}: allies question enforcement and verification",
                "The piece stresses implementation details, treaty verification, and the gap between public language and practical commitments.",
            ),
            (
                "Telegram Channel Monitor",
                "AE",
                "rus",
                f"{query}: commentators argue the announcement changes regional leverage",
                "A fast-moving social channel version of the story with higher emotional temperature and stronger geopolitical framing.",
            ),
        ]
        items: list[ConnectorItem] = []
        for index, (source, country, language, title, summary) in enumerate(prototypes[:limit], start=1):
            items.append(
                ConnectorItem(
                    provider=self.provider,
                    source_type="demo",
                    source_name=source,
                    source_country=country,
                    language=language,
                    title=title,
                    url=f"https://example.com/{index}",
                    summary=summary,
                    published_at=now - timedelta(hours=index * 5),
                    ranking_score=100 - index,
                    raw_payload={"demo": True, "query": query, "index": index},
                )
            )

        return ConnectorResult(
            provider=self.provider,
            status="demo",
            message="Demo results were generated because no external providers are configured yet.",
            items=items,
        )

