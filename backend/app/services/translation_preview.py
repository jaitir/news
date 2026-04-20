from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from functools import lru_cache
from time import time

from app.core.config import get_settings


LANGUAGE_ALIASES = {
    "ara": "ar",
    "ar": "ar",
    "eng": "en",
    "en": "en",
    "fas": "fa",
    "fa": "fa",
    "per": "fa",
    "ru": "ru",
    "rus": "ru",
    "tr": "tr",
    "tur": "tr",
    "zh": "zh-CN",
    "zho": "zh-CN",
    "chi": "zh-CN",
}


class TranslationPreviewService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._cache: dict[tuple[str, str | None, str], tuple[float, str | None, str | None]] = {}

    def translate_preview(
        self,
        *,
        text: str,
        target_language: str = "ru",
        source_language: str | None = None,
    ) -> tuple[str | None, str | None, str]:
        normalized_text = " ".join((text or "").split()).strip()
        if len(normalized_text) < 2:
            return None, None, self.settings.translation_preview_provider
        if not self.settings.translation_preview_enabled:
            return None, None, self.settings.translation_preview_provider

        normalized_source = _normalize_language(source_language) or _detect_language(normalized_text)
        normalized_target = _normalize_language(target_language) or "ru"
        if normalized_source == normalized_target:
            return None, normalized_source, self.settings.translation_preview_provider

        cache_key = (normalized_text, normalized_source, normalized_target)
        cached = self._cache.get(cache_key)
        now = time()
        if cached and cached[0] > now:
            return cached[1], cached[2], self.settings.translation_preview_provider

        translated: str | None = None
        provider = self.settings.translation_preview_provider
        if provider == "libretranslate":
            translated = _translate_with_libretranslate(
                normalized_text,
                source_language=normalized_source,
                target_language=normalized_target,
                endpoint=self.settings.translation_preview_endpoint,
                api_key=self.settings.translation_preview_api_key,
            )
        else:
            provider = "mymemory"
            translated = _translate_with_mymemory(
                normalized_text,
                source_language=normalized_source,
                target_language=normalized_target,
            )
            if not translated:
                provider = "google-free"
                translated = _translate_with_google_free(
                    normalized_text,
                    source_language=normalized_source,
                    target_language=normalized_target,
                )

        self._cache[cache_key] = (
            now + max(self.settings.translation_preview_cache_ttl_seconds, 60),
            translated,
            normalized_source,
        )
        return translated, normalized_source, provider


def _translate_with_mymemory(text: str, *, source_language: str, target_language: str) -> str | None:
    url = (
        "https://api.mymemory.translated.net/get?q="
        + urllib.parse.quote(text)
        + f"&langpair={urllib.parse.quote(source_language)}|{urllib.parse.quote(target_language)}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "media-aggregator/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.load(response)
    except Exception:
        return None
    translated = ((payload or {}).get("responseData") or {}).get("translatedText")
    normalized = " ".join((translated or "").split()).strip()
    if not normalized or normalized.lower() == text.lower():
        return None
    return normalized


def _translate_with_libretranslate(
    text: str,
    *,
    source_language: str,
    target_language: str,
    endpoint: str | None,
    api_key: str | None,
) -> str | None:
    if not endpoint:
        return None
    payload = {
        "q": text,
        "source": source_language,
        "target": target_language,
        "format": "text",
    }
    if api_key:
        payload["api_key"] = api_key
    encoded = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/translate",
        data=encoded,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "media-aggregator/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            body = json.load(response)
    except Exception:
        return None
    translated = (body or {}).get("translatedText")
    normalized = " ".join((translated or "").split()).strip()
    if not normalized or normalized.lower() == text.lower():
        return None
    return normalized


def _translate_with_google_free(text: str, *, source_language: str, target_language: str) -> str | None:
    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&dj=1"
        + f"&sl={urllib.parse.quote(source_language)}"
        + f"&tl={urllib.parse.quote(target_language)}"
        + "&q="
        + urllib.parse.quote(text)
    )
    request = urllib.request.Request(url, headers={"User-Agent": "media-aggregator/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.load(response)
    except Exception:
        return None

    parts = payload.get("sentences") or []
    translated = " ".join(
        str(part.get("trans", "")).strip()
        for part in parts
        if isinstance(part, dict) and part.get("trans")
    ).strip()
    normalized = " ".join((translated or "").split()).strip()
    if not normalized or normalized.lower() == text.lower():
        return None
    return normalized


def _normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[normalized]
    if "-" in normalized:
        base = normalized.split("-", 1)[0]
        return LANGUAGE_ALIASES.get(base, normalized)
    return normalized


def _detect_language(text: str) -> str:
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh-CN"
    if re.search(r"[ğüşöçıİ]", text, flags=re.IGNORECASE):
        return "tr"
    if re.search(r"[а-яё]", text, flags=re.IGNORECASE):
        return "ru"
    return "en"


@lru_cache
def get_translation_preview_service() -> TranslationPreviewService:
    return TranslationPreviewService()
