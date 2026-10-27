import asyncio
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app.auth import require_api_key
from app.chunking import chunk_document
from app.config import settings
from app.embeddings import embed_texts
from app.vectorstore import upsert_chunks, delete_by_doc_id, iter_payloads
from app.catalog import add_document, list_documents, remove_document, update_document
from app.knowledge import catalogue, product_cards

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])

ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")
_background: set[asyncio.Task] = set()   # keeps running tasks referenced until they finish


def _schedule_product_cards(doc_id: str, filename: str, chunks: list[dict]) -> None:
    """Build the product cards of a stored document after the upload has answered: it takes a minute or two."""
    async def run():
        try:
            product_cards.save(doc_id, filename, await product_cards.build(chunks))
        except Exception:  # noqa: BLE001
            logger.exception("product cards for %s could not be built", filename)

    task = asyncio.get_running_loop().create_task(run())
    _background.add(task)
    task.add_done_callback(_background.discard)
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024


def _embedding_error(e: Exception) -> HTTPException:
    """What went wrong while indexing, as the HTTP error the caller sees (or the reason a background job failed)."""
    if isinstance(e, httpx.HTTPStatusError):
        return HTTPException(status_code=400, detail=f"Embedding model rejected the request: {e.response.text.strip()}")
    if isinstance(e, httpx.HTTPError):
        return HTTPException(status_code=502, detail="Embedding model (Ollama) is unreachable")
    return HTTPException(status_code=502, detail="Vector store (Qdrant) is unreachable")


async def _index(doc_id: str, filename: str, chunks: list, progress=None) -> list[dict]:
    """Embed the chunks (in batches, reporting progress) and store them. Raises HTTPException."""
    texts = [c.text for c in chunks]
    try:
        vectors: list = []
        for start in range(0, len(texts), settings.EMBED_BATCH):
            vectors.extend(await embed_texts(texts[start:start + settings.EMBED_BATCH]))
            if progress:
                progress(len(vectors), len(texts))
        embedded_chunks = [
            {"embedding": v, "chunk_index": c.chunk_index, "page": c.page, "text": c.text,
             "section": c.section, "heading_path": c.heading_path, "source_url": c.source_url,
             "product": c.product, "group": c.group}
            for c, v in zip(chunks, vectors)
        ]
        upsert_chunks(doc_id, filename, embedded_chunks)
    except Exception as e:  # noqa: BLE001
        raise _embedding_error(e) from e
    return embedded_chunks


def _publish(doc_id: str, filename: str, embedded_chunks: list[dict], already_listed: bool = False) -> None:
    """Make a stored document the current one. A re-upload of the same file replaces the old copy (only now that
    the new one is stored, so a failed upload never leaves the knowledge base without it); otherwise every chunk
    would be answered twice. A copy still being indexed is never replaced."""
    replaced = [d["doc_id"] for d in list_documents()
                if d.get("filename") == filename and d["doc_id"] != doc_id and d.get("status") != "indexing"]
    if already_listed:
        update_document(doc_id, status="ready", chunk_count=len(embedded_chunks), progress=None, error=None)
    else:
        add_document(doc_id, filename, len(embedded_chunks))
    catalogue.invalidate()
    _schedule_product_cards(doc_id, filename, embedded_chunks)
    for old_id in replaced:
        remove_document(old_id)
        product_cards.remove(old_id)
        try:
            delete_by_doc_id(old_id)
        except Exception:
            logger.warning("replaced document %s: its old chunks could not be deleted from the vector store", old_id)


def _index_in_background(doc_id: str, filename: str, chunks: list) -> None:
    """Index a registered ("indexing") document after the upload has answered; the outcome is its status."""
    async def run():
        try:
            def progress(done: int, total: int) -> None:
                update_document(doc_id, progress={"done": done, "total": total})

            _publish(doc_id, filename, await _index(doc_id, filename, chunks, progress), already_listed=True)
        except HTTPException as e:
            logger.warning("indexing %s failed: %s", filename, e.detail)
            update_document(doc_id, status="failed", error=str(e.detail))
        except Exception:  # noqa: BLE001
            logger.exception("indexing %s failed", filename)
            update_document(doc_id, status="failed", error="Indexing failed; upload the document again.")

    task = asyncio.get_running_loop().create_task(run())
    _background.add(task)
    task.add_done_callback(_background.discard)


@router.post("")
async def upload_document(file: UploadFile, background: bool = Query(False, alias="async")):
    """Store and index a document. Small ones answer 200 once indexed. `?async=true`, or a document with more than
    ASYNC_UPLOAD_CHUNKS chunks, answers 202 at once and indexes in the background: embedding a large file takes
    longer than a gateway waits. Poll `GET /documents` for the document's `status` (indexing, ready or failed)."""
    filename = file.filename or "untitled"
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {ALLOWED_EXTENSIONS}")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_MB}MB limit")

    try:
        chunks = chunk_document(filename, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse document: {e}")

    if not chunks:
        raise HTTPException(status_code=400, detail="No extractable text found in document")

    doc_id = str(uuid.uuid4())
    if background or len(chunks) > settings.ASYNC_UPLOAD_CHUNKS:
        add_document(doc_id, filename, len(chunks), status="indexing")
        update_document(doc_id, progress={"done": 0, "total": len(chunks)})
        _index_in_background(doc_id, filename, chunks)
        return JSONResponse(status_code=202, content={"doc_id": doc_id, "filename": filename,
                                                      "chunk_count": len(chunks), "status": "indexing"})

    _publish(doc_id, filename, await _index(doc_id, filename, chunks))
    return {"doc_id": doc_id, "filename": filename, "chunk_count": len(chunks)}


@router.get("")
async def get_documents():
    return list_documents()


@router.get("/product-cards")
async def get_product_cards():
    """Which documents have product cards, how many, and when they were built."""
    return product_cards.summary()


@router.post("/{doc_id}/product-cards", status_code=202)
async def rebuild_product_cards(doc_id: str):
    """Rebuild a stored document's product cards from the chunks in the index (they build on their own after an
    upload; this is for a document uploaded before the cards existed, or after the model changed)."""
    document = next((d for d in list_documents() if d["doc_id"] == doc_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    fields = ["product", "group", "text", "source_url", "chunk_index"]
    _schedule_product_cards(doc_id, document["filename"], list(iter_payloads(fields, doc_id)))
    return {"doc_id": doc_id, "status": "building"}


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    if not remove_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    product_cards.remove(doc_id)
    catalogue.invalidate()
    try:
        delete_by_doc_id(doc_id)
    except Exception:
        raise HTTPException(status_code=502, detail="Vector store (Qdrant) is unreachable; catalog entry was removed, chunks may remain")
    return {"deleted": doc_id}
