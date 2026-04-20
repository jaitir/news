from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.core.countries import normalize_country_code
from app.core.source_registry import resolve_source_profile
from app.services.connectors.base import ConnectorItem
from app.services.pivot_translation import PivotTranslator, combine_for_translation, is_english
from app.services.query_planner import SearchPlan


NEGATIVE_WORDS = {
    "war",
    "crisis",
    "collapse",
    "threat",
    "attack",
    "fear",
    "sanction",
    "loss",
    "panic",
    "blockade",
}
POSITIVE_WORDS = {
    "deal",
    "agreement",
    "growth",
    "peace",
    "progress",
    "cooperation",
    "recovery",
    "support",
    "resume",
}
EMOTION_POSITIVE_PATTERNS: dict[str, int] = {
    "peace": 18,
    "ceasefire": 17,
    "deal": 11,
    "agreement": 11,
    "accord": 11,
    "treaty": 11,
    "growth": 12,
    "recover": 11,
    "rebound": 11,
    "progress": 9,
    "support": 8,
    "resume": 8,
    "stabil": 9,
    "cooperat": 8,
    "success": 10,
    "boost": 8,
    "соглаш": 11,
    "договор": 11,
    "перемир": 17,
    "мир": 18,
    "рост": 12,
    "восстанов": 11,
    "прогресс": 9,
    "поддерж": 8,
    "стабилиз": 9,
    "успех": 10,
    "accord": 11,
    "croiss": 12,
    "soutien": 8,
    "paix": 18,
    "progres": 9,
    "wachstum": 12,
    "frieden": 18,
    "unterstutz": 8,
    "erhol": 11,
    "acuerd": 11,
    "crecim": 12,
    "apoyo": 8,
    "paz": 18,
    "avance": 9,
    "anlas": 11,
    "buyume": 12,
    "destek": 8,
    "baris": 18,
    "ilerle": 9,
    "اتفاق": 11,
    "نمو": 12,
    "دعم": 8,
    "سلام": 18,
    "تقدم": 9,
    "استقرار": 9,
    "تعاف": 11,
    "توافق": 11,
    "رشد": 12,
    "حمایت": 8,
    "صلح": 18,
    "پیشرفت": 9,
    "ثبات": 9,
    "بهبود": 11,
    "协议": 11,
    "增长": 12,
    "支持": 8,
    "和平": 18,
    "进展": 9,
    "稳定": 9,
    "恢复": 11,
}
EMOTION_NEGATIVE_PATTERNS: dict[str, int] = {
    "war": 18,
    "conflict": 15,
    "crisis": 15,
    "attack": 16,
    "strike": 14,
    "missile": 13,
    "threat": 14,
    "fear": 11,
    "panic": 13,
    "collapse": 16,
    "plunge": 14,
    "blockade": 14,
    "sanction": 10,
    "death": 16,
    "killed": 17,
    "injur": 13,
    "explos": 15,
    "violen": 13,
    "tension": 11,
    "shortage": 12,
    "войн": 18,
    "конфликт": 15,
    "криз": 15,
    "атак": 16,
    "удар": 14,
    "ракет": 13,
    "угроз": 14,
    "страх": 11,
    "паник": 13,
    "обвал": 16,
    "паден": 14,
    "блокад": 14,
    "санкц": 10,
    "гибел": 16,
    "убит": 17,
    "взрыв": 15,
    "насил": 13,
    "напряж": 11,
    "guerre": 18,
    "conflit": 15,
    "crise": 15,
    "attaque": 16,
    "menace": 14,
    "panique": 13,
    "effondr": 16,
    "krieg": 18,
    "konflikt": 15,
    "angriff": 16,
    "drohung": 14,
    "panik": 13,
    "sanktion": 10,
    "guerra": 18,
    "conflicto": 15,
    "ataque": 16,
    "amenaz": 14,
    "violencia": 13,
    "crisis": 15,
    "savas": 18,
    "kriz": 15,
    "saldir": 16,
    "tehdit": 14,
    "gergin": 11,
    "حرب": 18,
    "صراع": 15,
    "أزمة": 15,
    "هجوم": 16,
    "تهديد": 14,
    "خوف": 11,
    "انهيار": 16,
    "عقوبات": 10,
    "قتيل": 17,
    "انفجار": 15,
    "توتر": 11,
    "عنف": 13,
    "جنگ": 18,
    "بحران": 15,
    "حمله": 16,
    "تهدید": 14,
    "ترس": 11,
    "سقوط": 16,
    "تحریم": 10,
    "کشته": 17,
    "انفجار": 15,
    "تنش": 11,
    "战争": 18,
    "冲突": 15,
    "危机": 15,
    "袭击": 16,
    "威胁": 14,
    "恐慌": 13,
    "崩溃": 16,
    "制裁": 10,
    "死亡": 17,
    "爆炸": 15,
    "紧张": 11,
}
EMOTION_DAMPENING_PATTERNS = {
    "analysis",
    "explainer",
    "what it means",
    "commentary",
    "разбор",
    "объясня",
    "обзор",
    "анализ",
    "explica",
    "analyse",
    "analisi",
}
NARRATIVE_BUCKETS = {
    "diplomatic": {"agreement", "deal", "talks", "meeting", "treaty", "official", "negotiation", "ceasefire"},
    "economic": {"market", "trade", "tariff", "economy", "supply", "business", "investor", "budget", "blockade"},
    "security": {"military", "attack", "weapon", "security", "border", "conflict", "war", "navy", "missile"},
    "governance": {"law", "court", "policy", "regulation", "election", "government", "congress"},
    "social_reaction": {"protest", "commentators", "public", "backlash", "reaction", "social", "outrage"},
}
WIRE_SOURCE_MARKERS = {
    "reuters",
    "associated press",
    "ap news",
    "agence france-presse",
    "afp",
    "tass",
    "efe",
    "dpa",
    "pa media",
    "kyodo",
}
PROVIDER_WEIGHTS = {
    "event_registry": 0.98,
    "guardian": 0.94,
    "media_cloud": 0.92,
    "gdelt": 0.84,
    "open_web": 0.72,
    "gnews": 0.81,
    "newsdata": 0.76,
    "x": 0.54,
    "telegram": 0.52,
    "mock": 0.1,
}
SOURCE_TYPE_WEIGHTS = {
    "news": 1.0,
    "social": 0.72,
    "telegram": 0.7,
}
NEGATION_CUES = {"not", "deny", "denies", "false", "reject", "rejected", "debunk", "no"}
SUPPORT_CUES = {"confirm", "confirmed", "supports", "signed", "agreed", "resume", "announced", "deal"}
EVENT_ABSENCE_CUES = {
    "подписание договора не",
    "подписание не",
    "соглашение не упоминается",
    "договор не упоминается",
    "не упоминается",
    "не говорится",
    "does not mention signing",
    "signing is not mentioned",
    "agreement is not mentioned",
    "not about signing",
}


