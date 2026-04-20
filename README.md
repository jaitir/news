# Global Media Intelligence

Greenfield MVP for cross-source media analysis:

- `frontend/`: Next.js analyst dashboard
- `backend/`: FastAPI service, persistence, export, source connectors
- `docker-compose.yml`: local orchestration for Postgres, backend, frontend

## What is already implemented

- Search form with query, lookback window, source toggles, and result limits
- Result persistence in Postgres-compatible schema
- Saved snapshots with reopen flow
- Unified result table with title, source, summary, narrative, emotion, stance
- Narrative grouping cards
- Excel and DOCX export for each saved snapshot
- Structured report layer for segment-based analyst briefs: pro-government, opposition, independent, western-aligned, and unknown
- Seeded source registry with political/editorial classification and coverage diagnostics
- Live connectors for `Event Registry`, `GDELT`, `X`, `Telegram`, `Guardian`, `GNews`, `Media Cloud`, and `NewsData.io`
- OpenAI-powered hybrid enrichment layer with item-level analysis, semantic clustering, semantic reranking, multilingual query expansion, and executive summaries
- Demo fallback mode so the product works before production credentials are added

## Local run

1. Copy `.env.example` to `.env`
2. Start infrastructure:

```bash
docker compose up --build
```

3. Open:

- Frontend: `http://localhost:3000`
- Backend docs: `http://localhost:8000/docs`
- Structured report endpoint: `http://localhost:8000/api/v1/searches/<snapshot_id>/report`

## Local development without Docker

### Backend

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
PYTHONPATH=backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend expects Postgres by default. If you want a disposable local smoke setup, override `DATABASE_URL` first.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Credentials you will add next

- `EVENT_REGISTRY_API_KEY`
- `X_BEARER_TOKEN`
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `GUARDIAN_OPEN_PLATFORM_KEY` (optional)
- `GNEWS_API_KEY` (optional)
- `MEDIA_CLOUD_API_KEY` (optional)
- `NEWSDATA_API_KEY` (optional)
- `TELEGRAM_CURATED_CHANNELS` (optional comma-separated allowlist like `bbcnews,cnn`)
- `X_CURATED_ACCOUNTS` (optional comma-separated allowlist like `reuters,ap`)
- `OPENAI_API_KEY`
- `ANALYSIS_MODE` (`heuristic`, `llm`, `hybrid`)
- `OPENAI_ENABLE_QUERY_EXPANSION`
- `OPENAI_QUERY_EXPANSION_MODEL`
- `QUERY_EXPANSION_LANGUAGES`
- `OPENAI_ENRICHMENT_MODEL` (recommended: `gpt-5.4-mini`)
- `OPENAI_SYNTHESIS_MODEL` (recommended: `gpt-5.4`)
- `OPENAI_DEEP_RESEARCH_MODEL` (recommended: `gpt-5.4-pro`)
- `OPENAI_DEEP_RESEARCH_REASONING_EFFORT` (`medium`, `high`, `xhigh`)
- `OPENAI_DEEP_RESEARCH_MAX_TOOL_CALLS`
- `OPENAI_EMBEDDING_MODEL`
- `OPENAI_LLM_ITEM_LIMIT`
- `OPENAI_ENABLE_SYNTHESIS`
- `OPENAI_ENABLE_SEMANTIC_CLUSTERING`
- `OPENAI_ENABLE_SEMANTIC_RERANKING`
- `REPORT_DOCX_TEMPLATE_PATH` (optional absolute path to a DOCX export template)

`GDELT` is public and does not require a key, but it can rate-limit under load.

## Telegram session bootstrap

Telegram channel search uses MTProto user authorization, not a bot token.

```bash
TELEGRAM_API_ID=... TELEGRAM_API_HASH=... .venv/bin/python backend/scripts/generate_telegram_session.py
```

The script prints a `TELEGRAM_SESSION_STRING`. Put that value into `.env`.

## Current limitations

- `Telegram` connector is implemented and works with MTProto, but Telegram global public-channel search can still require `Premium` or `Stars` depending on the account and query
- `X` connector currently targets recent search
- `NewsData.io` is connected through its latest endpoint, so deeper historical coverage depends on the plan
- The default curated X and Telegram pools are intentionally conservative and should be adjusted for your domain focus
- `Batch API` is wired through helper scripts for large offline enrichment jobs, while interactive searches use synchronous hybrid enrichment
- The current semantic clustering and semantic reranking use OpenAI embeddings plus lightweight local cosine-threshold logic; if you later add a vector database, this can be upgraded without changing the UI contract
- Multilingual search recall now depends on OpenAI query expansion plus translation fallback; this is much stronger than pure keyword search, but it is still not equivalent to a dedicated multilingual vector index over your full archive
- The source registry is currently a curated seed registry, not a complete global media database; use the candidate export script below to expand it incrementally from real searches

## OpenAI batch helpers

Generate a JSONL batch file for a stored snapshot:

```bash
PYTHONPATH=backend .venv/bin/python backend/scripts/create_openai_enrichment_batch.py <snapshot_id>
```

Generate and submit it to OpenAI in one step:

```bash
PYTHONPATH=backend .venv/bin/python backend/scripts/create_openai_enrichment_batch.py <snapshot_id> --submit
```

Check a batch and optionally download the output/error JSONL files:

```bash
PYTHONPATH=backend .venv/bin/python backend/scripts/check_openai_batch.py <batch_id>
```

## Source registry curation

Export unresolved sources from stored snapshots into a CSV for manual classification:

```bash
PYTHONPATH=backend .venv/bin/python backend/scripts/export_source_registry_candidates.py --output registry_candidates.csv
```

The CSV groups unknown sources by name and domain, and includes provider counts, countries, languages, sample queries, sample URLs, and last-seen time. This is the intended workflow for growing the source registry beyond the initial seed set.
