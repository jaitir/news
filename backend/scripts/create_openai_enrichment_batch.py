from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from app.db.session import SessionLocal
from app.services.llm_pipeline import build_batch_requests
from app.services.openai_api import OpenAIAPIClient
from app.services.query_planner import build_search_plan
from app.services.search_service import SearchService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a JSONL batch file for OpenAI enrichment.")
    parser.add_argument("snapshot_id", help="Snapshot UUID to export into an OpenAI batch.")
    parser.add_argument("--submit", action="store_true", help="Upload the JSONL file and create an OpenAI batch job.")
    parser.add_argument(
        "--output-dir",
        default="backend/output/batches",
        help="Directory where the generated JSONL file will be stored.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    service = SearchService()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        snapshot = service.get_snapshot_model(db, UUID(args.snapshot_id))
        items = [service._item_to_schema(item).model_dump() for item in snapshot.items]

    batch_bytes = build_batch_requests(
        items,
        query=snapshot.query_text,
        search_plan=build_search_plan(snapshot.query_text),
    )
    output_path = output_dir / f"{snapshot.id}.jsonl"
    output_path.write_bytes(batch_bytes)
    print(f"Saved batch input to {output_path}")

    if args.submit:
        client = OpenAIAPIClient()
        file_payload = await client.upload_batch_file(batch_bytes, output_path.name)
        batch_payload = await client.create_batch(input_file_id=file_payload["id"])
        print(f"Uploaded file: {file_payload['id']}")
        print(f"Created batch: {batch_payload['id']}")


if __name__ == "__main__":
    asyncio.run(main())
