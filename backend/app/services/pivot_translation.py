from __future__ import annotations

import asyncio
from collections.abc import Iterable

from deep_translator import GoogleTranslator


ENGLISH_MARKERS = {"en", "eng", "english"}


class PivotTranslator:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], str] = {}
        self._semaphore = asyncio.Semaphore(4)

    async def to_english(self, text: str, language: str | None) -> tuple[str, bool]:
        cleaned = " ".join(text.split()).strip()
        if not cleaned:
            return "", False
        if is_english(language):
            return cleaned, False

        cache_key = ((language or "auto").lower(), cleaned[:1200])
        if cache_key in self._cache:
            return self._cache[cache_key], True

        async with self._semaphore:
            translated = await asyncio.to_thread(_translate_to_english_sync, cleaned[:1200])
        if translated:
            self._cache[cache_key] = translated
            return translated, True
        return cleaned, False


def is_english(language: str | None) -> bool:
    if not language:
        return False
    normalized = language.strip().lower()
    return normalized in ENGLISH_MARKERS or normalized.startswith("en")


def combine_for_translation(parts: Iterable[str | None], max_chars: int = 900) -> str:
    cleaned_parts = [" ".join((part or "").split()).strip() for part in parts]
    merged = "\n\n".join(part for part in cleaned_parts if part)
    return merged[:max_chars]


def _translate_to_english_sync(text: str) -> str | None:
    try:
        translated = GoogleTranslator(source="auto", target="en").translate(text)
    except Exception:
        return None
    normalized = " ".join((translated or "").split()).strip()
    return normalized or None
