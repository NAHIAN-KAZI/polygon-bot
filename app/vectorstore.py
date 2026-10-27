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
                # Markdown only (None otherwise): where the chunk sits and which product it is about.
                "section": c.get("section"),
                "heading_path": c.get("heading_path") or [],
                "source_url": c.get("source_url"),
                "product": c.get("product"),
                "group": c.get("group"),
            },
        )
        for c in chunks
    ]
    _client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)


def _hit_dict(h) -> dict:
    return {
        "score": h.score,
        "doc_id": h.payload.get("doc_id"),
        "filename": h.payload.get("filename"),
        "page": h.payload.get("page"),
        "text": h.payload.get("text"),
        "section": h.payload.get("section"),
        "heading_path": h.payload.get("heading_path") or [],
        "source_url": h.payload.get("source_url"),
        "product": h.payload.get("product"),
        "group": h.payload.get("group"),
    }


def search(query_vector: list[float], top_k: int) -> list[dict]:
    hits = _client.search(
        collection_name=settings.QDRANT_COLLECTION,
        query_vector=query_vector,
        limit=top_k,
        score_threshold=settings.MIN_RELEVANCE_SCORE,
    )
    return [_hit_dict(h) for h in hits]


def search_in(query_vector: list[float], limit: int, products: list[str] | None = None) -> list[dict]:
    """Nearest chunks with no score floor (the caller ranks and filters), optionally only those of the named
    products. Each hit carries its point `id` so results of several searches can be merged."""
    query_filter = qm.Filter(must=[qm.FieldCondition(key="product", match=qm.MatchAny(any=products))]) \
        if products else None
    hits = _client.search(collection_name=settings.QDRANT_COLLECTION, query_vector=query_vector, limit=limit,
                          query_filter=query_filter)
    return [{**_hit_dict(h), "id": str(h.id)} for h in hits]


def iter_payloads(fields: list[str]):
    """Every stored point's payload, limited to `fields` (no vectors): for building small summaries of the index."""
    offset = None
    while True:
        points, offset = _client.scroll(collection_name=settings.QDRANT_COLLECTION, limit=500, offset=offset,
                                        with_payload=fields, with_vectors=False)
        for point in points:
            yield point.payload or {}
        if offset is None:
            return


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
