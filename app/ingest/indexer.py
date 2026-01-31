from typing import List
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from openai import OpenAI

from app.core.config import settings
from .chunker import Chunk
import uuid

NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678") 


def stable_point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, chunk_id))


def get_qdrant() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection(client: QdrantClient, vector_size: int) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection in existing:
        return
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    oc = OpenAI(api_key=settings.openai_api_key)
    resp = oc.embeddings.create(model=settings.embedding_model, input=texts)
    # keep order
    return [d.embedding for d in resp.data]


def index_chunks(chunks: List[Chunk]) -> int:
    if not chunks:
        return 0

    vectors = embed_texts([c.text for c in chunks])
    vector_size = len(vectors[0])

    qc = get_qdrant()
    ensure_collection(qc, vector_size)

    points: List[PointStruct] = []
    for i, c in enumerate(chunks):
        points.append(
          PointStruct(
    id=stable_point_id(c.payload["chunk_id"]),
    vector=vectors[i],
    payload={**c.payload, "text": c.text},
)

        )

    qc.upsert(collection_name=settings.qdrant_collection, points=points)
    return len(points)
