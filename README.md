🧠 Meeting Intelligence Platform
Scalable RAG-Based Transcript Understanding System

A production-oriented Retrieval-Augmented Generation (RAG) system for ingesting meeting transcripts, performing hybrid retrieval (dense + sparse), and generating citation-grounded answers with guardrails.

🚀 Overview

This system allows you to:

Ingest meeting transcripts

Chunk and enrich transcript data

Embed content using OpenAI embeddings

Store vectors in Qdrant (dense + sparse hybrid search)

Retrieve relevant transcript sections

Generate citation-backed answers

Enforce strict evidence guardrails

Support multi-turn conversations

🏗 System Architecture
flowchart TD
    A[User Upload Transcript] --> B[Validation Layer]
    B --> C[Duplicate Check]
    C --> D[Parsing & Chunking]
    D --> E[Metadata Enrichment]
    E --> F[Embedding Service]
    F --> G[Qdrant Vector Store]

    H[User Query] --> I[Query Validation]
    I --> J[Memory Lookup]
    J --> K[Query Rewriting]
    K --> L[Hybrid Retrieval]
    L --> M[Context Builder]
    M --> N[LLM Answer Generation]
    N --> O[Citation Guardrails]
    O --> P[Save Ask Memory]
    P --> Q[Response]

📄 1. Synthetic Transcript Generation
Purpose

Generate synthetic meeting transcripts for:

Testing ingestion pipeline

Demonstrating retrieval logic

Simulating realistic meetings

Production Alternative

In production:

Real meeting transcripts are uploaded

Preprocessing applied before ingestion

Synthetic generation removed entirely

⚠️ Impact: This step is optional and can be fully eliminated in production environments.

✅ 2. User Input Validation
Required Inputs

topic: string

participants: comma-separated list (2–10 names)

Validation Rules
Condition	Result
Missing topic	HTTP 400
Missing participants	HTTP 400
< 2 participants	HTTP 400
> 10 participants	HTTP 400
Why Strict Validation?

Ensures meaningful transcripts

Prevents generic LLM fallbacks

Improves generation quality

Avoids system misuse

📥 3. Transcript Ingestion Flow
3.1 Upload & Validation
File Requirements

Max size: 1 MB

Must contain lines formatted as:

[HH:MM:SS] Speaker: text


Invalid files → HTTP 400

3.2 Duplicate Protection

SHA-256 hash computed

Compared against stored ingestion hashes

Outcomes
Case	Behavior
Duplicate	Return existing meeting_id
New file	Continue processing
Benefits

Idempotent ingestion

Cost savings (no re-embedding)

Prevent vector duplication

✂️ 4. Chunking Strategy
Tumbling Window (No Overlap)

Default: 8 turns per chunk

Last chunk may contain fewer turns

Each Chunk Contains

chunk_id

Combined transcript text

Metadata payload:

meeting_id
file
line_start / line_end
time_start / time_end
time_start_sec / time_end_sec
speakers

Metadata Enrichment

Derived fields enable:

Time-based filtering

Speaker filtering

Citation enforcement

Meeting summaries

🧮 5. Embedding Pipeline
Batch Strategy

32 chunks per OpenAI call

Reduces API overhead

Model Used
text-embedding-3-small


1536-dimensional vectors

Cosine similarity search

Retry Logic
Attempt	Delay
1	Immediate
2	0.5 sec
3	1 sec
4	2 sec
Fail	Raise error
🗂 6. Vector Storage (Qdrant)
Collection: meeting_chunks

Each chunk stores:

Dense vector

Sparse vector

Metadata payload

Hybrid Retrieval Strategy
flowchart LR
    Q[Query Embedding] --> D[Dense Search]
    Q --> S[Sparse Search]
    D --> RRF[Reciprocal Rank Fusion]
    S --> RRF
    RRF --> TOPK[Top-K Chunks]

Filters
Mandatory

meeting_id

Optional

speaker_filter

time_filter

Default Configuration
top_k = 10


Overridable via config or request.

🔎 7. Retrieval → Answer Flow
Context Building

pack_context():

Deduplicates by chunk_id

Max 8 chunks

Formats:

SOURCE: file:line_start-line_end
chunk text


Optional additions:

Meeting overview

Time filter notice

Speaker filter notice

Follow-up context

Answer Generation

Model:

gpt-4o-mini


Low temperature.

Expected JSON output:

{
  "answer": "...",
  "citations": [
    {"file": "...", "line_start": 10, "line_end": 15}
  ]
}

🛡 Citation Guardrails

After LLM response:

Check	Purpose
Allowed ranges	Must match retrieved chunks
Overlap check	Must overlap allowed lines
Clamp	Trim citation range
Drop	Remove invalid citations
Dedupe	Merge duplicates
Refuse	If no valid citation → "Not found in transcript."

Ensures:

No hallucinated citations

No out-of-scope references

Strict transcript grounding

💬 Multi-Turn Memory
Current

In-memory OrderedDict

Stores last Q&A per meeting

Lost on restart

Future

Redis-backed memory

Distributed support

Audit-ready persistence

🔁 Query Processing Pipeline
sequenceDiagram
    participant User
    participant API
    participant Retriever
    participant LLM
    participant Guardrails

    User->>API: Ask Question
    API->>Retriever: Hybrid Retrieval
    Retriever-->>API: Retrieved Chunks
    API->>LLM: Generate Answer
    LLM-->>API: Answer + Citations
    API->>Guardrails: Validate Citations
    Guardrails-->>API: Cleaned Answer
    API-->>User: Final Response

📈 Current vs Future Scalability
Area	Current	Future
Ingestion	Single container	Distributed workers
Jobs	In-memory	Redis queue
Embeddings	Sync	Async / Parallel
Memory	In-memory	Redis / DB
Citation	LLM + Guardrails	Metadata-only citation
Retrieval	Static top_k	Dynamic + Reranker
🔐 Future Enhancements

PII redaction layer

Semantic caching

Langfuse tracing

RAGAS evaluation

Drift monitoring

GitHub CI validation

Cross-encoder reranking

Token budgeting

TTL-based meeting deletion

Multi-tenant collections

Observability (Prometheus/Grafana)

🧩 Tech Stack
Layer	Technology
API	FastAPI
Server	Uvicorn
LLM	OpenAI
Embeddings	text-embedding-3-small
Vector Store	Qdrant
UI	Streamlit
Validation	Pydantic
Config	python-dotenv, PyYAML
Package Manager	uv
Python	3.12
🧠 Architectural Philosophy

Python-first for rapid RAG iteration

Hybrid retrieval for precision + recall

Strict citation guardrails for trust

Designed to evolve into distributed architecture

Modular components for enterprise scaling

📌 Summary

This is a production-oriented, scalable Meeting Intelligence RAG system with:

Hybrid retrieval

Strict evidence enforcement

Multi-turn support

Clear scaling roadmap

Observability & compliance-ready design