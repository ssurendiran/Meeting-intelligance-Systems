# Meeting Intelligence RAG — Audit Report

**Date:** January 2025  
**Scope:** Codebase structure, security, testing, configuration, observability, and technical debt.

---

## 1. Executive Summary

The repository is a well-structured FastAPI RAG application for meeting transcripts with ingest, ask (citations), stream, summary, versioned prompts, hybrid retrieval, and guardrails. The audit identifies **strengths** (clear layering, observability, tests) and **actionable items** (doc fixes, deprecations, security hardening, and consistency).

---

## 2. Architecture & Structure

| Area | Assessment |
|------|------------|
| **Layout** | Clear: `app/` (core, ingest, rag, guardrails, observability, eval), `tests/`, `scripts/`, `ui/`. |
| **Config** | Centralized in `app/core/config.py` with Pydantic and env; `.env.example` documents vars. |
| **API** | FastAPI with Pydantic schemas; routes grouped in `main.py` with section comments. |
| **Shared logic** | Ask pipeline uses `_ask_retrieve_and_build_context()` for /ask and /ask_stream (no duplication). |

**Recommendation:** Consider splitting `main.py` (838 lines) into route modules (e.g. `app/routes/ingest.py`, `ask.py`, `eval.py`) for maintainability; optional.

---

## 3. Security

| Item | Status | Notes |
|------|--------|--------|
| **Rate limiting** | ✅ | Per-IP, 20 req/60s; applied on ingest, ask, summary, job status, generate_eval_dataset, etc. |
| **Prompt injection** | ✅ | Heuristic detector; retrieval still allowed, generation instructions tightened. |
| **File size** | ✅ | `MAX_FILE_KB` (default 1024 KB); enforced in sync ingest, async ingest, worker. |
| **API key** | ✅ | `OPENAI_API_KEY` from env; not logged. |
| **Path traversal** | ⚠️ | Upload filenames (`f.filename` or `out_name`) are joined with `sync_dir` / `job_dir` without sanitization. A filename like `../../etc/passwd` could write outside the intended directory. **Recommendation:** Sanitize: use `os.path.basename(f.filename)` and reject names containing path separators. |
| **Duplicate ingest** | ✅ | Content hash prevents re-ingest; 409 returns existing `meeting_id`. |

---

## 4. Configuration & Documentation

| Issue | Severity | Action |
|-------|----------|--------|
| **README vs config** | Low | README says "Max file size per upload | **500 KB**"; `config.py` default is `MAX_FILE_KB=1024` (1 MB). Align README to "1024 KB (1 MB)" or change default. |
| **.env.example** | ✅ | Documents `OPENAI_API_KEY`, `QDRANT_*`, `PROMPT_VERSION`, optional cost vars. |
| **History DB path** | ✅ | `app/observability/history.py` uses `__file__`-relative path to `data/history.db`; correct from repo root. |

---

## 5. Deprecations & Tech Debt

| Item | Location | Recommendation |
|------|----------|----------------|
| **FastAPI `on_event("startup")`** | `app/main.py` L96 | Deprecated in FastAPI; use lifespan context manager. Migrate to `lifespan` for startup/shutdown. |
| **In-memory rate limiter** | `app/guardrails/rate_limit.py` | Per-process; not shared across workers. Acceptable for single-instance; for multi-worker use Redis or similar. |
| **In-memory JOBS** | `app/ingest/jobs.py` | Async job state is process-local; restarts lose state. Document; consider Redis/DB for production. |
| **Observability** | `app/observability/` | Langfuse Cloud when configured; no in-app metrics store. |

---

## 6. Async Ingest vs Sync

| Aspect | Sync ingest | Async ingest |
|--------|-------------|--------------|
| **Duplicate check** | ✅ Yes | ❌ No (same content can be re-ingested via async). |
| **last_meeting_id.txt** | ✅ Updated | ❌ Not updated (script `generate_dataset_and_run_ragas.py` defaults to last *sync* ingest). |
| **Transcript location** | `data/uploads/sync/{meeting_id}/` | `data/uploads/{job_id}/` |

