from typing import Iterable, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    PointStruct,
    SparseVector,
    SparseVectorParams,
)
import uuid
from app.utils.retry import with_retry
from app.utils.sparse_encoding import text_to_sparse_indices_values

from app.core.config import settings
from app.core.openai_client import get_openai_client
from .chunker import Chunk


NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def stable_point_id(chunk_id: str) -> str:
    """Return a deterministic UUID string for a chunk_id (for Qdrant point id).
    Why available: Qdrant requires stable point IDs for upserts; same chunk_id always maps to same point."""
    return str(uuid.uuid5(NAMESPACE, chunk_id))


def get_qdrant() -> QdrantClient:
    """Return a Qdrant client for the configured QDRANT_URL.
    Why available: Used by indexer and retriever to connect to the vector store."""
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection(client: QdrantClient, vector_size: int) -> None:
    """Create the meeting_chunks collection if it does not exist (dense + sparse vectors)."""
    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection in existing:
        return
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(size=vector_size, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: SparseVectorParams(),
        },
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts into dense vectors using the configured embedding model (with retry).
    Why available: Indexer and retriever need dense embeddings for semantic search; retry handles transient API failures."""
    oc = get_openai_client()
    resp = with_retry(
        lambda: oc.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
    )
    return [d.embedding for d in resp.data]


def index_chunks_stream(chunks: Iterable[Chunk], batch_size: int = 32) -> int:
    """
    Streaming-safe indexer:
    - consumes chunks iterable
    - embeds in batches
    - upserts in batches
    """
    qc = get_qdrant()
    total = 0
    ensured = False

    batch: List[Chunk] = []

    def flush_batch() -> int:
        """Embed the current batch, upsert points to Qdrant, and return the number of points written. Used by index_chunks_stream when batch is full or at end."""
        nonlocal ensured, total
        if not batch:
            return 0

        texts = [c.text for c in batch]
        vectors = embed_texts(texts)

        if not ensured:
            ensure_collection(qc, len(vectors[0]))
            ensured = True

        points: List[PointStruct] = []
        for i, c in enumerate(batch):
            idx_sparse, val_sparse = text_to_sparse_indices_values(c.text, mode="doc")
            points.append(
                PointStruct(
                    id=stable_point_id(c.payload["chunk_id"]),
                    vector={
                        DENSE_VECTOR_NAME: vectors[i],
                        SPARSE_VECTOR_NAME: SparseVector(indices=idx_sparse, values=val_sparse),
                    },
                    payload={**c.payload, "text": c.text},
                )
            )

        qc.upsert(collection_name=settings.qdrant_collection, points=points)
        total += len(points)
        return len(points)

    for c in chunks:
        batch.append(c)
        if len(batch) >= batch_size:
            flush_batch()
            batch = []

    flush_batch()
    return total


def index_chunks(chunks: List[Chunk]) -> int:
    """Index a list of chunks to Qdrant (embed + upsert). Returns total number of points indexed.
    Why available: Non-streaming API used by worker when all chunks are already in memory."""
    return index_chunks_stream(chunks, batch_size=32)