async def enrich_items(items: list[ConnectorItem], query: str, search_plan: SearchPlan, enable_pivot_translation: bool = True) -> list[dict]:
    translator = PivotTranslator() if enable_pivot_translation else None
    title_clusters, summary_clusters = _build_originality_clusters(items)

    enriched: list[dict] = []
    for item in items:
        raw = asdict(item)
        pivot_summary, was_translated = await _pivot_summary_for_item(item, translator)
        analysis_text = f"{item.title} {pivot_summary}".lower()
        source_profile = resolve_source_profile(
            source_name=item.source_name,
            url=item.url,
            handle=(item.raw_payload or {}).get("_source_handle"),
            country_hint=item.source_country,
        )
        query_alignment = infer_query_alignment(analysis_text, search_plan)
        stance = infer_stance_to_query(analysis_text, search_plan)
        originality = infer_originality(item, title_clusters, summary_clusters)
        is_curated_source = bool((item.raw_payload or {}).get("_curated_source"))
        weighted_score = compute_weighted_score(
            item=item,
            query_alignment=query_alignment,
            originality=originality,
            is_curated_source=is_curated_source,
        )
        enriched.append(
            {
                **raw,
                "pivot_summary": pivot_summary,
                "pivot_language": "en" if pivot_summary else item.language,
                "was_translated": was_translated,
                "query_alignment": query_alignment,
                "stance": stance,
                "originality": originality,
                "weighted_score": weighted_score,
                "is_curated_source": is_curated_source,
                "source_profile": source_profile,
                "exact_quotes": _extract_exact_quotes(f"{item.title}\n{item.summary}"),
                "narrative": infer_narrative(analysis_text),
                "emotion": infer_emotion(analysis_text),
            }
        )

    focused_items = apply_retrieval_focus(deduplicate(enriched), search_plan, stage="pre")
    return filter_for_quality(focused_items, search_plan)


