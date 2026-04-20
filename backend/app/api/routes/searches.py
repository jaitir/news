from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.search import (
    ProviderStatusResponse,
    SearchReportResponse,
    SearchRequest,
    SearchResponse,
    SearchSnapshotListResponse,
)
from app.services.export_service import build_snapshot_docx_bytes, build_snapshot_workbook
from app.services.search_service import SearchService

router = APIRouter(prefix="/searches", tags=["searches"])


@lru_cache
def get_search_service() -> SearchService:
    return SearchService()


@router.get("/providers/statuses", response_model=list[ProviderStatusResponse])
def provider_statuses(service: SearchService = Depends(get_search_service)) -> list[ProviderStatusResponse]:
    return service.connector_statuses()


@router.post("", response_model=SearchResponse)
async def run_search(
    payload: SearchRequest,
    x_device_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    return await service.execute(db, payload, device_id=x_device_id)


@router.get("", response_model=SearchSnapshotListResponse)
def list_searches(
    limit: int = Query(default=20, ge=1, le=100),
    x_device_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
    service: SearchService = Depends(get_search_service),
) -> SearchSnapshotListResponse:
    return service.list_snapshots(db, limit, device_id=x_device_id)


@router.get("/{snapshot_id}", response_model=SearchResponse)
def get_search(
    snapshot_id: UUID,
    x_device_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    return service.get_snapshot(db, snapshot_id, device_id=x_device_id)


@router.get("/{snapshot_id}/report", response_model=SearchReportResponse)
async def get_search_report(
    snapshot_id: UUID,
    x_device_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
    service: SearchService = Depends(get_search_service),
) -> SearchReportResponse:
    return await service.get_structured_report(db, snapshot_id, device_id=x_device_id)


@router.get("/{snapshot_id}/export")
async def export_search(
    snapshot_id: UUID,
    format: str = Query(default="excel", pattern="^(excel|docx)$"),
    device_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    service: SearchService = Depends(get_search_service),
) -> Response:
    snapshot = service.get_snapshot_model(db, snapshot_id, device_id=device_id)
    if snapshot.status == "processing":
        raise HTTPException(status_code=409, detail="Search is still processing.")
    if snapshot.status == "failed":
        meta = (snapshot.provider_summary or {}).get("_meta") or {}
        raise HTTPException(status_code=409, detail=meta.get("error_message") or "Search failed.")
    report = await service.get_structured_report(db, snapshot_id, device_id=device_id)
    if format == "docx":
        payload = build_snapshot_docx_bytes(snapshot, report)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"snapshot-{snapshot_id}.docx"
    else:
        payload = build_snapshot_workbook(snapshot, report)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"snapshot-{snapshot_id}.xlsx"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
