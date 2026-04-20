from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.countries import normalize_country_code
from app.core.source_registry import resolve_source_profile
from app.db.session import SessionLocal
from app.models.search import SearchResultItem, SearchSnapshot
from app.schemas.search import (
    ExecutiveSummaryResponse,
    ProviderStatusResponse,
    QueryPlanResponse,
    SearchReportResponse,
    SearchItemResponse,
    SearchRequest,
    SearchResponse,
    SearchSnapshotListResponse,
    SearchSnapshotSummary,
)
from app.services.analytics import build_narrative_groups, build_provider_summary, enrich_items
from app.services.connectors.event_registry import EventRegistryConnector
from app.services.connectors.gdelt import GDELTConnector
from app.services.connectors.gnews import GNewsConnector
from app.services.connectors.guardian import GuardianConnector
from app.services.connectors.media_cloud import MediaCloudConnector
from app.services.connectors.mock import MockConnector
from app.services.connectors.newsdata import NewsDataConnector
from app.services.connectors.open_web import OpenWebConnector
from app.services.connectors.telegram import TelegramConnector
from app.services.connectors.x_search import XConnector
from app.services.connectors.base import ConnectorResult
from app.services.llm_pipeline import apply_llm_pipeline
from app.services.query_expansion import enrich_search_plan
from app.services.query_planner import SearchPlan, build_search_plan, plan_queries_for_provider
from app.services.report_service import build_search_report

REPORT_CACHE_VERSION = 1


