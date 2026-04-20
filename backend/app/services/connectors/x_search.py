from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import httpx

from app.core.config import get_settings
from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult


class XConnector(BaseConnector):
    provider = "x"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        token = self.settings.x_bearer_token
        curated_accounts = set(self.settings.x_curated_accounts)
        if not token:
            return ConnectorResult(
                provider=self.provider,
                status="unconfigured",
                message="X bearer token is missing.",
                items=[],
            )
        token = unquote(token)

        end_time = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=15)
        requested_window = timedelta(days=lookback_days)
        # X recent search rejects requests that sit exactly on the 7-day boundary.
        max_recent_window = timedelta(days=6, hours=23, minutes=55)
        start_time = end_time - min(requested_window, max_recent_window)
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=30) as client:
            payload: dict | None = None
            invalid_request_detail = "X API rejected the search parameters."
            for query_candidate in _build_query_candidates(query, curated_accounts):
                params = {
                    "query": query_candidate,
                    "max_results": min(limit, 100),
                    "tweet.fields": "created_at,lang,public_metrics",
                    "expansions": "author_id",
                    "user.fields": "name,username,location",
                    "start_time": start_time.isoformat().replace("+00:00", "Z"),
                    "end_time": end_time.isoformat().replace("+00:00", "Z"),
                }
                response = await client.get(
                    "https://api.x.com/2/tweets/search/recent",
                    params=params,
                    headers=headers,
                )
                if response.status_code == 402:
                    return ConnectorResult(
                        provider=self.provider,
                        status="payment_required",
                        message="X API requires a paid plan with search access for this app.",
                        items=[],
                    )
                if response.status_code == 403:
                    return ConnectorResult(
                        provider=self.provider,
                        status="forbidden",
                        message="X API rejected recent search. Check that the app has a paid plan with search access.",
                        items=[],
                    )
                if response.status_code == 400:
                    invalid_request_detail = response.json().get("detail") or invalid_request_detail
                    continue

                response.raise_for_status()
                payload = response.json()
                if payload.get("data"):
                    break

            if payload is None:
                return ConnectorResult(
                    provider=self.provider,
                    status="invalid_request",
                    message=invalid_request_detail,
                    items=[],
                )

        users = {
            user["id"]: user
            for user in payload.get("includes", {}).get("users", [])
        }
        items: list[ConnectorItem] = []
        for post in payload.get("data", []):
            author = users.get(post.get("author_id", ""), {})
            username = (author.get("username") or "").lower()
            curated = bool(username and username in curated_accounts)
            if curated_accounts and not curated:
                continue
            metrics = post.get("public_metrics") or {}
            items.append(
                ConnectorItem(
                    provider=self.provider,
                    source_type="social",
                    source_name=author.get("name") or author.get("username") or "Unknown account",
                    source_country=author.get("location"),
                    language=post.get("lang"),
                    title=(post.get("text") or "").strip()[:160],
                    url=f"https://x.com/{author.get('username', 'i')}/status/{post.get('id')}",
                    summary=(post.get("text") or "").strip(),
                    published_at=_parse_x_timestamp(post.get("created_at")),
                    ranking_score=int(metrics.get("like_count", 0) + metrics.get("retweet_count", 0) * 2),
                    raw_payload={
                        **post,
                        "_author": author,
                        "_source_handle": author.get("username"),
                        "_curated_source": curated,
                    },
                )
            )

        return ConnectorResult(
            provider=self.provider,
            status="ok",
            message="Recent X posts loaded successfully.",
            items=items,
        )


def _parse_x_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _build_query_candidates(query: str, curated_accounts: set[str]) -> list[str]:
    tokens = [
        token
        for token in (piece.strip(" ,.!?\"'()[]{}:;").lower() for piece in query.split())
        if len(token) > 2 and token not in {"the", "and", "with", "from", "that", "this", "into"}
    ]
    keyword_fallback = " ".join(list(dict.fromkeys(tokens))[:5]) if tokens else ""
    base_candidates = [f'("{query}")']
    if keyword_fallback:
        base_candidates.append(f"({keyword_fallback})")

    candidates: list[str] = []
    if curated_accounts:
        handles = sorted(curated_accounts)
        for base in base_candidates:
            for chunk in _chunk(handles, 6):
                account_clause = " OR ".join(f"from:{handle}" for handle in chunk)
                candidates.append(f"{base} ({account_clause}) -is:retweet")
    else:
        candidates = [f"{base} -is:retweet" for base in base_candidates]
    return candidates


def _chunk(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]
