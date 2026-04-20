from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ConnectorItem:
    provider: str
    source_type: str
    source_name: str
    source_country: str | None
    language: str | None
    title: str
    url: str
    summary: str
    published_at: datetime
    ranking_score: int
    raw_payload: dict


@dataclass(slots=True)
class ConnectorResult:
    provider: str
    status: str
    message: str
    items: list[ConnectorItem]


class BaseConnector(ABC):
    provider: str

    @abstractmethod
    async def search(self, query: str, lookback_days: int, limit: int) -> ConnectorResult:
        raise NotImplementedError

