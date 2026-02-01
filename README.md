# Meeting Intelligence RAG

FastAPI + Qdrant + OpenAI RAG for meeting transcripts: ingest, ask (with citations), stream, summary. Versioned prompts, hybrid (dense + sparse) retrieval with RRF, prompt-injection guardrails.

## Ingestion

- **Script (sample .txt):** `bash scripts/fresh_reset.sh` — resets, brings up stack, and ingests `sample_data/transcript1.txt`. Use the printed Meeting ID in the UI or for tests.

## Limits

| Limit | Default | Env / location |
|-------|--------|----------------|
| Max file size per upload | 1024 KB (1 MB) | `MAX_FILE_KB` |
| Turns per chunk | 8 | `CHUNK_TURNS` |
| Default retrieval top_k | 10 | `RETRIEVE_TOP_K` |
| Rate limit | 20 requests / 60 s per IP | `app/main.py` |

Print current limits: `uv run python scripts/print_limits.py`

## Docker: reflecting code changes

- **With `docker-compose.override.yml`** (included): `app/` and `ui/` are mounted into the containers, so edits to the code are reflected without rebuild. The API runs with `--reload`; Streamlit reloads on file change. Just run `docker-compose up -d` and change files.
- **Without the override** (e.g. you removed it): rebuild after code changes: `docker-compose up -d --build`.

## Run from scratch (down all, auto-ingest, test)

```bash
bash scripts/fresh_reset.sh
```

Then:

- **UI:** http://localhost:8501 — Enter the Meeting ID (from script), then Ask / Extract Summary.
- **E2E:** `uv run pytest tests/test_e2e_api.py -v`

## Local run (no Docker API/UI)

```bash
bash scripts/fresh_reset.sh
docker-compose up -d qdrant
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
uv run streamlit run ui/streamlit_app.py
```

Set `QDRANT_URL=http://localhost:6333` and `OPENAI_API_KEY` in `.env`.

## Tests

- **Pytest:** `uv run pytest tests/ -v`

## Project layout

- `app/main.py` — API routes.
- `app/rag/` — retriever (hybrid + RRF), answerer, streamer, query_rewriter, context.
- `app/prompts/v1/` — versioned YAML prompts.
- `app/ingest/` — parser, chunker, indexer (dense + sparse).
- `ui/streamlit_app.py` — Streamlit UI.
- `scripts/fresh_reset.sh` — down all, clear data, up stack, auto-ingest sample.
- `scripts/print_limits.py` — print ingestion and API limits.
