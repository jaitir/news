from __future__ import annotations

from dataclasses import replace
from typing import Any

from deep_translator import GoogleTranslator

from app.core.countries import normalize_country_code
from app.core.config import get_settings
from app.services.openai_api import OpenAIAPIClient, OpenAIAPIError
from app.services.query_planner import SearchPlan


DEFAULT_LANGUAGE_LABELS = {
    "en": "English",
    "ru": "Russian",
    "ar": "Arabic",
    "fa": "Persian",
    "tr": "Turkish",
    "zh": "Chinese",
}

QUERY_EXPANSION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "paraphrases": {
            "type": "array",
            "items": {"type": "string"},
        },
        "multilingual_queries": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                code: {
                    "type": "array",
                    "items": {"type": "string"},
                }
                for code in DEFAULT_LANGUAGE_LABELS
            },
            "required": list(DEFAULT_LANGUAGE_LABELS.keys()),
        },
        "focus_country_codes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "strict_entity_phrases": {
            "type": "array",
            "items": {"type": "string"},
        },
        "search_mode": {
            "type": "string",
            "enum": ["broad", "strict_entity"],
        },
    },
    "required": ["paraphrases", "multilingual_queries", "focus_country_codes", "strict_entity_phrases", "search_mode"],
}

_QUERY_EXPANSION_CACHE: dict[str, tuple[list[str], dict[str, list[str]], list[str], list[str], str]] = {}


async def enrich_search_plan(plan: SearchPlan) -> SearchPlan:
    settings = get_settings()
    cache_key = plan.original_query.strip().lower()
    if cache_key in _QUERY_EXPANSION_CACHE:
        paraphrases, multilingual_queries, focus_country_codes, strict_entity_phrases, search_mode = _QUERY_EXPANSION_CACHE[cache_key]
        return replace(
            plan,
            paraphrases=paraphrases,
            multilingual_queries=multilingual_queries,
            focus_country_codes=focus_country_codes,
            strict_entity_phrases=strict_entity_phrases,
            search_mode=search_mode,
        )

    languages = [code for code in settings.query_expansion_languages if code in DEFAULT_LANGUAGE_LABELS]
    multilingual_queries = {code: [] for code in languages}
    paraphrases: list[str] = []
    focus_country_codes = list(plan.focus_country_codes)
    strict_entity_phrases = list(plan.strict_entity_phrases)
    search_mode = plan.search_mode

    if settings.openai_api_key and settings.openai_enable_query_expansion:
        try:
            payload = await OpenAIAPIClient().chat_json(
                model=settings.openai_query_expansion_model,
                system_prompt=_system_prompt(languages),
                user_prompt=_user_prompt(plan, languages),
                schema_name="multilingual_query_expansion",
                schema=QUERY_EXPANSION_SCHEMA,
            )
            paraphrases = _dedupe_texts(payload.get("paraphrases", []), plan.original_query)
            multilingual_queries = {
                code: _dedupe_texts(
                    (payload.get("multilingual_queries") or {}).get(code, []),
                    plan.original_query,
                    include_original=False,
                )
                for code in languages
            }
            focus_country_codes = _normalize_country_codes(payload.get("focus_country_codes", [])) or focus_country_codes
            strict_entity_phrases = _dedupe_texts(
                (payload.get("strict_entity_phrases") or []) + strict_entity_phrases,
                plan.original_query,
            )[:12]
            candidate_mode = str(payload.get("search_mode") or "").strip().lower()
            if candidate_mode in {"broad", "strict_entity"}:
                search_mode = candidate_mode
        except OpenAIAPIError:
            paraphrases = []
            multilingual_queries = {code: [] for code in languages}

    if not paraphrases:
        paraphrases = _fallback_paraphrases(plan)

    if not any(multilingual_queries.values()):
        multilingual_queries = _fallback_multilingual_queries(plan, languages)

    # Guarantee that English search variants always exist for cross-lingual providers.
    multilingual_queries["en"] = _dedupe_texts(
        multilingual_queries.get("en", []) + [plan.original_query, *strict_entity_phrases[:2], *paraphrases[:2], plan.keyword_query],
        plan.original_query,
    )

    _QUERY_EXPANSION_CACHE[cache_key] = (
        paraphrases,
        multilingual_queries,
        focus_country_codes,
        strict_entity_phrases,
        search_mode,
    )
    return replace(
        plan,
        paraphrases=paraphrases,
        multilingual_queries=multilingual_queries,
        focus_country_codes=focus_country_codes,
        strict_entity_phrases=strict_entity_phrases,
        search_mode=search_mode,
    )