class SearchService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._report_locks: dict[str, asyncio.Lock] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self.connector_factory = {
            "event_registry": EventRegistryConnector,
            "gdelt": GDELTConnector,
            "open_web": OpenWebConnector,
            "gnews": GNewsConnector,
            "guardian": GuardianConnector,
            "media_cloud": MediaCloudConnector,
            "newsdata": NewsDataConnector,
            "x": XConnector,
            "telegram": TelegramConnector,
        }

    async def execute(self, db: Session, payload: SearchRequest, device_id: str | None = None) -> SearchResponse:
        snapshot = SearchSnapshot(
            device_id=device_id,
            query_text=payload.query,
            lookback_days=payload.lookback_days,
            requested_sources=payload.sources,
            total_results=0,
            status="processing",
            provider_summary=self._build_processing_provider_summary(payload),
        )
        db.add(snapshot)
        db.flush()
        snapshot_id = snapshot.id
        db.commit()
        db.refresh(snapshot)
        self._spawn_processing_task(snapshot_id, payload, device_id=device_id)
        return self.get_snapshot(db, snapshot_id, device_id=device_id)

    async def _build_search_plan(self, query: str) -> SearchPlan:
        base_plan = build_search_plan(query)
        try:
            return await asyncio.wait_for(
                enrich_search_plan(base_plan),
                timeout=max(self.settings.search_query_expansion_timeout_seconds, 1),
            )
        except Exception:
            return base_plan

    def list_snapshots(self, db: Session, limit: int = 20, device_id: str | None = None) -> SearchSnapshotListResponse:
        stmt = select(SearchSnapshot)
        if device_id:
            stmt = stmt.where(SearchSnapshot.device_id == device_id)
        stmt = stmt.order_by(SearchSnapshot.created_at.desc()).limit(limit)
        snapshots = list(db.scalars(stmt))
        return SearchSnapshotListResponse(items=[self._snapshot_to_summary(snapshot) for snapshot in snapshots])

    def get_snapshot(self, db: Session, snapshot_id: UUID, device_id: str | None = None) -> SearchResponse:
        snapshot = self._load_snapshot(db, snapshot_id, device_id=device_id)
        provider_statuses = [
            ProviderStatusResponse(
                provider=provider,
                status=payload.get("status", "stored"),
                message=payload.get("message", "Stored snapshot."),
                count=payload.get("count", 0),
            )
            for provider, payload in snapshot.provider_summary.items()
            if not str(provider).startswith("_")
        ]
        items = self._sort_item_schemas([self._item_to_schema(item) for item in snapshot.items])
        meta = snapshot.provider_summary.get("_meta", {})
        stored_query_plan = meta.get("query_plan") or {}
        query_plan = (
            QueryPlanResponse(**stored_query_plan)
            if stored_query_plan
            else self._query_plan_to_schema(build_search_plan(snapshot.query_text))
        )
        return SearchResponse(
            snapshot=self._snapshot_to_summary(snapshot),
            query_plan=query_plan,
            analysis_mode=meta.get("analysis_mode", "heuristic"),
            provider_statuses=provider_statuses,
            items=items,
            narrative_groups=build_narrative_groups([item.model_dump() for item in items]),
            executive_summary=self._executive_summary_from_payload(meta.get("executive_summary")),
        )

    def get_snapshot_model(self, db: Session, snapshot_id: UUID, device_id: str | None = None) -> SearchSnapshot:
        return self._load_snapshot(db, snapshot_id, device_id=device_id)

    async def get_structured_report(
        self,
        db: Session,
        snapshot_id: UUID,
        device_id: str | None = None,
    ) -> SearchReportResponse:
        snapshot = self._load_snapshot(db, snapshot_id, device_id=device_id)
        if snapshot.status == "processing":
            raise HTTPException(status_code=409, detail="Search is still processing.")
        if snapshot.status == "failed":
            meta = (snapshot.provider_summary or {}).get("_meta") or {}
            raise HTTPException(status_code=409, detail=meta.get("error_message") or "Search failed.")
        cached = self._cached_report_from_snapshot(snapshot)
        if cached:
            return cached

        lock = self._report_locks.setdefault(str(snapshot_id), asyncio.Lock())
        async with lock:
            snapshot = self._load_snapshot(db, snapshot_id, device_id=device_id)
            cached = self._cached_report_from_snapshot(snapshot)
            if cached:
                return cached

            snapshot_response = self.get_snapshot(db, snapshot_id, device_id=device_id)
            report = await build_search_report(snapshot_response)
            self._store_cached_report(db, snapshot, report)
            return report

    def connector_statuses(self) -> list[ProviderStatusResponse]:
        rows: list[ProviderStatusResponse] = []
        for name, factory in self.connector_factory.items():
            connector = factory()
            if name == "gdelt":
                rows.append(
                    ProviderStatusResponse(
                        provider=name,
                        status="ready",
                        message="Public GDELT connector is available without credentials.",
                        count=0,
                    )
                )
            elif name == "event_registry":
                ready = bool(self.settings.event_registry_api_key)
                rows.append(
                    ProviderStatusResponse(
                        provider=name,
                        status="ready" if ready else "needs_key",
                        message="Provide an Event Registry API key to enable curated global media coverage.",
                        count=0,
                    )
                )
            elif name == "x":
                ready = bool(self.settings.x_bearer_token)
                rows.append(
                    ProviderStatusResponse(
                        provider=name,
                        status="ready" if ready else "needs_key",
                        message="Provide an X bearer token to search recent posts.",
                        count=0,
                    )
                )
            elif name == "guardian":
                ready = bool(self.settings.guardian_open_platform_key)
                rows.append(
                    ProviderStatusResponse(
                        provider=name,
                        status="ready" if ready else "needs_key",
                        message="Guardian Open Platform is a useful open editorial reference layer.",
                        count=0,
                    )
                )
            elif name == "open_web":
                rows.append(
                    ProviderStatusResponse(
                        provider=name,
                        status="ready",
                        message="Открытый веб-поиск добирает актуальные публикации вне news API-агрегаторов.",
                        count=0,
                    )
                )
            elif name == "gnews":
                ready = bool(self.settings.gnews_api_key)
                rows.append(
                    ProviderStatusResponse(
                        provider=name,
                        status="ready" if ready else "needs_key",
                        message="GNews is a useful secondary global index with a separate crawling stack.",
                        count=0,
                    )
                )
            elif name == "media_cloud":
                ready = bool(self.settings.media_cloud_api_key)
                rows.append(
                    ProviderStatusResponse(
                        provider=name,
                        status="ready" if ready else "needs_key",
                        message="Media Cloud adds an independent research-oriented story index for cross-checking.",
                        count=0,
                    )
                )
            elif name == "newsdata":
                ready = bool(self.settings.newsdata_api_key)
                rows.append(
                    ProviderStatusResponse(
                        provider=name,
                        status="ready" if ready else "needs_key",
                        message="NewsData.io adds another multilingual crawler layer, with latest-endpoint limits on some plans.",
                        count=0,
                    )
                )
            else:
                ready = bool(
                    self.settings.telegram_api_id
                    and self.settings.telegram_api_hash
                    and self.settings.telegram_session_string
                )
                rows.append(
                    ProviderStatusResponse(
                        provider=name,
                        status="ready" if ready else "needs_session",
                        message=(
                            "Telegram requires MTProto credentials and a session string. "
                            "Global public-channel search may additionally require Telegram Premium or Stars."
                        ),
                        count=0,
                    )
                )
        return rows

    def _load_snapshot(self, db: Session, snapshot_id: UUID, device_id: str | None = None) -> SearchSnapshot:
        stmt = (
            select(SearchSnapshot)
            .options(selectinload(SearchSnapshot.items))
            .where(SearchSnapshot.id == snapshot_id)
        )
        if device_id:
            stmt = stmt.where(SearchSnapshot.device_id == device_id)
        snapshot = db.scalar(stmt)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Snapshot not found.")
        return snapshot

    def _cached_report_from_snapshot(self, snapshot: SearchSnapshot) -> SearchReportResponse | None:
        meta = (snapshot.provider_summary or {}).get("_meta") or {}
        if meta.get("cached_report_version") != REPORT_CACHE_VERSION:
            return None
        cached_report = meta.get("cached_report")
        if not isinstance(cached_report, dict):
            return None
        try:
            return SearchReportResponse(**cached_report)
        except Exception:
            return None

    def _store_cached_report(
        self,
        db: Session,
        snapshot: SearchSnapshot,
        report: SearchReportResponse,
    ) -> None:
        provider_summary = dict(snapshot.provider_summary or {})
        meta = dict(provider_summary.get("_meta") or {})
        meta["cached_report_version"] = REPORT_CACHE_VERSION
        meta["cached_report"] = report.model_dump(mode="json")
        provider_summary["_meta"] = meta
        snapshot.provider_summary = provider_summary
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

    async def _warm_report_cache(self, snapshot_id: UUID, device_id: str | None = None) -> None:
        try:
            with SessionLocal() as db:
                await self.get_structured_report(db, snapshot_id, device_id=device_id)
        except Exception:
            return

    def _spawn_processing_task(self, snapshot_id: UUID, payload: SearchRequest, device_id: str | None = None) -> None:
        task = asyncio.create_task(self._process_snapshot(snapshot_id, payload, device_id=device_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _process_snapshot(self, snapshot_id: UUID, payload: SearchRequest, device_id: str | None = None) -> None:
        try:
            (
                search_plan,
                provider_statuses,
                enriched_items,
                executive_summary,
                analysis_mode,
            ) = await self._run_search_pipeline(payload)
        except Exception as exc:
            with SessionLocal() as db:
                snapshot = self._load_snapshot(db, snapshot_id)
                provider_summary = dict(snapshot.provider_summary or {})
                meta = dict(provider_summary.get("_meta") or {})
                meta["analysis_mode"] = "failed"
                meta["error_message"] = str(exc) or "Search failed."
                provider_summary["_meta"] = meta
                snapshot.status = "failed"
                snapshot.provider_summary = provider_summary
                db.add(snapshot)
                db.commit()
            return

        with SessionLocal() as db:
            snapshot = self._load_snapshot(db, snapshot_id)
            snapshot.items.clear()
            provider_summary = build_provider_summary([row.model_dump() for row in provider_statuses])
            provider_summary["_meta"] = {
                "analysis_mode": analysis_mode,
                "executive_summary": executive_summary,
                "query_plan": self._query_plan_to_schema(search_plan).model_dump(),
                "requested_countries": payload.countries,
                "error_message": None,
            }
            snapshot.total_results = len(enriched_items)
            snapshot.status = "ready"
            snapshot.provider_summary = provider_summary
            db.add(snapshot)
            db.flush()

            for row in enriched_items:
                db.add(
                    SearchResultItem(
                        snapshot_id=snapshot.id,
                        provider=row["provider"],
                        source_type=row["source_type"],
                        source_name=row["source_name"],
                        source_country=row["source_country"],
                        language=row["language"],
                        title=row["title"],
                        url=row["url"],
                        summary=row["summary"],
                        narrative=row["narrative"],
                        emotion=row["emotion"],
                        stance=row["stance"],
                        published_at=row["published_at"],
                        ranking_score=row["ranking_score"],
                        raw_payload=_json_safe(
                            {
                                **(row["raw_payload"] or {}),
                                "_analysis": {
                                    "pivot_summary": row["pivot_summary"],
                                    "pivot_language": row["pivot_language"],
                                    "query_alignment": row["query_alignment"],
                                    "originality": row["originality"],
                                    "weighted_score": row["weighted_score"],
                                    "is_curated_source": row["is_curated_source"],
                                    "analysis_method": row.get("analysis_method", "heuristic"),
                                    "semantic_cluster": row.get("semantic_cluster"),
                                    "cluster_label": row.get("cluster_label"),
                                    "evidence_density": row.get("evidence_density"),
                                    "semantic_query_score": row.get("semantic_query_score"),
                                    "source_profile": row.get("source_profile"),
                                    "exact_quotes": row.get("exact_quotes", []),
                                },
                            }
                        ),
                    )
                )

            db.commit()
        self._spawn_processing_task_report(snapshot_id, device_id=device_id)

    async def _run_search_pipeline(
        self,
        payload: SearchRequest,
    ) -> tuple[SearchPlan, list[ProviderStatusResponse], list[dict], dict | None, str]:
        search_plan = await self._build_search_plan(payload.query)
        connectors = [self.connector_factory[name]() for name in payload.sources if name in self.connector_factory]
        tasks = [self._run_connector(connector, payload, search_plan) for connector in connectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        provider_statuses: list[ProviderStatusResponse] = []
        collected_items = []
        for connector, result in zip(connectors, results, strict=False):
            if isinstance(result, Exception):
                provider_statuses.append(
                    ProviderStatusResponse(
                        provider=connector.provider,
                        status="error",
                        message=str(result),
                        count=0,
                    )
                )
                continue

            provider_statuses.append(
                ProviderStatusResponse(
                    provider=result.provider,
                    status=result.status,
                    message=result.message,
                    count=len(result.items),
                )
            )
            collected_items.extend(result.items)

        if not collected_items and self.settings.enable_demo_data:
            demo_result = await MockConnector().search(payload.query, payload.lookback_days, min(payload.limit_per_source, 10))
            provider_statuses.append(
                ProviderStatusResponse(
                    provider=demo_result.provider,
                    status=demo_result.status,
                    message=demo_result.message,
                    count=len(demo_result.items),
                )
            )
            collected_items.extend(demo_result.items)

        enriched_items = await enrich_items(
            collected_items,
            payload.query,
            search_plan,
            enable_pivot_translation=self.settings.enable_pivot_translation,
        )
        enriched_items = self._filter_items_by_countries(enriched_items, payload.countries)
        try:
            enriched_items, executive_summary, analysis_mode = await asyncio.wait_for(
                apply_llm_pipeline(
                    enriched_items,
                    query=payload.query,
                    search_plan=search_plan,
                ),
                timeout=max(self.settings.search_llm_timeout_seconds, 1),
            )
        except Exception:
            executive_summary = None
            analysis_mode = "heuristic_timeout"
        provider_counts = Counter(row["provider"] for row in enriched_items)
        for status in provider_statuses:
            status.count = provider_counts.get(status.provider, 0)
            if payload.countries and status.status == "ok":
                status.message = f"{status.message} Применен фильтр по выбранным странам."
        return search_plan, provider_statuses, enriched_items, executive_summary, analysis_mode

    def _spawn_processing_task_report(self, snapshot_id: UUID, device_id: str | None = None) -> None:
        task = asyncio.create_task(self._warm_report_cache(snapshot_id, device_id=device_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _build_processing_provider_summary(self, payload: SearchRequest) -> dict:
        base_plan = self._query_plan_to_schema(build_search_plan(payload.query)).model_dump()
        provider_summary: dict[str, dict] = {
            source: {
                "status": "queued",
                "message": "Источник поставлен в очередь на обработку.",
                "count": 0,
            }
            for source in payload.sources
        }
        provider_summary["_meta"] = {
            "analysis_mode": "processing",
            "executive_summary": None,
            "query_plan": base_plan,
            "requested_countries": payload.countries,
            "error_message": None,
        }
        return provider_summary

    @staticmethod
    def _snapshot_to_summary(snapshot: SearchSnapshot) -> SearchSnapshotSummary:
        meta = snapshot.provider_summary.get("_meta", {}) if snapshot.provider_summary else {}
        return SearchSnapshotSummary(
            id=snapshot.id,
            query_text=snapshot.query_text,
            lookback_days=snapshot.lookback_days,
            requested_sources=snapshot.requested_sources,
            requested_countries=meta.get("requested_countries") or [],
            total_results=snapshot.total_results,
            status=snapshot.status,
            error_message=meta.get("error_message"),
            created_at=snapshot.created_at,
        )

    @staticmethod
    def _item_to_schema(item: SearchResultItem) -> SearchItemResponse:
        analysis = (item.raw_payload or {}).get("_analysis", {})
        source_profile = analysis.get("source_profile") or resolve_source_profile(
            source_name=item.source_name,
            url=item.url,
            country_hint=item.source_country,
        )
        return SearchItemResponse(
            id=item.id,
            provider=item.provider,
            source_type=item.source_type,
            source_name=item.source_name,
            source_country=item.source_country,
            language=item.language,
            title=item.title,
            url=item.url,
            summary=item.summary,
            pivot_summary=analysis.get("pivot_summary", item.summary),
            pivot_language=analysis.get("pivot_language"),
            narrative=item.narrative,
            emotion=item.emotion,
            stance=item.stance,
            query_alignment=analysis.get("query_alignment", "low"),
            originality=analysis.get("originality", "unknown"),
            weighted_score=int(analysis.get("weighted_score", item.ranking_score)),
            is_curated_source=bool(analysis.get("is_curated_source", False)),
            analysis_method=analysis.get("analysis_method", "heuristic"),
            semantic_cluster=analysis.get("semantic_cluster"),
            cluster_label=analysis.get("cluster_label"),
            semantic_query_score=analysis.get("semantic_query_score"),
            source_profile=source_profile,
            exact_quotes=analysis.get("exact_quotes", []),
            published_at=item.published_at,
            ranking_score=item.ranking_score,
        )

    @staticmethod
    def _query_plan_to_schema(plan: SearchPlan) -> QueryPlanResponse:
        return QueryPlanResponse(
            original_query=plan.original_query,
            expanded_query=plan.expanded_query,
            keyword_query=plan.keyword_query,
            anchor_terms=plan.anchor_terms,
            entity_aliases=plan.entity_aliases,
            paraphrases=plan.paraphrases,
            multilingual_queries=plan.multilingual_queries,
        )

    @staticmethod
    def _sort_item_schemas(items: list[SearchItemResponse]) -> list[SearchItemResponse]:
        alignment_rank = {"high": 3, "medium": 2, "low": 1}
        return sorted(
            items,
            key=lambda item: (
                item.weighted_score,
                alignment_rank.get(item.query_alignment, 0),
                item.published_at,
            ),
            reverse=True,
        )

    @staticmethod
    def _executive_summary_from_payload(payload) -> ExecutiveSummaryResponse | None:
        if not payload:
            return None
        return ExecutiveSummaryResponse(**payload)

    @staticmethod
    def _filter_items_by_countries(items: list[dict], countries: list[str]) -> list[dict]:
        selected_codes = {
            normalize_country_code(value)
            for value in countries
            if normalize_country_code(value)
        }
        if not selected_codes:
            return items

        filtered: list[dict] = []
        for item in items:
            profile = item.get("source_profile") or {}
            candidates: list[str] = []
            if profile.get("country"):
                candidates.append(profile.get("country"))
            raw_country = item.get("source_country")
            if raw_country:
                candidates.extend(str(raw_country).split(","))

            normalized_codes = {
                normalize_country_code(candidate)
                for candidate in candidates
                if normalize_country_code(candidate)
            }
            if normalized_codes & selected_codes:
                filtered.append(item)
        return filtered

    async def _run_connector(self, connector, payload: SearchRequest, search_plan: SearchPlan):
        queries = plan_queries_for_provider(connector.provider, search_plan)
        collected_items = []
        seen_fingerprints: set[str] = set()
        last_result = None
        terminal_statuses = {
            "rate_limited",
            "quota_reached",
            "limited_plan",
            "payment_required",
            "premium_required",
            "unauthorized",
            "forbidden",
            "invalid_request",
        }
        for index, query in enumerate(queries):
            per_query_limit = self._per_query_limit(connector.provider, payload.limit_per_source, index)
            try:
                result = await asyncio.wait_for(
                    connector.search(query, payload.lookback_days, per_query_limit),
                    timeout=max(self.settings.search_connector_timeout_seconds, 1),
                )
            except TimeoutError:
                result = ConnectorResult(
                    provider=connector.provider,
                    status="timeout",
                    message="Источник не успел ответить в бюджет времени этого веб-поиска.",
                    items=[],
                )
            last_result = result
            for item in result.items:
                fingerprint = self._connector_item_fingerprint(item)
                if fingerprint in seen_fingerprints:
                    continue
                seen_fingerprints.add(fingerprint)
                collected_items.append(item)
            enough_results = len(collected_items) >= payload.limit_per_source
            terminal_failure = not result.items and result.status in terminal_statuses
            if enough_results or terminal_failure:
                break

        if last_result is None:
            raise RuntimeError(f"{connector.provider} produced no result object.")

        if len(queries) > 1 and collected_items:
            return type(last_result)(
                provider=last_result.provider,
                status="ok",
                message=f"{last_result.message} Query expansion was used to broaden recall.",
                items=collected_items,
            )

        if collected_items and last_result.status != "ok":
            return type(last_result)(
                provider=last_result.provider,
                status="ok",
                message=f"{last_result.message} Partial results were recovered via fallback query strategy.",
                items=collected_items,
            )

        return last_result

    @staticmethod
    def _connector_item_fingerprint(item) -> str:
        normalized_url = (item.url or "").split("?")[0].rstrip("/").lower()
        normalized_title = " ".join((item.title or "").lower().split())[:180]
        return f"{normalized_url}|{normalized_title}"

    @staticmethod
    def _per_query_limit(provider: str, requested_limit: int, query_index: int) -> int:
        if provider == "open_web":
            if query_index == 0:
                return min(requested_limit, 16)
            return min(requested_limit, 10)
        if provider in {"x", "telegram"}:
            return min(requested_limit, 25)
        return requested_limit


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