**Recommendation:** Document that "last ingested" is sync-only; optionally add duplicate check and/or `last_meeting_id` update for async when job completes (e.g. same hash logic as sync).

---

## 7. Eval Dataset & RAGAS

| Item | Status |
|------|--------|
| **API** `POST /generate_eval_dataset` | Writes to `data/rag_eval_dataset.json`. |
| **RAGAS test default path** | `tests/data/rag_eval_dataset.json` (or `RAG_EVAL_DATASET` env). |
| **Script** `generate_dataset_and_run_ragas.py` | Writes to `tests/data/rag_eval_dataset.json` and runs RAGAS; uses `data/last_meeting_id.txt` (sync). |
| **Mismatch** | If users only call the API (no script), RAGAS won’t see the file unless they set `RAG_EVAL_DATASET=data/rag_eval_dataset.json` or copy. Document in README/API docs. |

---

## 8. Testing

| Area | Coverage |
|------|----------|
| **Unit** | Parser, citations, timestamps; focused and stable. |
| **E2E API** | Ingest, ask, stream, summary, job status, invalid/unknown meeting_id. |
| **RAGAS** | Dataset exists, evaluate metrics, optional threshold test (skipped by default). |
| **E2E dependency** | Tests that ingest expect no prior duplicate (same sample transcript) or get 409; RAGAS fixture accepts 409 and uses returned `meeting_id`. |

**Recommendation:** Document that a clean state (e.g. `scripts/fresh_reset.sh`) or unique transcript is needed for E2E ingest tests when running repeatedly.

---

## 9. Observability

| Feature | Status |
|---------|--------|
| **Langfuse Cloud** | Optional; when `LANGFUSE_*` env vars are set, traces /ask and /ask_stream (retrieval, context, LLM spans; tokens, cost). |
| **Cost** | Configurable per-1K token costs in config; used for Langfuse trace metadata. |
| **UI** | No built-in Metrics page; observability via Langfuse dashboard. |

---

## 10. Error Handling

| Area | Assessment |
|------|------------|
| **API** | HTTPException with appropriate status codes; guardrails (rate limit, prompt injection, validation). |
| **Generic 500** | `as_http_500(e)` used; no internal details leaked. |
| **Query rewriter** | Logs warning on failure; falls back to original question. |
| **Worker** | Exceptions in async job set status to "failed" and call `record_error`. |

---

## 11. Action Items (Prioritized)

### P0 (Correctness / Security)

1. **Path traversal:** Sanitize upload filenames (e.g. `os.path.basename`, reject `os.sep` in name) in sync and async ingest and in worker when writing files.

### P1 (Documentation / Consistency)

2. **README:** Fix "Max file size" to 1024 KB (1 MB) to match `config.py` default, or add `MAX_FILE_KB` to `.env.example` and document.
3. **Eval dataset path:** Document in README that API writes to `data/rag_eval_dataset.json` and RAGAS reads `tests/data/rag_eval_dataset.json` by default; set `RAG_EVAL_DATASET` or use script when using API-only.
4. **last_meeting_id:** Document that it is updated only for sync ingest; script `generate_dataset_and_run_ragas.py` uses it as default meeting_id.

### P2 (Tech debt / Nice-to-have)

5. **FastAPI lifespan:** Replace `@app.on_event("startup")` with a lifespan context manager.
6. **Async ingest:** Optionally add duplicate check and/or update of `last_meeting_id.txt` when async job completes (for consistency with sync).

---

## 12. Summary

The codebase is in good shape: clear structure, observability, tests, and guardrails. The audit recommends one **security hardening** (path traversal), **documentation fixes** (README limits, eval paths, last_meeting_id), and **optional tech debt** (lifespan, async ingest consistency). No blocking issues were found for normal development and deployment.