def _system_prompt(languages: list[str]) -> str:
    targets = ", ".join(f"{code} ({DEFAULT_LANGUAGE_LABELS[code]})" for code in languages)
    return (
        "You are a multilingual retrieval strategist for global media monitoring. "
        "Expand the user's event query conservatively. Keep the same factual meaning. "
        "When the query is about a very specific chokepoint, corridor, named route, treaty, visit, summit, or infrastructure object, "
        "treat it as a strict entity search and preserve that entity explicitly. "
        "Generate concise paraphrases that reflect how journalists might describe the same event, "
        "including softer or indirect phrasings such as blockade, disruption, closure, restriction, suspension, "
        "or routing impact when appropriate. "
        "Return short search-ready strings only. "
        f"Provide multilingual search variants for these languages: {targets}. "
        "Also infer which countries' media are most likely to carry direct coverage and list them as ISO-like country codes or country names. "
        "Do not invent new actors or claims."
    )


def _user_prompt(plan: SearchPlan, languages: list[str]) -> str:
    language_labels = {code: DEFAULT_LANGUAGE_LABELS[code] for code in languages}
    return (
        "{\n"
        f'  "query": {plan.original_query!r},\n'
        f'  "expanded_query": {plan.expanded_query!r},\n'
        f'  "keyword_query": {plan.keyword_query!r},\n'
        f'  "anchor_terms": {plan.anchor_terms!r},\n'
        f'  "entity_aliases": {plan.entity_aliases!r},\n'
        f'  "search_mode": {plan.search_mode!r},\n'
        f'  "focus_country_codes": {plan.focus_country_codes!r},\n'
        f'  "strict_entity_phrases": {plan.strict_entity_phrases!r},\n'
        f'  "target_languages": {language_labels!r}\n'
        "}\n"
        "Return up to 4 paraphrases, up to 2 search strings per target language, a search_mode, up to 8 focus_country_codes, "
        "and up to 8 strict_entity_phrases."
    )


def _fallback_paraphrases(plan: SearchPlan) -> list[str]:
    candidates = [
        *plan.strict_entity_phrases[:2],
        plan.expanded_query,
        plan.keyword_query,
        " ".join([*plan.entity_terms[:4], *plan.action_terms[:3]]).strip(),
        " ".join([*plan.action_terms[:3], *plan.entity_terms[:4]]).strip(),
    ]
    return _dedupe_texts(candidates, plan.original_query)[:4]


def _fallback_multilingual_queries(plan: SearchPlan, languages: list[str]) -> dict[str, list[str]]:
    queries = {code: [] for code in languages}
    seeds = _dedupe_texts(
        [plan.original_query, *plan.strict_entity_phrases[:2], *plan.paraphrases[:2], plan.keyword_query],
        plan.original_query,
    )
    for code in languages:
        if code == "en":
            queries[code] = _dedupe_texts([plan.original_query, *seeds], plan.original_query)[:3]
            continue

        translated: list[str] = []
        for text in seeds[:2] or [plan.original_query]:
            try:
                translated_text = GoogleTranslator(source="auto", target=code).translate(text)
            except Exception:
                translated_text = None
            if translated_text:
                translated.append(" ".join(translated_text.split()).strip())
        queries[code] = _dedupe_texts(translated, plan.original_query, include_original=False)[:2]
    return queries


def _dedupe_texts(values: list[str], original_query: str, *, include_original: bool = True) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    original_normalized = " ".join(original_query.split()).strip().lower()
    for value in values:
        normalized = " ".join((value or "").split()).strip()
        if len(normalized) < 3:
            continue
        if normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        deduped.append(normalized)
    if include_original and original_normalized and not any(value.lower() == original_normalized for value in deduped):
        deduped.insert(0, " ".join(original_query.split()).strip())
    return deduped


def _normalize_country_codes(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        code = normalize_country_code(str(value))
        if code:
            normalized.append(code)
    return list(dict.fromkeys(normalized))