def finalize_items(items: list[dict], search_plan: SearchPlan | None = None) -> list[dict]:
    focused_items = apply_retrieval_focus(deduplicate(items), search_plan, stage="post")
    return filter_for_quality(focused_items, search_plan)


def recompute_row_weight(row: dict) -> int:
    item = ConnectorItem(
        provider=row["provider"],
        source_type=row["source_type"],
        source_name=row["source_name"],
        source_country=row.get("source_country"),
        language=row.get("language"),
        title=row["title"],
        url=row["url"],
        summary=row["summary"],
        published_at=row["published_at"],
        ranking_score=row.get("ranking_score", 0),
        raw_payload=row.get("raw_payload") or {},
    )
    return compute_weighted_score(
        item=item,
        query_alignment=row.get("query_alignment", "low"),
        originality=row.get("originality", "unknown"),
        is_curated_source=bool(row.get("is_curated_source", False)),
    )


def infer_narrative(text: str) -> str:
    scores: Counter[str] = Counter()
    tokens = set(re.findall(r"\b[\w-]+\b", text))
    for label, keywords in NARRATIVE_BUCKETS.items():
        scores[label] = len(tokens & keywords)
    if not scores or max(scores.values()) == 0:
        return "general framing"
    return scores.most_common(1)[0][0].replace("_", " ")


def infer_emotion(text: str) -> str:
    score = infer_emotion_score(text)
    if score >= 18:
        return "positive"
    if score <= -18:
        return "negative"
    return "neutral"


def infer_emotion_score(primary_text: str, secondary_text: str = "") -> int:
    primary_score = _score_emotion_text(primary_text, weight=1.45)
    secondary_score = _score_emotion_text(secondary_text, weight=1.0)
    raw_score = primary_score + secondary_score
    if raw_score == 0 and secondary_text:
        raw_score = _score_emotion_text(f"{primary_text} {secondary_text}", weight=1.15)
    if raw_score == 0:
        return 0

    scaled = int(round(100 * math.tanh(raw_score / 28)))
    if scaled == 0:
        return 6 if raw_score > 0 else -6
    return max(-100, min(100, scaled))


def infer_query_alignment(text: str, search_plan: SearchPlan) -> str:
    if not search_plan.core_terms and not search_plan.entity_terms:
        return "low"
    tokens = set(re.findall(r"\b[\w-]+\b", text))
    strict_hits = _strict_phrase_matches(text, search_plan.strict_entity_phrases)
    entity_hits = _entity_match_count(text, tokens, search_plan.entity_terms, search_plan.entity_patterns)
    action_hits = len(tokens & set(search_plan.action_terms))
    core_hits = len(tokens & set(search_plan.core_terms))
    ratio = core_hits / max(len(search_plan.core_terms), 1)
    if search_plan.search_mode == "strict_entity":
        if strict_hits >= 1 and action_hits >= 1:
            return "high"
        if strict_hits >= 1 and core_hits >= 1:
            return "medium"
        if strict_hits >= 1:
            return "low"
        if entity_hits >= 2 and action_hits >= 1:
            return "medium"
        if entity_hits >= 1 and (action_hits >= 1 or core_hits >= 1):
            return "low"
        return "low"
    if search_plan.original_query.lower() in text or (entity_hits >= 2 and action_hits >= 1):
        return "high"
    if ratio >= 0.45 or (entity_hits >= 1 and action_hits >= 1) or (entity_hits >= 2 and core_hits >= 2):
        return "medium"
    if entity_hits >= 1 or core_hits >= 1:
        return "low"
    return "low"


