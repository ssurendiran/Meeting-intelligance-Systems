from typing import List, Dict, Any
from qdrant_client import QdrantClient
from openai import OpenAI

from app.core.config import settings


def _embed_query(q: str) -> List[float]:
    oc = OpenAI(api_key=settings.openai_api_key)
    resp = oc.embeddings.create(model=settings.embedding_model, input=[q])
    return resp.data[0].embedding


def retrieve(meeting_id: str, question: str, top_k: int) -> List[Dict[str, Any]]:
    qc = QdrantClient(url=settings.qdrant_url)
    qvec = _embed_query(question)

    res = qc.query_points(
        collection_name=settings.qdrant_collection,
        query=qvec,
        limit=top_k,
        with_payload=True,
        query_filter={
            "must": [{"key": "meeting_id", "match": {"value": meeting_id}}]
        },
    )

    # res.points contains ScoredPoint items
    results: List[Dict[str, Any]] = []
    for p in res.points:
        payload = p.payload or {}
        results.append(
            {
                "score": float(p.score),
                "file": payload.get("file"),
                "line_start": payload.get("line_start"),
                "line_end": payload.get("line_end"),
                "chunk_id": payload.get("chunk_id"),
                "text": payload.get("text", ""),
            }
        )
    return results
