from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.services.openai_api import OpenAIAPIClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check an OpenAI batch job and optionally download its output.")
    parser.add_argument("batch_id", help="OpenAI batch identifier.")
    parser.add_argument("--download-dir", default="backend/output/batches", help="Where to save output/error files.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    client = OpenAIAPIClient()
    payload = await client.retrieve_batch(args.batch_id)
    print(payload)

    output_dir = Path(args.download_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if payload.get("output_file_id"):
        content = await client.download_file_text(payload["output_file_id"])
        output_path = output_dir / f"{args.batch_id}-output.jsonl"
        output_path.write_text(content, encoding="utf-8")
        print(f"Downloaded output to {output_path}")

    if payload.get("error_file_id"):
        content = await client.download_file_text(payload["error_file_id"])
        error_path = output_dir / f"{args.batch_id}-errors.jsonl"
        error_path.write_text(content, encoding="utf-8")
        print(f"Downloaded errors to {error_path}")


if __name__ == "__main__":
    asyncio.run(main())
