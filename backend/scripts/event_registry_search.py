from __future__ import annotations

import asyncio
import json
import sys

from app.schemas.event_registry import EventRegistrySearchRequest
from app.services.event_registry_news_service import EventRegistryNewsService


async def _main() -> None:
    raw_payload = sys.stdin.read()
    payload = EventRegistrySearchRequest.model_validate(json.loads(raw_payload))
    result = await EventRegistryNewsService().search(payload)
    sys.stdout.write(result.model_dump_json())


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except Exception as error:
        sys.stderr.write(str(error))
        sys.exit(1)
