from __future__ import annotations

from dataclasses import dataclass
import re

from app.core.countries import normalize_country_code


STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "with",
    "for",
    "in",
    "on",
    "at",
    "from",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "that",
    "this",
    "as",
    "how",
    "what",
    "when",
    "where",
    "why",
    "по",
    "о",
    "об",
    "в",
    "во",
    "на",
    "из",
    "для",
    "от",
    "до",
    "над",
    "под",
    "при",
    "и",
    "или",
    "что",
    "это",
    "как",
    "когда",
    "где",
    "кто",
    "ли",
    "с",
    "со",
    "у",
}

ENTITY_ALIASES = {
    "united states": ["us", "u.s.", "usa", "america", "american", "washington"],
    "china": ["prc", "chinese", "beijing"],
    "russia": ["russian", "moscow", "kremlin"],
    "ukraine": ["ukrainian", "kyiv", "kiev"],
    "european union": ["eu", "europe"],
    "united kingdom": ["uk", "britain", "british", "london"],
    "iran": ["iranian", "tehran"],
    "israel": ["israeli", "jerusalem"],
    "india": ["indian", "new delhi"],
    "turkey": ["turkish", "ankara"],
}

GEOPOLITICAL_ENTITY_HINTS = {
    "zangezur corridor": {
        "patterns": [
            "zangezur",
            "зангезур",
            "зангезурск",
            "syunik corridor",
            "сюник",
            "meghri corridor",
            "мегри",
        ],
        "aliases": [
            "Zangezur corridor",
            "Zangezur transport corridor",
            "Syunik corridor",
            "Meghri corridor",
            "Зангезурский коридор",
            "Сюникский коридор",
            "Мегринский коридор",
        ],
        "focus_countries": ["AZ", "AM", "TR", "RU", "IR", "GE", "US", "GB", "FR"],
    },
    "lachin corridor": {
        "patterns": ["lachin corridor", "lachin", "лачин", "бердзор"],
        "aliases": ["Lachin corridor", "Berdzor corridor", "Лачинский коридор"],
        "focus_countries": ["AZ", "AM", "RU", "TR", "IR", "FR", "US", "GB"],
    },
    "strait of hormuz": {
        "patterns": ["strait of hormuz", "hormuz", "ормуз"],
        "aliases": ["Strait of Hormuz", "Hormuz Strait", "Ормузский пролив"],
        "focus_countries": ["IR", "US", "GB", "AE", "SA", "QA", "IL"],
    },
    "suez canal": {
        "patterns": ["suez canal", "suez", "суэц"],
        "aliases": ["Suez Canal", "Суэцкий канал"],
        "focus_countries": ["EG", "US", "GB", "FR", "SA", "AE"],
    },
}


@dataclass(slots=True)
class SearchPlan:
    original_query: str
    expanded_query: str
    keyword_query: str
    anchor_terms: list[str]
    entity_aliases: dict[str, list[str]]
    core_terms: list[str]
    entity_terms: list[str]
    entity_patterns: list[str]
    action_terms: list[str]
    paraphrases: list[str]
    multilingual_queries: dict[str, list[str]]
    focus_country_codes: list[str]
    strict_entity_phrases: list[str]
    search_mode: str


def build_search_plan(query: str) -> SearchPlan:
    lowered = query.lower()
    entity_aliases: dict[str, list[str]] = {}
    entity_patterns: list[str] = []
    for canonical, aliases in ENTITY_ALIASES.items():
        if canonical in lowered or any(alias in lowered for alias in aliases):
            entity_aliases[canonical] = aliases

    focus_country_codes: list[str] = []
    strict_entity_phrases: list[str] = []
    search_mode = "broad"
    for canonical, hint in GEOPOLITICAL_ENTITY_HINTS.items():
        if any(pattern in lowered for pattern in hint["patterns"]):
            entity_aliases[canonical] = _dedupe(list(entity_aliases.get(canonical, [])) + hint["aliases"])
            focus_country_codes = _normalize_country_codes(hint["focus_countries"])
            strict_entity_phrases = _dedupe(hint["aliases"] + [canonical])
            entity_patterns.extend(hint["patterns"])
            search_mode = "strict_entity"

    raw_core_terms = _extract_anchor_terms(query)
    alias_terms = [
        alias
        for aliases in entity_aliases.values()
        for alias in aliases
        if alias not in lowered
    ]
    alias_terms = _dedupe(alias_terms)

    expanded_parts = [query]
    if alias_terms:
        expanded_parts.append(" ".join(alias_terms[:6]))
    expanded_query = " ".join(part for part in expanded_parts if part).strip()

    entity_terms = _dedupe(
        list(entity_aliases.keys())
        + [alias for aliases in entity_aliases.values() for alias in aliases]
    )
    entity_patterns = _dedupe(entity_patterns + [term.lower() for term in entity_terms if len(term) >= 4])
    entity_lexemes = set()
    for term in entity_terms:
        entity_lexemes.update(term.split())
    core_terms = [term for term in raw_core_terms if not _looks_like_entity_term(term, entity_lexemes, entity_patterns)]
    keyword_terms = _dedupe(raw_core_terms + list(entity_aliases.keys()) + alias_terms)
    action_terms = [term for term in core_terms if term not in entity_lexemes]
    keyword_query = " ".join(keyword_terms[:10]) or query

    return SearchPlan(
        original_query=query,
        expanded_query=expanded_query,
        keyword_query=keyword_query,
        anchor_terms=keyword_terms[:12],
        entity_aliases=entity_aliases,
        core_terms=core_terms[:8],
        entity_terms=entity_terms[:12],
        entity_patterns=entity_patterns[:16],
        action_terms=action_terms[:8],
        paraphrases=[],
        multilingual_queries={},
        focus_country_codes=focus_country_codes,
        strict_entity_phrases=strict_entity_phrases[:12],
        search_mode=search_mode,
    )


