from __future__ import annotations

import asyncio
import json
import math
from collections import Counter, defaultdict
from typing import Any

from app.core.config import get_settings
from app.services.analytics import build_narrative_groups, finalize_items, recompute_row_weight
from app.services.openai_api import OpenAIAPIClient
from app.services.query_planner import SearchPlan


ITEM_BATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "item_id": {"type": "string"},
                    "pivot_summary": {"type": "string"},
                    "narrative": {"type": "string"},
                    "emotion": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                    "stance": {"type": "string", "enum": ["supports", "disputes", "mixed", "unclear"]},
                    "query_alignment": {"type": "string", "enum": ["high", "medium", "low"]},
                    "originality": {"type": "string", "enum": ["original", "syndicated", "social primary", "unknown"]},
                    "evidence_density": {"type": "string", "enum": ["high", "medium", "low"]},
                    "digest_like": {"type": "boolean"},
                },
                "required": [
                    "item_id",
                    "pivot_summary",
                    "narrative",
                    "emotion",
                    "stance",
                    "query_alignment",
                    "originality",
                    "evidence_density",
                    "digest_like",
                ],
            },
        }
    },
    "required": ["items"],
}

SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "overview": {"type": "string"},
        "main_narratives": {"type": "array", "items": {"type": "string"}},
        "cross_market_differences": {"type": "array", "items": {"type": "string"}},
        "notable_disputes": {"type": "array", "items": {"type": "string"}},
        "confidence_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "overview",
        "main_narratives",
        "cross_market_differences",
        "notable_disputes",
        "confidence_notes",
    ],
}


async def apply_llm_pipeline(
    items: list[dict],
    *,
    query: str,
    search_plan: SearchPlan,
) -> tuple[list[dict], dict[str, Any] | None, str]:
    settings = get_settings()
    if not settings.openai_api_key or settings.analysis_mode == "heuristic":
        return _mark_analysis_method(items, "heuristic"), None, "heuristic"

    rows = [dict(item) for item in items]
    for index, row in enumerate(rows, start=1):
        row.setdefault("analysis_method", "heuristic")
        row.setdefault("semantic_cluster", None)
        row.setdefault("cluster_label", row.get("narrative"))
        row.setdefault("semantic_query_score", None)
        row.setdefault("llm_item_id", f"item_{index}")

    try:
        rows = await _apply_llm_item_enrichment(rows, query=query, search_plan=search_plan)
        rows = await _apply_semantic_query_reranking(rows, query=query, search_plan=search_plan)
        rows = await _assign_semantic_clusters(rows)
        rows = finalize_items(rows, search_plan)
        summary = await _build_executive_summary(rows, query=query) if settings.openai_enable_synthesis else None
        return rows, summary, settings.analysis_mode
    except Exception:
        return _mark_analysis_method(items, "heuristic"), None, "heuristic_fallback"


def build_batch_requests(
    items: list[dict],
    *,
    query: str,
    search_plan: SearchPlan,
    model: str | None = None,
) -> bytes:
    settings = get_settings()
    model_name = model or settings.openai_enrichment_model
    requests = []
    for batch_index, chunk in enumerate(_chunk_items(_select_llm_candidates(items), settings.openai_batch_chunk_size), start=1):
        custom_id = f"enrichment-batch-{batch_index}"
        requests.append(
            {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": _item_enrichment_system_prompt()},
                        {"role": "user", "content": _item_enrichment_user_prompt(chunk, query, search_plan)},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "media_item_batch_analysis",
                            "strict": True,
                            "schema": ITEM_BATCH_SCHEMA,
                        },
                    },
                },
            }
        )
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in requests).encode("utf-8")


async def _apply_llm_item_enrichment(items: list[dict], *, query: str, search_plan: SearchPlan) -> list[dict]:
    settings = get_settings()
    client = OpenAIAPIClient()
    candidates = _select_llm_candidates(items)
    if not candidates:
        return items

    limit = settings.openai_llm_item_limit
    if limit and limit > 0:
        candidates = candidates[:limit]
    batches = list(_chunk_items(candidates, settings.openai_batch_chunk_size))
    overrides: dict[str, dict[str, Any]] = {}
    semaphore = asyncio.Semaphore(max(settings.openai_enrichment_concurrency, 1))

    async def process_chunk(chunk: list[dict]) -> dict[str, dict[str, Any]]:
        async with semaphore:
            payload = await client.chat_json(
                model=settings.openai_enrichment_model,
                system_prompt=_item_enrichment_system_prompt(),
                user_prompt=_item_enrichment_user_prompt(chunk, query, search_plan),
                schema_name="media_item_batch_analysis",
                schema=ITEM_BATCH_SCHEMA,
            )
            return {
                row["item_id"]: row
                for row in payload.get("items", [])
            }

    batch_payloads = await asyncio.gather(*(process_chunk(chunk) for chunk in batches))
    for payload in batch_payloads:
        overrides.update(payload)

    merged: list[dict] = []
    for item in items:
        item_id = item["llm_item_id"]
        override = overrides.get(item_id)
        if not override:
            merged.append(item)
            continue
        merged_item = dict(item)
        merged_item["pivot_summary"] = override["pivot_summary"] or item["pivot_summary"]
        merged_item["narrative"] = override["narrative"] or item["narrative"]
        merged_item["emotion"] = override["emotion"]
        merged_item["stance"] = override["stance"]
        merged_item["query_alignment"] = override["query_alignment"]
        merged_item["originality"] = override["originality"]
        merged_item["evidence_density"] = override["evidence_density"]
        merged_item["analysis_method"] = "llm"
        merged_item["digest_like"] = bool(override["digest_like"])
        merged_item["weighted_score"] = recompute_row_weight(merged_item) - (18 if merged_item["digest_like"] else 0)
        merged.append(merged_item)
    return merged


