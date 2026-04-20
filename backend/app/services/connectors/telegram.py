from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from telethon import TelegramClient, functions, types
from telethon.errors.rpcerrorlist import PremiumAccountRequiredError
from telethon.sessions import StringSession

from app.core.config import get_settings
from app.services.connectors.base import BaseConnector, ConnectorItem, ConnectorResult


class TelegramConnector(BaseConnector):
    provider = "telegram"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        curated_channels = set(self.settings.telegram_curated_channels)
        if not (
            self.settings.telegram_api_id
            and self.settings.telegram_api_hash
            and self.settings.telegram_session_string
        ):
            return ConnectorResult(
                provider=self.provider,
                status="unconfigured",
                message="Telegram credentials are missing. This connector expects MTProto credentials and a session string.",
                items=[],
            )

        api_id = int(self.settings.telegram_api_id)
        api_hash = self.settings.telegram_api_hash
        session_string = self.settings.telegram_session_string
        allow_paid_stars = self.settings.telegram_allow_paid_stars or None

        async with TelegramClient(StringSession(session_string), api_id, api_hash) as client:
            if not await client.is_user_authorized():
                return ConnectorResult(
                    provider=self.provider,
                    status="session_expired",
                    message="Telegram session is not authorized. Generate a fresh session string.",
                    items=[],
                )

            try:
                if self.settings.telegram_use_global_search:
                    flood = await client(
                        functions.channels.CheckSearchPostsFloodRequest(query=query)
                    )
                    query_is_free = bool(getattr(flood, "query_is_free", False))
                    remains = int(getattr(flood, "remains", 0))
                    stars_amount = int(getattr(flood, "stars_amount", 0) or 0)
                    if not query_is_free and remains <= 0 and not allow_paid_stars:
                        return ConnectorResult(
                            provider=self.provider,
                            status="paid_required",
                            message=(
                                "Telegram global post search for this query currently requires Stars. "
                                f"Required amount: {stars_amount}."
                            ),
                            items=[],
                        )

                    messages_response = await client(
                        functions.channels.SearchPostsRequest(
                            query=query,
                            offset_rate=0,
                            offset_peer=types.InputPeerEmpty(),
                            offset_id=0,
                            limit=min(limit, 100),
                            allow_paid_stars=allow_paid_stars,
                        )
                    )
                else:
                    messages_response = await client(
                        functions.messages.SearchGlobalRequest(
                            q=query,
                            filter=types.InputMessagesFilterEmpty(),
                            min_date=datetime.now(timezone.utc) - timedelta(days=lookback_days),
                            max_date=datetime.now(timezone.utc),
                            offset_rate=0,
                            offset_peer=types.InputPeerEmpty(),
                            offset_id=0,
                            limit=min(limit, 100),
                            broadcasts_only=True,
                        )
                    )
            except PremiumAccountRequiredError:
                return ConnectorResult(
                    provider=self.provider,
                    status="premium_required",
                    message=(
                        "Telegram global public-channel search requires a Telegram Premium account "
                        "for this session. Keep Telegram enabled only after upgrading the account "
                        "or switch to a curated channel-list strategy."
                    ),
                    items=[],
                )

            chat_lookup = {
                chat.id: chat
                for chat in getattr(messages_response, "chats", [])
            }

            items: list[ConnectorItem] = []
            for message in getattr(messages_response, "messages", []):
                chat = chat_lookup.get(getattr(getattr(message, "peer_id", None), "channel_id", None))
                username = getattr(chat, "username", None)
                normalized_username = (username or "").lower()
                curated = bool(normalized_username and normalized_username in curated_channels)
                if curated_channels and not curated:
                    continue
                url = f"https://t.me/{username}/{message.id}" if username else ""
                text = (getattr(message, "message", None) or "").strip()
                if not text:
                    continue

                views = int(getattr(message, "views", 0) or 0)
                forwards = int(getattr(message, "forwards", 0) or 0)
                reactions = getattr(message, "reactions", None)
                reaction_count = int(getattr(reactions, "results", None) and sum(result.count for result in reactions.results) or 0)

                items.append(
                    ConnectorItem(
                        provider=self.provider,
                        source_type="telegram",
                        source_name=getattr(chat, "title", None) or username or "Telegram channel",
                        source_country=None,
                        language=None,
                        title=text[:160],
                        url=url,
                        summary=text[:900],
                        published_at=getattr(message, "date", datetime.now(timezone.utc)),
                        ranking_score=views + forwards * 2 + reaction_count,
                        raw_payload={
                            **message.to_dict(),
                            "_source_handle": username,
                            "_curated_source": curated,
                        },
                    )
                )

            if curated_channels and len(items) < max(4, limit // 4):
                items.extend(
                    await self._search_curated_channels(
                        client=client,
                        curated_channels=sorted(curated_channels),
                        query=query,
                        lookback_days=lookback_days,
                        limit=limit,
                    )
                )

            items = _dedupe_items(items)[:limit]

        return ConnectorResult(
            provider=self.provider,
            status="ok",
            message="Telegram posts loaded successfully.",
            items=items,
        )

    async def _search_curated_channels(
        self,
        *,
        client: TelegramClient,
        curated_channels: list[str],
        query: str,
        lookback_days: int,
        limit: int,
    ) -> list[ConnectorItem]:
        collected: list[ConnectorItem] = []
        per_channel_limit = max(2, min(4, math.ceil(limit / max(min(len(curated_channels), 8), 1))))
        oldest_allowed = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        for username in curated_channels[:24]:
            try:
                entity = await client.get_entity(username)
            except Exception:
                continue

            async for message in client.iter_messages(entity, search=query, limit=per_channel_limit):
                text = (getattr(message, "message", None) or "").strip()
                if not text:
                    continue
                published_at = getattr(message, "date", datetime.now(timezone.utc))
                if published_at < oldest_allowed:
                    continue
                views = int(getattr(message, "views", 0) or 0)
                forwards = int(getattr(message, "forwards", 0) or 0)
                reactions = getattr(message, "reactions", None)
                reaction_count = int(getattr(reactions, "results", None) and sum(result.count for result in reactions.results) or 0)
                collected.append(
                    ConnectorItem(
                        provider=self.provider,
                        source_type="telegram",
                        source_name=getattr(entity, "title", None) or username or "Telegram channel",
                        source_country=None,
                        language=None,
                        title=text[:160],
                        url=f"https://t.me/{username}/{message.id}",
                        summary=text[:900],
                        published_at=published_at,
                        ranking_score=views + forwards * 2 + reaction_count,
                        raw_payload={
                            **message.to_dict(),
                            "_source_handle": username,
                            "_curated_source": True,
                        },
                    )
                )
        return collected


def _dedupe_items(items: list[ConnectorItem]) -> list[ConnectorItem]:
    seen: set[str] = set()
    deduped: list[ConnectorItem] = []
    for item in sorted(items, key=lambda row: (row.ranking_score, row.published_at), reverse=True):
        if item.url in seen:
            continue
        seen.add(item.url)
        deduped.append(item)
    return deduped