def infer_stance_to_query(text: str, search_plan: SearchPlan) -> str:
    tokens = set(re.findall(r"\b[\w-]+\b", text))
    matched_terms = tokens & set(search_plan.core_terms)
    entity_hits = _entity_matches(text, tokens, search_plan.entity_terms, search_plan.entity_patterns)
    action_hits = tokens & set(search_plan.action_terms)
    has_negation = bool(tokens & NEGATION_CUES)
    has_support = bool(tokens & SUPPORT_CUES)

    if (matched_terms or entity_hits) and has_negation and has_support:
        return "mixed"
    if (entity_hits or action_hits) and has_negation:
        return "disputes"
    if entity_hits and (action_hits or has_support):
        return "supports"
    if infer_query_alignment(text, search_plan) == "high":
        return "supports"
    return "unclear"


def infer_originality(item: ConnectorItem, title_clusters: dict[str, int], summary_clusters: dict[str, int]) -> str:
    if item.source_type in {"social", "telegram"}:
        return "social primary"

    source_marker = item.source_name.lower()
    domain = _extract_domain(item.url)
    if any(marker in source_marker or marker in domain for marker in WIRE_SOURCE_MARKERS):
        return "syndicated"

    title_key = _normalize_text(item.title)
    summary_key = _normalize_text(item.summary[:240])
    if title_clusters.get(title_key, 0) > 1 or summary_clusters.get(summary_key, 0) > 1:
        return "syndicated"
    if item.summary and len(item.summary) > 120:
        return "original"
    return "unknown"


def compute_weighted_score(
    item: ConnectorItem,
    query_alignment: str,
    originality: str,
    is_curated_source: bool,
) -> int:
    provider_weight = PROVIDER_WEIGHTS.get(item.provider, 0.65)
    source_type_weight = SOURCE_TYPE_WEIGHTS.get(item.source_type, 0.8)
    recency_days = max((datetime.now(timezone.utc) - item.published_at).total_seconds() / 86400, 0)
    recency_points = max(0, 20 - int(recency_days * 1.8))
    if item.provider == "open_web":
        recency_points = min(recency_points, 6)
    social_signal = min(18, int(math.log1p(max(item.ranking_score, 0)) * 3.2)) if item.ranking_score else 0
    alignment_points = {"high": 34, "medium": 16, "low": -10}.get(query_alignment, -12)
    originality_points = {
        "original": 10,
        "syndicated": -6,
        "social primary": 0,
        "unknown": 0,
    }.get(originality, 0)
    curated_bonus = 8 if is_curated_source else 0
    score = int(provider_weight * 34 + source_type_weight * 12 + recency_points + social_signal + alignment_points + originality_points + curated_bonus)
    if item.source_type in {"social", "telegram"} and query_alignment == "low":
        score -= 24
    if item.source_type in {"social", "telegram"} and query_alignment == "medium":
        score -= 10
    if item.source_type == "news" and query_alignment == "low":
        score -= 12
    if item.source_type in {"social", "telegram"} and _is_digest_like(f"{item.title}\n{item.summary}"):
        score -= 22
    return max(1, min(score, 100))


