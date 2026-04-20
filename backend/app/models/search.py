import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SearchSnapshot(Base):
    __tablename__ = "search_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[str | None] = mapped_column(String(128), index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    requested_sources: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    total_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    provider_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["SearchResultItem"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by=lambda: SearchResultItem.published_at.desc(),
    )


class SearchResultItem(Base):
    __tablename__ = "search_result_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("search_snapshots.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_country: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    narrative: Mapped[str] = mapped_column(String(255), nullable=False)
    emotion: Mapped[str] = mapped_column(String(64), nullable=False)
    stance: Mapped[str] = mapped_column(String(64), nullable=False, default="unclear")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ranking_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    snapshot: Mapped[SearchSnapshot] = relationship(back_populates="items")