async def _assign_semantic_clusters(items: list[dict]) -> list[dict]:
    settings = get_settings()
    if not settings.openai_enable_semantic_clustering or not settings.openai_api_key or not items:
        return items

    client = OpenAIAPIClient()
    texts = [_embedding_text(item) for item in items]
    embeddings = await client.create_embeddings(
        model=settings.openai_embedding_model,
        inputs=texts,
        dimensions=settings.openai_embedding_dimensions,
    )
    if len(embeddings) != len(items):
        return items

    clusters: list[dict[str, Any]] = []
    assignments: list[int] = []
    threshold = 0.78
    for embedding in embeddings:
        best_index = -1
        best_score = -1.0
        for cluster_index, cluster in enumerate(clusters):
            score = _cosine_similarity(embedding, cluster["centroid"])
            if score > best_score:
                best_score = score
                best_index = cluster_index
        if best_index >= 0 and best_score >= threshold:
            assignments.append(best_index)
            cluster = clusters[best_index]
            cluster["members"].append(embedding)
            cluster["centroid"] = _mean_vector(cluster["members"])
        else:
            assignments.append(len(clusters))
            clusters.append({"members": [embedding], "centroid": embedding[:]})

    grouped_rows: dict[int, list[dict]] = defaultdict(list)
    for item, cluster_index in zip(items, assignments, strict=False):
        grouped_rows[cluster_index].append(item)

    for cluster_index, rows in grouped_rows.items():
        dominant_narrative = Counter(row["narrative"] for row in rows).most_common(1)[0][0]
        cluster_id = f"cluster_{cluster_index + 1}"
        for row in rows:
            row["semantic_cluster"] = cluster_id
            row["cluster_label"] = dominant_narrative
    return items


async def _apply_semantic_query_reranking(
    items: list[dict],
    *,
    query: str,
    search_plan: SearchPlan,
) -> list[dict]:
    settings = get_settings()
    if not settings.openai_enable_semantic_reranking or not settings.openai_api_key or not items:
        return items

    client = OpenAIAPIClient()
    query_inputs = _query_embedding_candidates(query, search_plan)
    item_inputs = [_embedding_text(item) for item in items]
    embeddings = await client.create_embeddings(
        model=settings.openai_embedding_model,
        inputs=query_inputs + item_inputs,
        dimensions=settings.openai_embedding_dimensions,
    )
    if len(embeddings) != len(query_inputs) + len(item_inputs):
        return items

    query_vectors = embeddings[: len(query_inputs)]
    item_vectors = embeddings[len(query_inputs) :]

    for item, vector in zip(items, item_vectors, strict=False):
        score = max((_cosine_similarity(vector, query_vector) for query_vector in query_vectors), default=0.0)
        item["semantic_query_score"] = round(score, 4)
        item["weighted_score"] = max(
            1,
            min(100, int(item.get("weighted_score", 0) + _semantic_score_bonus(score))),
        )
        item["query_alignment"] = _promote_alignment(item.get("query_alignment", "low"), score)

    return items


async def _build_executive_summary(items: list[dict], *, query: str) -> dict[str, Any] | None:
    client = OpenAIAPIClient()
    payload = await client.chat_json(
        model=get_settings().openai_synthesis_model,
        system_prompt=_synthesis_system_prompt(),
        user_prompt=_synthesis_user_prompt(items, query),
        schema_name="media_executive_summary",
        schema=SYNTHESIS_SCHEMA,
    )
    return payload


def _select_llm_candidates(items: list[dict]) -> list[dict]:
    ranked = sorted(
        [dict(item) for item in items],
        key=lambda row: (
            row.get("weighted_score", 0),
            1 if row.get("query_alignment") == "high" else 0,
            row.get("published_at"),
        ),
        reverse=True,
    )
    selected: list[dict] = []
    for index, item in enumerate(ranked, start=1):
        copy = dict(item)
        copy["llm_item_id"] = copy.get("llm_item_id") or f"item_{index}"
        selected.append(copy)
    return selected


def _mark_analysis_method(items: list[dict], method: str) -> list[dict]:
    rows = []
    for index, item in enumerate(items, start=1):
        row = dict(item)
        row.setdefault("analysis_method", method)
        row.setdefault("semantic_cluster", None)
        row.setdefault("cluster_label", row.get("narrative"))
        row.setdefault("semantic_query_score", None)
        row.setdefault("llm_item_id", f"item_{index}")
        rows.append(row)
    return rows