def plan_queries_for_provider(provider: str, plan: SearchPlan) -> list[str]:
    multilingual = _flatten_multilingual_queries(plan, provider)
    if plan.search_mode == "strict_entity":
        regional_queries = _regional_focus_queries(plan)
        strict_queries = _dedupe(
            [
                plan.original_query,
                *plan.strict_entity_phrases[:4],
                *regional_queries[:4],
                *plan.paraphrases[:4],
                *multilingual[:4],
                plan.keyword_query,
            ]
        )
        if provider == "open_web":
            open_web_queries = _dedupe(
                [
                    plan.original_query,
                    *plan.strict_entity_phrases[:5],
                    *regional_queries[:10],
                    *plan.paraphrases[:4],
                    *multilingual[:6],
                    plan.keyword_query,
                ]
            )
            return open_web_queries[:16]
        if provider == "x":
            return strict_queries[:5]
        if provider == "telegram":
            return strict_queries[:5]
        return strict_queries[:8]

    if provider in {"x"}:
        queries = [plan.original_query, *plan.paraphrases[:2], *multilingual[:2]]
        return _dedupe(queries)[:4]

    if provider in {"telegram"}:
        queries = [plan.keyword_query, plan.original_query, *plan.paraphrases[:1], *multilingual[:2]]
        return _dedupe(queries)[:4]

    queries = [plan.original_query]
    if plan.expanded_query != plan.original_query:
        queries.append(plan.expanded_query)
    if plan.keyword_query not in queries:
        queries.append(plan.keyword_query)
    queries.extend(plan.paraphrases[:3])
    queries.extend(multilingual[:4])
    return _dedupe(queries)[:7]


def _flatten_multilingual_queries(plan: SearchPlan, provider: str) -> list[str]:
    if not plan.multilingual_queries:
        return []

    if provider in {"telegram", "x"}:
        preferred_languages = ("en", "ru", "ar", "fa", "tr")
    else:
        preferred_languages = ("en", "ar", "fa", "tr", "zh", "ru")

    flattened: list[str] = []
    for language in preferred_languages:
        flattened.extend(plan.multilingual_queries.get(language, []))
    return _dedupe(flattened)


def _extract_anchor_terms(query: str) -> list[str]:
    tokens = re.findall(r"\b[\w.-]{2,}\b", query.lower())
    return _dedupe([token for token in tokens if token not in STOPWORDS])


def _normalize_country_codes(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        code = normalize_country_code(value)
        if code:
            normalized.append(code)
    return _dedupe(normalized)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _looks_like_entity_term(token: str, entity_lexemes: set[str], entity_patterns: list[str]) -> bool:
    lowered = token.lower().strip()
    if not lowered:
        return False
    if lowered in entity_lexemes:
        return True
    return any(pattern and (pattern in lowered or lowered in pattern) for pattern in entity_patterns)


def _regional_focus_queries(plan: SearchPlan) -> list[str]:
    if plan.search_mode != "strict_entity" or not plan.strict_entity_phrases:
        return []

    primary_phrase = plan.strict_entity_phrases[0]
    action_hints = _action_hints(plan.action_terms)
    country_labels = [_country_query_label(code) for code in plan.focus_country_codes[:6]]
    regional_focus = [label for label in country_labels if label]
    query_variants = [
        f"{primary_phrase} agreement",
        f"{primary_phrase} memorandum",
        f"signed agreement on {primary_phrase}",
        f"{primary_phrase} signed",
    ]
    for label in regional_focus[:4]:
        query_variants.extend(
            [
                f"{primary_phrase} {label} agreement",
                f"{primary_phrase} {label} memorandum",
                f"{label} {primary_phrase}",
            ]
        )
    if len(regional_focus) >= 2:
        query_variants.extend(
            [
                f"{primary_phrase} {regional_focus[0]} {regional_focus[1]} agreement",
                f"{regional_focus[0]} {regional_focus[1]} {primary_phrase}",
            ]
        )
    for action_hint in action_hints:
        query_variants.append(f"{primary_phrase} {action_hint}")
    return _dedupe(query_variants)


def _action_hints(action_terms: list[str]) -> list[str]:
    hints = {
        "подписание": ["agreement signing", "signed agreement"],
        "соглашение": ["agreement", "deal"],
        "договор": ["agreement", "deal"],
        "меморандум": ["memorandum"],
        "визит": ["official visit"],
        "переговоры": ["talks"],
    }
    resolved: list[str] = []
    for term in action_terms:
        lowered = term.lower().strip()
        if lowered in hints:
            resolved.extend(hints[lowered])
    return _dedupe(resolved)


def _country_query_label(code: str) -> str | None:
    labels = {
        "AZ": "Azerbaijan",
        "AM": "Armenia",
        "TR": "Turkey",
        "RU": "Russia",
        "IR": "Iran",
        "GE": "Georgia",
        "US": "United States",
        "GB": "United Kingdom",
        "FR": "France",
    }
    return labels.get(code)
