from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

from mediacloud.api import SearchApi
from mediacloud.error import APIResponseError, MCException

from app.core.config import get_settings
from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult


class MediaCloudConnector(BaseConnector):
    provider = "media_cloud"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        api_key = self.settings.media_cloud_api_key
        if not api_key:
            return ConnectorResult(
                provider=self.provider,
                status="unconfigured",
                message="Media Cloud API key is missing.",
                items=[],
            )

        start_date = date.today() - timedelta(days=lookback_days)
        end_date = date.today()

        try:
            stories, _ = await asyncio.to_thread(
                _fetch_stories,
                api_key,
                query,
                start_date,
                end_date,
                min(limit, 100),
            )
        except APIResponseError as exc:
            status_code = exc.response.status_code
            if status_code == 401:
                return ConnectorResult(
                    provider=self.provider,
                    status="unauthorized",
                    message="Media Cloud rejected the API token.",
                    items=[],
                )
            if status_code == 429:
                return ConnectorResult(
                    provider=self.provider,
                    status="rate_limited",
                    message="Media Cloud rate-limited this request. Retry shortly.",
                    items=[],
                )
            if status_code == 403:
                return ConnectorResult(
                    provider=self.provider,
                    status="forbidden",
                    message="Media Cloud denied this query for the current account.",
                    items=[],
                )
            return ConnectorResult(
                provider=self.provider,
                status="error",
                message=str(exc),
                items=[],
            )
        except MCException as exc:
            return ConnectorResult(
                provider=self.provider,
                status="error",
                message=exc.message,
                items=[],
            )

        items: list[ConnectorItem] = []
        for story in stories:
            summary = (story.get("text") or story.get("title") or "").strip()
            items.append(
                ConnectorItem(
                    provider=self.provider,
                    source_type="news",
                    source_name=story.get("media_name") or "Unknown source",
                    source_country=None,
                    language=story.get("language"),
                    title=story.get("title") or "Untitled article",
                    url=story.get("url") or "",
                    summary=summary[:900],
                    published_at=_story_date_to_datetime(story.get("publish_date")),
                    ranking_score=0,
                    raw_payload=story,
                )
            )

        return ConnectorResult(
            provider=self.provider,
            status="ok",
            message="Coverage loaded from Media Cloud.",
            items=items,
        )


def _fetch_stories(
    api_key: str,
    query: str,
    start_date: date,
    end_date: date,
    page_size: int,
) -> tuple[list[dict], str | None]:
    api = SearchApi(api_key)
    return api.story_list(
        query,
        start_date=start_date,
        end_date=end_date,
        page_size=page_size,
        sort_order="desc",
    )


def _story_date_to_datetime(value: date | str | None) -> datetime:
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
