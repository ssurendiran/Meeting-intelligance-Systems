from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Filter,
    FieldCondition,
    MatchValue,
    Range,
    SparseVector,
    Prefetch,
    FusionQuery,
    Fusion,
)
from app.core.config import settings
from app.core.openai_client import get_openai_client
from app.utils.sparse_encoding import text_to_sparse_indices_values
from app.ingest.meeting_stats import timestamp_to_seconds

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def _embed_query(q: str) -> List[float]:
    """Embed a query string into a dense vector using the configured embedding model.
    Why available: Used by retrieve and retrieve_multi for semantic search; single place for query embedding."""
    oc = get_openai_client()
    resp = oc.embeddings.create(model=settings.embedding_model, input=[q])
    return resp.data[0].embedding


def retrieve(
    meeting_id: str,
    question: str,
    top_k: int,
    speaker_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve top_k chunks for a meeting and question using dense + sparse fusion (RRF). If speaker_filter is set, only chunks where that speaker appears are returned (case-insensitive).
    Why available: Core retrieval used by /ask, /ask_stream, and /summary; hybrid search improves recall over dense-only."""
    qc = QdrantClient(url=settings.qdrant_url)
    qvec = _embed_query(question)
    idx_sparse, val_sparse = text_to_sparse_indices_values(question, mode="query")
    sparse_q = SparseVector(indices=idx_sparse, values=val_sparse)

    # Over-fetch when filtering by speaker so we have enough after filter
    prefetch_limit = max(top_k * 4, 20) if speaker_filter else max(top_k * 2, 20)
    res = qc.query_points(
        collection_name=settings.qdrant_collection,
        prefetch=[
            Prefetch(query=qvec, using=DENSE_VECTOR_NAME, limit=prefetch_limit),
            Prefetch(query=sparse_q, using=SPARSE_VECTOR_NAME, limit=prefetch_limit),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=prefetch_limit,
        with_payload=True,
        query_filter=Filter(
            must=[FieldCondition(key="meeting_id", match=MatchValue(value=meeting_id))]
        ),
    )

    results: List[Dict[str, Any]] = []
    for p in res.points or []:
        chunk = _point_to_chunk(p)
        if speaker_filter and not _chunk_has_speaker(chunk, speaker_filter):
            continue
        results.append(chunk)
    return results[:top_k]


def _point_to_chunk(p, score: float = 0.0) -> Dict[str, Any]:
    """Build chunk dict from Qdrant point (payload + optional score). Record from scroll has no .score."""
    payload = p.payload or {}
    p_score = getattr(p, "score", None)
    return {
        "score": float(p_score) if p_score is not None else score,
        "file": payload.get("file"),
        "line_start": payload.get("line_start"),
        "line_end": payload.get("line_end"),
        "chunk_id": payload.get("chunk_id"),
        "text": payload.get("text", ""),
        "time_start": payload.get("time_start"),
        "time_end": payload.get("time_end"),
        "time_start_sec": payload.get("time_start_sec"),
        "time_end_sec": payload.get("time_end_sec"),
        "speakers": payload.get("speakers") or [],
    }


def _chunk_has_speaker(chunk: Dict[str, Any], speaker: str) -> bool:
    """Return True if chunk's speakers list contains speaker (case-insensitive). Used when speaker_filter is set on retrieve or retrieve_chunks_containing_time."""
    if not speaker or not speaker.strip():
        return True
    speakers = chunk.get("speakers") or []
    key = speaker.strip().lower()
    return any((s or "").strip().lower() == key for s in speakers)


def retrieve_chunks_containing_time(
    meeting_id: str,
    timestamp_sec: int,
    limit: int = 20,
    speaker_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return chunks whose [time_start, time_end] contains the given second. If speaker_filter is set, only chunks where that speaker appears are returned. Uses time_start_sec/time_end_sec when present; otherwise scrolls and filters in Python.
    Why available: Powers 'what was said at HH:MM:SS' by merging time-filtered chunks with semantic retrieval in _ask_retrieve_and_build_context."""
    qc = QdrantClient(url=settings.qdrant_url)
    scroll_limit = limit * 4 if speaker_filter else limit
    scroll_filter = Filter(
        must=[
            FieldCondition(key="meeting_id", match=MatchValue(value=meeting_id)),
            FieldCondition(
                key="time_start_sec",
                range=Range(lte=timestamp_sec),
            ),
            FieldCondition(
                key="time_end_sec",
                range=Range(gte=timestamp_sec),
            ),
        ]
    )
    res, _ = qc.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=scroll_filter,
        limit=scroll_limit,
        with_payload=True,
        with_vectors=False,
    )
    if res:
        out = [_point_to_chunk(p, score=1.0) for p in res]
        if speaker_filter:
            out = [c for c in out if _chunk_has_speaker(c, speaker_filter)]
        return out[:limit]
    # Fallback: no numeric fields (old ingest) — scroll by meeting_id and filter in Python
    fallback_filter = Filter(
        must=[FieldCondition(key="meeting_id", match=MatchValue(value=meeting_id))]
    )
    res, _ = qc.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=fallback_filter,
        limit=500,
        with_payload=True,
        with_vectors=False,
    )
    out: List[Dict[str, Any]] = []
    for p in res or []:
        payload = p.payload or {}
        ts = payload.get("time_start")
        te = payload.get("time_end")
        if ts is not None and te is not None:
            if timestamp_to_seconds(ts) <= timestamp_sec <= timestamp_to_seconds(te):
                chunk = _point_to_chunk(p, score=1.0)
                if speaker_filter and not _chunk_has_speaker(chunk, speaker_filter):
                    continue
                out.append(chunk)
    return out[:limit]


def retrieve_multi(
    meeting_id: str,
    queries: List[str],
    top_k: int,
    speaker_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Multi-query retrieval: run retrieval for each query, merge by chunk_id (keep max score), sort by score descending, return top_k. If speaker_filter is set, only chunks where that speaker appears are returned.
    Why available: Used by /ask and /ask_stream when query_rewriter produces multiple queries; improves recall over a single query."""
    if not queries:
        return []
    if len(queries) == 1:
        return retrieve(meeting_id, queries[0], top_k, speaker_filter=speaker_filter)

    # top_k per query so we have enough to merge; then take top_k total
    per_query = max(2, (top_k + len(queries) - 1) // len(queries))
    by_chunk: Dict[str, Dict[str, Any]] = {}

    for q in queries:
        for item in retrieve(meeting_id, q, per_query, speaker_filter=speaker_filter):
            cid = item.get("chunk_id")
            if not cid:
                continue
            if cid not in by_chunk or item["score"] > by_chunk[cid]["score"]:
                by_chunk[cid] = item

    merged = list(by_chunk.values())
    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged[:top_k]
