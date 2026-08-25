import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import settings

_client = QdrantClient(url=settings.QDRANT_URL)


def ensure_collection() -> None:
    existing = [c.name for c in _client.get_collections().collections]
    if settings.QDRANT_COLLECTION not in existing:
        _client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=qm.VectorParams(size=settings.EMBED_DIM, distance=qm.Distance.COSINE),
        )


def upsert_chunks(doc_id: str, filename: str, chunks: list[dict]) -> None:
    points = [
        qm.PointStruct(
            id=str(uuid.uuid4()),
            vector=c["embedding"],
            payload={
                "doc_id": doc_id,
                "filename": filename,
                "chunk_index": c["chunk_index"],
                "page": c["page"],
                "text": c["text"],
            },
        )
        for c in chunks
    ]
    _client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)


def search(query_vector: list[float], top_k: int) -> list[dict]:
    hits = _client.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=query_vector,
        limit=top_k,
        score_threshold=settings.MIN_RELEVANCE_SCORE,
    )
    return [
        {
            "score": h.score,
            "doc_id": h.payload.get("doc_id"),
            "filename": h.payload.get("filename"),
            "page": h.payload.get("page"),
            "text": h.payload.get("text"),
        }
        for h in hits
    ]


def delete_by_doc_id(doc_id: str) -> None:
    _client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])
        ),
    )


def check_qdrant() -> bool:
    try:
        _client.get_collections()
        return True
    except Exception:
        return False
