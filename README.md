# 🧠 Meeting Intelligence Platform

**Scalable RAG-Based Transcript Understanding System**

---

## What We Built

We built a Meeting Intelligence system that can ingest real meeting transcripts, index them intelligently, and answer questions grounded strictly in transcript evidence.

The goal was simple:

> Given a meeting transcript, allow users to ask natural questions and get precise, citation-backed answers — without hallucinations.

Under the hood, this is a hybrid RAG (Retrieval-Augmented Generation) system with guardrails, structured chunking, and strict evidence enforcement.

---

## 🚀 Why We Built It This Way



- **Idempotent ingestion** — no duplicate vector bloat
- **Time-aware and speaker-aware filtering**
- **Strict citation guardrails** — no fake references
- **Multi-turn follow-up handling**
- **Clear scaling path** toward production

This README explains exactly how the system works.

---

## 🏗 High-Level Architecture

We split the system into two clear flows:

### 📥 Ingestion Flow

```
User Upload
  → Validation (size, format)
  → Duplicate Check (content hash)
  → Parsing & Chunking (8 turns per chunk)
  → Metadata Enrichment (time, speakers)
  → Embedding (OpenAI batch)
  → Qdrant Vector Store (upsert)
```

### 🔍 Ask (Query) Flow

```
User Query
  → Guardrails (rate limit, prompt injection)
  → Memory Lookup (meeting_id)
  → Time/Speaker Parsing
  → Query Rewrite (1–3 variations)
  → Hybrid Retrieval (Dense + Sparse RRF)
  → Context Build
  → LLM Answer
  → Citation Validation
  → Save Memory
  → Response
```

---

## 📊 Full Ask Flow (Detailed)

```mermaid
flowchart TD
    U1[User question + meeting_id] --> A1[POST /ask]
    A1 --> A2[Rate limit check]
    A2 --> A3{Prompt injection?}
    A3 -->|Yes| A4[Reject 400]
    A3 -->|No| A5[Memory lookup]
    A5 --> A6[Parse time & speaker]
    A6 --> A7[Query rewrite 1-3 variations]
    A7 --> A8[Embed query]
    A8 --> A9[Qdrant Dense + Sparse search]
    A9 --> A10[Apply filters meeting_id/time/speaker]
    A10 --> A11[Return top_k chunks]
    A11 --> A12[Build context]
    A12 --> A13[Generate answer LLM]
    A13 --> A14[Citation guardrails]
    A14 --> A15[Save ask memory]
    A15 --> A16[Return answer + citations]
```

### 📊 End-to-End Ask Flow (Multi-Turn)

```mermaid
flowchart TD
    subgraph UI
        U1[User types question + meeting_id]
    end
    
    subgraph API["API Layer"]
        A1[POST /ask]
        A2[Rate limit check]
        A3{Prompt injection?}
        A4[400 Reject]
        A5[Memory Lookup by meeting_id]
        A6[Parse time + speaker from question]
    end
    
    subgraph MemoryLookup["Memory Lookup (ASK_MEMORY)"]
        M1[Key: meeting_id]
        M2{Entry exists?}
        M3[Get stored_question, stored_answer, retrieved]
        M4[No stored - first turn]
    end
    
    subgraph UseForRetrieval["Use for Retrieval"]
        R1a[use_for_retrieval = current question]
        R1b[use_for_retrieval = stored_question + anchor]
        F2{Follow-up? Short vague OR phrase}
    end
    
    subgraph Rewrite
        R2[Query rewrite LLM 1-3 queries]
    end
    
    subgraph Retrieval["Retrieval"]
        V1[Embed use_for_retrieval OpenAI]
        V2[Qdrant Dense + Sparse RRF]
        V3[Filter meeting_id, speaker, time]
        V4[Return top_k chunks]
    end
    
    subgraph Context["Context Build"]
        C1[pack_context from retrieved]
        C2[Add overview, time, speaker filters]
        C3{Follow-up?}
        C4[Prepend stored_answer + user follow-up to context]
    end
    
    subgraph Answer
        D1[generate_answer LLM]
        D2[Citation guardrails]
        D3[Save ask memory by meeting_id]
    end
    
    subgraph Response
        E1[AskResponse]
        E2[UI shows answer + citations]
    end
    
    U1 --> A1 --> A2 --> A3
    A3 -->|Hit| A4
    A3 -->|Pass| A5 --> M1 --> M2
    M2 -->|No| M4 --> R1a
    M2 -->|Yes| M3 --> A6 --> F2
    F2 -->|Yes| R1b
    F2 -->|No| R1a
    R1a --> R2
    R1b --> R2
    R2 --> V1 --> V2 --> V3 --> V4
    V4 --> C1 --> C2 --> C3
    C3 -->|Yes| C4 --> D1
    C3 -->|No| D1
    D1 --> D2 --> D3 --> E1 --> E2
```

---

## 1️⃣ Synthetic Transcript Generation

Initially, we created synthetic transcripts for testing. Users provide:

- **Topic** (string, mandatory)
- **2–10 participants** (comma-separated)

This allows us to simulate real meetings. However, this step is purely for demo/testing.

**In production:** Real transcripts are uploaded. Synthetic generation can be removed entirely.

**Validation rules:**

| Condition          | Result   |
|--------------------|----------|
| Empty topic        | HTTP 400 |
| Empty participants | HTTP 400 |
| &lt; 2 participants | HTTP 400 |
| &gt; 10 participants | HTTP 400 |

---

## 2️⃣ Ingestion Design Decisions

We deliberately designed ingestion to be strict.

### File Validation

- **Max size:** 1 MB
- **Format:** Must contain at least one valid line: `[HH:MM:SS] Speaker: text`

**Why?** Prevents system abuse, avoids ingesting random text files, keeps embedding cost predictable.

### Duplicate Protection

Before parsing, we compute SHA-256 of file content. If already ingested:

- Return the existing `meeting_id`
- No re-embedding
- No vector duplication

This makes ingestion idempotent and cost-efficient.

---

## 3️⃣ Chunking Strategy

We use a tumbling window approach:

- **8 speaker turns per chunk**
- **No overlap**
- Last chunk may be smaller

Each chunk stores:

- Text, `meeting_id`, `file`
- `line_start` / `line_end`
- `time_start` / `time_end`
- `time_start_sec` / `time_end_sec`
- `speakers`

We enrich metadata because we want time-based filtering, speaker filtering, precise citations, and meeting overview summaries. This metadata becomes extremely important during retrieval.

---

## 4️⃣ Embedding Strategy

- **Batch size:** 32 chunks per API call
- **Model:** `text-embedding-3-small` (1536 dimensions, cosine similarity)
- **Retry:** Exponential backoff (0.5s, 1s, 2s)

**Why?** Real systems fail occasionally — network or rate limits — and ingestion should be resilient.

---

## 5️⃣ Vector Storage (Qdrant)

**Collection:** `meeting_chunks`

Each chunk stores:

- Dense vector
- Sparse vector
- Metadata payload

**Hybrid retrieval:**

1. Dense similarity
2. Sparse keyword scoring
3. RRF (Reciprocal Rank Fusion)
4. Return top_k (default 10)

**Filters:**

- `meeting_id` (mandatory)
- `speaker` (optional, parsed from question)
- Time range (optional, parsed from question)

This guarantees strict meeting isolation.

---

## 6️⃣ Ask Flow — What Actually Happens

When a user asks a question:

1. Rate limit check
2. Prompt injection check
3. Memory lookup by `meeting_id`
4. Parse time references from question
5. Parse speaker references from question
6. Rewrite question into 1–3 search queries
7. Run hybrid retrieval
8. Build context (max 8 chunks)
9. Send to LLM (`gpt-4o-mini`)
10. Validate citations
11. Store ask memory
12. Return answer + citations

---

## 7️⃣ Citation Guardrails (Critical Part)

We do not trust LLM citations blindly. We:

- Define allowed ranges from retrieved chunks
- Ensure citations overlap retrieved content
- Clamp citation ranges to allowed bounds
- Remove invalid citations
- Dedupe duplicates

**If no valid citations remain:** Refuse and return `"Not found in transcript."`

This prevents hallucinated references.

---

## 8️⃣ Multi-Turn Support (Ask Memory)

We store: last question, last answer, retrieved chunks — keyed by `meeting_id`.

| State   | Implementation      |
|---------|---------------------|
| Current | In-memory OrderedDict, lost on restart |
| Future  | Redis-backed, shared across replicas, audit-ready |

---

## 9️⃣ Current Limitations

- Embeddings are synchronous
- Ingestion jobs stored in memory
- No distributed workers yet
- Static top_k
- No reranker yet

These are intentional tradeoffs for iteration speed.

---

## 🔮 Planned Improvements

- Redis job queue
- Worker-based ingestion
- Async embedding
- Cross-encoder reranking
- Dynamic top_k
- Metadata-only citations
- PII redaction layer
- Semantic caching
- Langfuse tracing
- RAGAS evaluation
- Drift monitoring
- CI gating with evaluation datasets

---

## 🧰 Tech Stack

| Layer       | Technology              |
|-------------|-------------------------|
| API         | FastAPI                 |
| Server      | Uvicorn                 |
| LLM         | OpenAI (gpt-4o-mini)    |
| Embeddings  | text-embedding-3-small  |
| Vector DB   | Qdrant                  |
| UI          | Streamlit               |
| Validation  | Pydantic                |
| Config      | python-dotenv           |
| Package Manager | uv                 |
| Python      | 3.12                    |

---

## 🧩 Why This Architecture Works

- **Hybrid retrieval** improves recall
- **Strict filters** improve precision
- **Guardrails** prevent hallucination
- **Metadata** enables time/speaker intelligence
- **Design** supports scaling without redesign

This is not just a demo RAG. It's built with production constraints in mind.