def _chunk_items(items: list[dict], chunk_size: int) -> list[list[dict]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _item_enrichment_system_prompt() -> str:
    return (
        "Ты аналитик глобальных медиа. Анализируй каждый материал консервативно. "
        "Высокое совпадение с запросом допускается только когда материал прямо описывает ключевой инфоповод, "
        "его основные сущности и действие из запроса. Дайджесты, подборки, списки акций и многотемные сводки "
        "обычно должны получать medium или low, если целевой сюжет не является центральным. "
        "Если запрос относится к конкретному коридору, проливу, маршруту, соглашению или визиту, не повышай релевантность "
        "без прямого упоминания этой сущности или её общепринятого алиаса. "
        "Если в запросе есть действие вроде подписания, соглашения, визита, переговоров, меморандума или запуска, "
        "а в материале обсуждается только общий фон вокруг объекта без самого события, ставь low и явно отмечай это в саммари. "
        "Возвращай краткие нейтральные саммари на русском и короткие ярлыки нарратива на русском."
    )


def _item_enrichment_user_prompt(items: list[dict], query: str, search_plan: SearchPlan) -> str:
    compact_items = [
        {
            "item_id": item["llm_item_id"],
            "provider": item["provider"],
            "source_type": item["source_type"],
            "source_name": item["source_name"],
            "language": item.get("language"),
            "title": item["title"],
            "summary": item["pivot_summary"],
            "current_narrative": item["narrative"],
            "current_stance": item["stance"],
        }
        for item in items
    ]
    return json.dumps(
        {
            "query": query,
            "anchor_terms": search_plan.anchor_terms,
            "core_terms": search_plan.core_terms,
            "action_terms": search_plan.action_terms,
            "entity_aliases": search_plan.entity_aliases,
            "search_mode": search_plan.search_mode,
            "strict_entity_phrases": search_plan.strict_entity_phrases,
            "focus_country_codes": search_plan.focus_country_codes,
            "paraphrases": search_plan.paraphrases,
            "multilingual_queries": search_plan.multilingual_queries,
            "items": compact_items,
        },
        ensure_ascii=False,
        indent=2,
    )


def _synthesis_system_prompt() -> str:
    return (
        "Ты senior-аналитик media intelligence. Своди общую картину кратко и по-русски, "
        "выделяй расхождения в нарративах, спорные линии и ограничения уверенности. "
        "Будь нейтральным и опирайся только на предоставленные данные."
    )


def _synthesis_user_prompt(items: list[dict], query: str) -> str:
    top_items = [
        {
            "provider": item["provider"],
            "source": item["source_name"],
            "country": item.get("source_country"),
            "language": item.get("language"),
            "title": item["title"],
            "pivot_summary": item["pivot_summary"],
            "narrative": item["narrative"],
            "emotion": item["emotion"],
            "stance": item["stance"],
            "alignment": item["query_alignment"],
            "weight": item["weighted_score"],
            "cluster": item.get("cluster_label") or item.get("narrative"),
        }
        for item in items[:14]
    ]
    return json.dumps(
        {
            "query": query,
            "narrative_groups": build_narrative_groups(items)[:8],
            "top_items": top_items,
        },
        ensure_ascii=False,
        indent=2,
    )


def _embedding_text(item: dict) -> str:
    return " ".join(
        part
        for part in [
            item.get("title", ""),
            item.get("pivot_summary", ""),
            item.get("narrative", ""),
            item.get("stance", ""),
        ]
        if part
    )[:2000]


def _query_embedding_candidates(query: str, search_plan: SearchPlan) -> list[str]:
    variants = [
        query,
        search_plan.expanded_query,
        search_plan.keyword_query,
        *search_plan.paraphrases[:4],
        *search_plan.multilingual_queries.get("en", [])[:2],
    ]

    seen: set[str] = set()
    candidates: list[str] = []
    for variant in variants:
        normalized = " ".join((variant or "").split()).strip()
        if len(normalized) < 3:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        candidates.append(normalized)
    return candidates[:10]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    width = len(vectors[0])
    sums = [0.0] * width
    for vector in vectors:
        for index, value in enumerate(vector):
            sums[index] += value
    return [value / len(vectors) for value in sums]


def _semantic_score_bonus(score: float) -> int:
    if score >= 0.82:
        return 16
    if score >= 0.74:
        return 11
    if score >= 0.66:
        return 7
    if score >= 0.58:
        return 3
    if score < 0.35:
        return -6
    return 0


def _promote_alignment(current: str, semantic_score: float) -> str:
    ranking = {"low": 1, "medium": 2, "high": 3}
    current_rank = ranking.get(current, 1)
    if semantic_score >= 0.78:
        semantic_rank = 3
    elif semantic_score >= 0.6:
        semantic_rank = 2
    else:
        semantic_rank = 1

    final_rank = max(current_rank, semantic_rank)
    reverse = {value: key for key, value in ranking.items()}
    return reverse.get(final_rank, current)
