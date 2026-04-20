from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select

from app.core.source_registry import resolve_source_profile
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.search import SearchResultItem, SearchSnapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Export unknown media sources from stored snapshots for registry curation.")
    parser.add_argument("--limit", type=int, default=200, help="Maximum number of candidates to export.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("source_registry_candidates.csv"),
        help="Destination CSV path.",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        rows = list(
            session.execute(
                select(SearchResultItem, SearchSnapshot.query_text, SearchSnapshot.created_at)
                .join(SearchSnapshot, SearchSnapshot.id == SearchResultItem.snapshot_id)
                .order_by(SearchSnapshot.created_at.desc())
            )
        )

    grouped: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "source_name": "",
            "domain": "",
            "provider_counts": defaultdict(int),
            "countries": set(),
            "languages": set(),
            "queries": set(),
            "sample_urls": set(),
            "last_seen": None,
            "count": 0,
        }
    )

    for item, query_text, created_at in rows:
        if resolve_source_profile(source_name=item.source_name, url=item.url):
            continue

        domain = _extract_domain(item.url)
        key = (item.source_name, domain)
        bucket = grouped[key]
        bucket["source_name"] = item.source_name
        bucket["domain"] = domain
        bucket["provider_counts"][item.provider] += 1
        if item.source_country:
            bucket["countries"].add(item.source_country)
        if item.language:
            bucket["languages"].add(item.language)
        bucket["queries"].add(query_text)
        bucket["sample_urls"].add(item.url)
        bucket["count"] += 1
        if bucket["last_seen"] is None or created_at > bucket["last_seen"]:
            bucket["last_seen"] = created_at

    candidates = sorted(grouped.values(), key=lambda row: (row["count"], row["last_seen"]), reverse=True)[: args.limit]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "source_name",
                "domain",
                "occurrences",
                "providers",
                "countries",
                "languages",
                "sample_queries",
                "sample_urls",
                "last_seen",
            ]
        )
        for row in candidates:
            writer.writerow(
                [
                    row["source_name"],
                    row["domain"],
                    row["count"],
                    ", ".join(f"{provider}:{count}" for provider, count in sorted(row["provider_counts"].items())),
                    ", ".join(sorted(row["countries"])),
                    ", ".join(sorted(row["languages"])),
                    " | ".join(sorted(row["queries"])[:4]),
                    " | ".join(sorted(row["sample_urls"])[:3]),
                    row["last_seen"].isoformat() if row["last_seen"] else "",
                ]
            )

    print(f"Exported {len(candidates)} registry candidates to {args.output}")


def _extract_domain(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    hostname = (parsed.netloc or parsed.path).lower()
    return hostname.removeprefix("www.").strip("/")


if __name__ == "__main__":
    main()
