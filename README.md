

```md
# 🧠 Meeting Intelligence Platform
### Scalable RAG-Based Transcript Understanding System

A production-oriented Retrieval-Augmented Generation (RAG) system for ingesting meeting transcripts, performing hybrid retrieval (dense + sparse), and generating citation-grounded answers with strict guardrails.

---

## 🚀 Overview

This system enables:

- Transcript ingestion
- Parsing and chunking with rich metadata
- Hybrid dense + sparse retrieval (RRF fusion)
- Citation-backed answer generation
- Multi-turn conversation support
- Clear roadmap for production scaling

---

## 🏗 System Architecture

### Ingestion Flow

User Upload  
→ Validation  
→ Duplicate Check  
→ Parsing & Chunking  
→ Metadata Enrichment  
→ Embedding  
→ Qdrant Vector Store  

### Query Flow

User Query  
→ Rate Limit & Guardrails  
→ Memory Lookup  
→ Time/Speaker Parsing  
→ Query Rewriting  
→ Hybrid Retrieval (Dense + Sparse)  
→ Context Builder  
→ LLM Answer Generation  
→ Citation Guardrails  
→ Save Ask Memory  
→ Response  

---

## 1️⃣ Synthetic Transcript Generation

### Purpose

Generate a synthetic meeting transcript based on user-provided topic and participants.

Used for:
- Testing ingestion pipeline
- Demo environments
- Simulating real meeting scenarios

### Production Alternative

In production:

- Real transcripts will be uploaded.
- Preprocessing occurs before ingestion.
- Synthetic generation can be completely removed.

**Impact:** This step can be eliminated.

---

## 2️⃣ User Input Validation

### Required Inputs

- `topic` (string)
- `participants` (2–10 names, comma-separated)

### Validation Rules

| Condition | Result |
|------------|--------|
| Empty topic | HTTP 400 |
| Empty participants | HTTP 400 |
| < 2 participants | HTTP 400 |
| > 10 participants | HTTP 400 |

### Why Validation Exists

- Ensures meaningful transcript generation
- Prevents generic fallback meetings
- Improves LLM output quality
- Avoids system misuse

---

## 3️⃣ Transcript Ingestion

### File Requirements

- Maximum size: **1 MB**
- Must contain at least one valid line in format:

[HH:MM:SS] Speaker: text

Invalid files → HTTP 400.

---

### Duplicate Protection

- SHA-256 hash computed
- Compared against stored ingestion hashes
- If duplicate → return existing `meeting_id`
- No re-embedding or re-indexing

Benefits:
- Idempotent uploads
- Avoids embedding cost duplication
- Prevents vector DB bloat

---

## 4️⃣ Chunking Logic

### Strategy

- Tumbling window (no overlap)
- Default: 8 turns per chunk
- Final chunk may contain fewer turns

### Each Chunk Contains

- chunk_id
- Joined transcript text
- meeting_id
- file
- line_start / line_end
- time_start / time_end
- time_start_sec / time_end_sec
- speakers

### Metadata Enables

- Time filtering
- Speaker filtering
- Citation enforcement
- Meeting overview summaries

---

## 5️⃣ Embedding Pipeline

### Batch Strategy

- 32 chunks per API call
- Reduces overhead
- Improves throughput

### Model

text-embedding-3-small  
1536-dimensional vectors  
Cosine similarity

### Retry Strategy

Attempt 1 → immediate  
Attempt 2 → 0.5s delay  
Attempt 3 → 1s delay  
Attempt 4 → 2s delay  
Fail after retries  

---

## 6️⃣ Vector Storage (Qdrant)

### Collection

meeting_chunks

### Stored Per Chunk

- Dense vector (cosine similarity)
- Sparse vector (keyword scoring)
- Metadata payload

---

### Retrieval Strategy

1. Dense search
2. Sparse search
3. RRF fusion
4. Return top_k results (default = 10)

Mandatory filter:
- meeting_id

Optional filters:
- speaker_filter
- time_filter

---

## 7️⃣ Answer Generation

### Flow

1. Build context (max 8 chunks)
2. Include metadata filters if applied
3. Send to LLM (gpt-4o-mini)
4. Parse structured JSON output
5. Apply citation guardrails
6. Return final response

---

## Citation Guardrails

- Citation must overlap retrieved chunks
- Clamp line ranges to valid ranges
- Drop invalid citations
- Dedupe duplicates
- If no valid citation → return:
  "Not found in transcript."

---

## 8️⃣ Ask Memory (Multi-turn Support)

Current:
- In-memory storage
- Lost on restart

Future:
- Redis / database-backed
- Shared across replicas
- Audit-ready

---

## 9️⃣ Future Scalability

Planned improvements:

- Redis job queue
- Worker-based ingestion
- Async embedding
- Cross-encoder reranking
- Dynamic top_k
- Metadata-only citation
- PII redaction
- Semantic caching
- Langfuse tracing
- RAGAS evaluation
- Drift monitoring
- CI validation

---

## 🧰 Tech Stack

| Layer | Technology |
|--------|------------|
| API | FastAPI |
| Server | Uvicorn |
| LLM | OpenAI |
| Embeddings | text-embedding-3-small |
| Vector Store | Qdrant |
| UI | Streamlit |
| Validation | Pydantic |
| Config | python-dotenv |
| Package Manager | uv |
| Python | 3.12 |

---

## 📌 Summary

This is a scalable, production-oriented Meeting Intelligence RAG system designed with:

- Hybrid retrieval
- Strict evidence enforcement
- Multi-turn conversation support
- Clear scaling roadmap
- Enterprise-ready extensibility