def deduplicate(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    alignment_rank = {"high": 3, "medium": 2, "low": 1}
    for item in sorted(
        items,
        key=lambda row: (alignment_rank.get(row["query_alignment"], 0), row["weighted_score"], row["published_at"]),
        reverse=True,
    ):
        fingerprint = normalize_fingerprint(item["url"], item["title"])
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(item)
    return deduped


def filter_for_quality(items: list[dict], search_plan: SearchPlan | None = None) -> list[dict]:
    if search_plan and search_plan.search_mode == "strict_entity":
        direct_items = [item for item in items if item.get("retrieval_bucket") == "direct"]
        contextual_items = [item for item in items if item.get("retrieval_bucket") == "contextual"]
        if direct_items:
            if len(direct_items) >= 8:
                return direct_items
            return direct_items + contextual_items[: max(4, 10 - len(direct_items))]
        if contextual_items:
            return contextual_items[: min(len(contextual_items), 12)]

    strong_items = [
        item
        for item in items
        if item["query_alignment"] in {"high", "medium"}
        or float(item.get("semantic_query_score") or 0.0) >= 0.6
    ]
    if len(strong_items) < 6:
        return items

    supplemental_items = [
        item
        for item in items
        if item not in strong_items
        and (
            (
                item["query_alignment"] == "low"
                and float(item.get("semantic_query_score") or 0.0) >= 0.38
                and (
                    item["is_curated_source"]
                    or item["provider"] in {"event_registry", "guardian", "media_cloud", "gdelt", "gnews", "newsdata"}
                )
            )
            or (
                item["provider"] in {"event_registry", "guardian", "media_cloud", "gdelt", "gnews", "newsdata"}
                and item.get("weighted_score", 0) >= 58
            )
        )
    ]
    overflow_cap = 12 if len(strong_items) < 24 else 18
    return strong_items + supplemental_items[:overflow_cap]


def normalize_fingerprint(url: str, title: str) -> str:
    normalized_title = _normalize_text(title)[:120]
    normalized_url = url.split("?")[0].rstrip("/")
    return f"{normalized_url}|{normalized_title}"


def build_narrative_groups(items: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in items:
        label = item.get("cluster_label") or item["narrative"]
        groups[(label, item["emotion"])].append(item)

    response: list[dict] = []
    for (narrative, emotion), group_items in groups.items():
        top_sources = Counter(item["source_name"] for item in group_items).most_common(3)
        weighted_count = round(sum(item.get("weighted_score", 0) for item in group_items) / 100, 2)
        response.append(
            {
                "narrative": narrative,
                "emotion": emotion,
                "count": len(group_items),
                "weighted_count": weighted_count,
                "top_sources": [name for name, _ in top_sources],
            }
        )

    response.sort(key=lambda group: (group["weighted_count"], group["count"]), reverse=True)
    return response


def build_provider_summary(statuses: list[dict]) -> dict:
    return {
        row["provider"]: {
            "status": row["status"],
            "message": row["message"],
            "count": row["count"],
        }
        for row in statuses
    }


async def _pivot_summary_for_item(item: ConnectorItem, translator: PivotTranslator | None) -> tuple[str, bool]:
    original = combine_for_translation([item.title, item.summary], max_chars=900)
    if not original:
        return "", False
    if not translator or is_english(item.language):
        return original, False
    return await translator.to_english(original, item.language)


def _build_originality_clusters(items: list[ConnectorItem]) -> tuple[dict[str, int], dict[str, int]]:
    title_clusters: Counter[str] = Counter()
    summary_clusters: Counter[str] = Counter()
    for item in items:
        title_key = _normalize_text(item.title)
        if title_key:
            title_clusters[title_key] += 1
        summary_key = _normalize_text(item.summary[:240])
        if summary_key:
            summary_clusters[summary_key] += 1
    return dict(title_clusters), dict(summary_clusters)


def _extract_domain(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    return hostname.lower().removeprefix("www.")


def _normalize_text(value: str) -> str:
    return re.sub(r"\W+", "", (value or "").lower())


def _normalize_emotion_text(value: str) -> str:
    lowered = unicodedata.normalize("NFKD", (value or "").lower())
    stripped = "".join(character for character in lowered if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", stripped).strip()


def _score_emotion_text(text: str, *, weight: float) -> float:
    normalized = _normalize_emotion_text(text)
    if not normalized:
        return 0.0

    tokens = re.findall(r"\b[\w-]+\b", normalized, flags=re.UNICODE)
    positive_total, positive_hits, positive_peak = _emotion_bucket_stats(
        normalized,
        tokens,
        EMOTION_POSITIVE_PATTERNS,
    )
    negative_total, negative_hits, negative_peak = _emotion_bucket_stats(
        normalized,
        tokens,
        EMOTION_NEGATIVE_PATTERNS,
    )

    raw_score = float(positive_total - negative_total)
    raw_score += (positive_hits - negative_hits) * 1.6
    raw_score += (positive_peak - negative_peak) * 0.32
    raw_score *= _emotion_dampening_factor(normalized)
    return raw_score * weight


def _emotion_bucket_stats(
    text: str,
    tokens: list[str],
    patterns: dict[str, int],
) -> tuple[int, int, int]:
    total = 0
    hit_count = 0
    peak = 0

    for pattern, weight in patterns.items():
        occurrences = min(2, _emotion_pattern_occurrences(text, tokens, pattern))
        if not occurrences:
            continue
        total += weight * occurrences
        hit_count += occurrences
        peak = max(peak, weight)

    return total, hit_count, peak


def _emotion_pattern_occurrences(text: str, tokens: list[str], pattern: str) -> int:
    if " " in pattern or _uses_direct_substring_matching(pattern):
        return text.count(pattern)
    return sum(1 for token in tokens if token.startswith(pattern))


def _uses_direct_substring_matching(pattern: str) -> bool:
    return any(
        "\u0600" <= character <= "\u06ff" or "\u4e00" <= character <= "\u9fff"
        for character in pattern
    )


def _emotion_dampening_factor(text: str) -> float:
    if any(pattern in text for pattern in EMOTION_DAMPENING_PATTERNS):
        return 0.72
    return 1.0


def _entity_match_count(text: str, tokens: set[str], entity_terms: list[str], entity_patterns: list[str]) -> int:
    return len(_entity_matches(text, tokens, entity_terms, entity_patterns))


def _entity_matches(text: str, tokens: set[str], entity_terms: list[str], entity_patterns: list[str]) -> set[str]:
    matches: set[str] = set()
    for term in entity_terms:
        normalized = term.lower().strip()
        if not normalized:
            continue
        if " " in normalized:
            if normalized in text:
                matches.add(normalized)
            continue
        if normalized in tokens:
            matches.add(normalized)
    for pattern in entity_patterns:
        normalized = pattern.lower().strip()
        if not normalized:
            continue
        if normalized in text or any(normalized in token or token in normalized for token in tokens if len(token) >= 4):
            matches.add(normalized)
    return matches


def _is_digest_like(text: str) -> bool:
    lowered = text.lower()
    bullet_markers = lowered.count("•") + lowered.count("👇") + lowered.count("\n-") + lowered.count("\n1.") + lowered.count("\n2.")
    digest_markers = {
        "news updates",
        "important data",
        "stocks to watch",
        "morning stock markets",
        "breaking news roundup",
    }
    return bullet_markers >= 3 or any(marker in lowered for marker in digest_markers)


def _extract_exact_quotes(text: str) -> list[str]:
    if not text:
        return []

    patterns = [
        r'"([^"\n]{12,260})"',
        r"“([^”\n]{12,260})”",
        r"«([^»\n]{12,260})»",
    ]
    quotes: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.findall(pattern, text):
            normalized = " ".join(match.split()).strip()
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            quotes.append(normalized)
    return quotes[:4]


def apply_retrieval_focus(items: list[dict], search_plan: SearchPlan | None, *, stage: str) -> list[dict]:
    if not search_plan or search_plan.search_mode != "strict_entity":
        return items

    direct_items: list[dict] = []
    contextual_items: list[dict] = []
    fallback_items: list[dict] = []
    focus_countries = set(search_plan.focus_country_codes)
    for item in items:
        row = dict(item)
        source_summary = row.get("summary") or row.get("pivot_summary", "")
        text = f"{row.get('title', '')} {source_summary}".lower()
        tokens = set(re.findall(r"\b[\w-]+\b", text))
        strict_hits = _strict_phrase_matches(text, search_plan.strict_entity_phrases)
        entity_hits = _entity_match_count(text, tokens, search_plan.entity_terms, search_plan.entity_patterns)
        action_hits = len(tokens & set(search_plan.action_terms))
        semantic_score = float(row.get("semantic_query_score") or 0.0)
        absence_cue = _has_event_absence_cue(text)
        near_event_signal = _has_near_event_signal(text)
        country_code = normalize_country_code(
            ((row.get("source_profile") or {}).get("country")) or row.get("source_country")
        )

        row["strict_entity_hits"] = strict_hits
        row["focus_country_match"] = bool(country_code and country_code in focus_countries)

        direct_match = not absence_cue and (
            strict_hits >= 1 and action_hits >= 1
        ) or (
            not absence_cue
            and search_plan.entity_terms
            and entity_hits >= 2
            and action_hits >= 1
            and (stage == "pre" or semantic_score >= 0.72)
        )
        contextual_match = (
            (
                row["focus_country_match"]
                or strict_hits >= 1
            )
            and (
                row.get("query_alignment") in {"medium", "high"}
                or (
                    row.get("query_alignment") == "low"
                    and row["focus_country_match"]
                    and strict_hits >= 1
                    and semantic_score >= 0.82
                )
            )
            and (not absence_cue or near_event_signal)
        )

        if direct_match:
            row["retrieval_bucket"] = "direct"
            direct_items.append(row)
            continue
        if contextual_match:
            row["retrieval_bucket"] = "contextual"
            contextual_items.append(row)
            continue

        if row["focus_country_match"] or strict_hits >= 1 or entity_hits >= 1:
            row["retrieval_bucket"] = "background"
            fallback_items.append(row)

    if direct_items:
        direct_items = _rank_focus_bucket(direct_items)
        contextual_items = _rank_focus_bucket(contextual_items)
        direct_items = _diversify_focus_items(direct_items)
        contextual_items = _diversify_focus_items(contextual_items)
        selected = direct_items + contextual_items[: max(4, 10 - len(direct_items))]
        selected = _backfill_focus_country_coverage(selected, contextual_items + fallback_items, focus_countries)
        return _backfill_provider_diversity(selected, contextual_items + fallback_items)
        

    contextual_items = _rank_focus_bucket(contextual_items)
    contextual_items = _diversify_focus_items(contextual_items)
    if contextual_items:
        selected = contextual_items[: min(len(contextual_items), 12)]
        selected = _backfill_focus_country_coverage(selected, fallback_items, focus_countries)
        return _backfill_provider_diversity(selected, fallback_items)

    fallback_items = _rank_focus_bucket(fallback_items)
    fallback_items = _diversify_focus_items(fallback_items)
    if fallback_items:
        selected = fallback_items[: min(len(fallback_items), 10)]
        selected = _backfill_focus_country_coverage(selected, fallback_items, focus_countries)
        return _backfill_provider_diversity(selected, fallback_items)

    return items[: min(len(items), 12)]


def _strict_phrase_matches(text: str, strict_phrases: list[str]) -> int:
    lowered = text.lower()
    matches = 0
    for phrase in strict_phrases:
        normalized = phrase.lower().strip()
        if normalized and normalized in lowered:
            matches += 1
    return matches


def _rank_focus_bucket(items: list[dict]) -> list[dict]:
    alignment_rank = {"high": 3, "medium": 2, "low": 1}
    return sorted(
        items,
        key=lambda item: (
            item.get("strict_entity_hits", 0),
            1 if item.get("focus_country_match") else 0,
            alignment_rank.get(item.get("query_alignment", "low"), 0),
            float(item.get("semantic_query_score") or 0.0),
            item.get("weighted_score", 0),
            item.get("published_at"),
        ),
        reverse=True,
    )


def _diversify_focus_items(items: list[dict]) -> list[dict]:
    kept: list[dict] = []
    per_source: Counter[str] = Counter()
    per_provider: Counter[str] = Counter()
    per_cluster_country: Counter[tuple[str, str]] = Counter()
    for item in items:
        source_key = (item.get("source_name") or "").lower()
        provider_key = (item.get("provider") or "").lower()
        cluster_key = item.get("cluster_label") or item.get("narrative") or "unknown"
        country_key = normalize_country_code(
            ((item.get("source_profile") or {}).get("country")) or item.get("source_country")
        ) or "unknown"
        if source_key and per_source[source_key] >= 2:
            continue
        if provider_key and per_provider[provider_key] >= 4:
            continue
        if per_cluster_country[(cluster_key, country_key)] >= 2:
            continue
        kept.append(item)
        if source_key:
            per_source[source_key] += 1
        if provider_key:
            per_provider[provider_key] += 1
        per_cluster_country[(cluster_key, country_key)] += 1
    return kept or items


def _backfill_focus_country_coverage(
    selected: list[dict],
    pool: list[dict],
    focus_countries: set[str],
) -> list[dict]:
    if not selected or not focus_countries:
        return selected

    covered = {
        normalize_country_code(((item.get("source_profile") or {}).get("country")) or item.get("source_country"))
        for item in selected
        if normalize_country_code(((item.get("source_profile") or {}).get("country")) or item.get("source_country"))
    }
    missing = [code for code in focus_countries if code not in covered]
    if not missing:
        return selected

    selected_fingerprints = {
        normalize_fingerprint(item.get("url", ""), item.get("title", ""))
        for item in selected
    }
    candidates = _rank_focus_bucket(pool)
    for country_code in missing:
        for candidate in candidates:
            candidate_country = normalize_country_code(
                ((candidate.get("source_profile") or {}).get("country")) or candidate.get("source_country")
            )
            if candidate_country != country_code:
                continue
            fingerprint = normalize_fingerprint(candidate.get("url", ""), candidate.get("title", ""))
            if fingerprint in selected_fingerprints:
                continue
            selected.append(candidate)
            selected_fingerprints.add(fingerprint)
            break
    return _rank_focus_bucket(_diversify_focus_items(selected))


def _backfill_provider_diversity(selected: list[dict], pool: list[dict]) -> list[dict]:
    if not selected or not pool:
        return selected

    present_providers = {item.get("provider") for item in selected if item.get("provider")}
    if len(present_providers) >= 3:
        return selected

    selected_fingerprints = {
        normalize_fingerprint(item.get("url", ""), item.get("title", ""))
        for item in selected
    }
    candidates = _rank_focus_bucket(pool)
    extras_added = 0
    for candidate in candidates:
        provider = candidate.get("provider")
        if not provider or provider in present_providers:
            continue
        if candidate.get("query_alignment") == "low" and float(candidate.get("semantic_query_score") or 0.0) < 0.7:
            continue
        fingerprint = normalize_fingerprint(candidate.get("url", ""), candidate.get("title", ""))
        if fingerprint in selected_fingerprints:
            continue
        selected.append(candidate)
        selected_fingerprints.add(fingerprint)
        present_providers.add(provider)
        extras_added += 1
        if extras_added >= 2 or len(present_providers) >= 3:
            break
    return _rank_focus_bucket(_diversify_focus_items(selected))


def _has_event_absence_cue(text: str) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in EVENT_ABSENCE_CUES)


def _has_near_event_signal(text: str) -> bool:
    lowered = text.lower()
    cues = {
        "меморандум",
        "соглашен",
        "договор",
        "agreement",
        "deal",
        "memorandum",
        "statement",
    }
    return any(cue in lowered for cue in cues)
