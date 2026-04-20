from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.routes.deep_research import router as deep_research_router
from app.api.routes.event_registry import router as event_registry_router
from app.api.routes.searches import router as searches_router
from app.api.routes.translations import router as translations_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.models import SearchResultItem, SearchSnapshot

settings = get_settings()


def ensure_runtime_columns() -> None:
    inspector = inspect(engine)
    if "search_snapshots" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("search_snapshots")}
    if "device_id" in existing_columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE search_snapshots ADD COLUMN device_id VARCHAR(128)"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_runtime_columns()
    yield


app = FastAPI(title=settings.project_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_origin_regex=r"https://.*\.(trycloudflare\.com|proxy\.runpod\.net)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(searches_router, prefix=settings.api_v1_prefix)
app.include_router(translations_router, prefix=settings.api_v1_prefix)
app.include_router(deep_research_router, prefix=settings.api_v1_prefix)
app.include_router(event_registry_router, prefix=settings.api_v1_prefix)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
