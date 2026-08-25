import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.auth import require_api_key
from app.chunking import chunk_document
from app.config import settings
from app.embeddings import embed_texts
from app.vectorstore import upsert_chunks, delete_by_doc_id
from app.catalog import add_document, list_documents, remove_document

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])

ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024


@router.post("")
async def upload_document(file: UploadFile):
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
    try:
        vectors = await embed_texts([c.text for c in chunks])
        embedded_chunks = [
            {"embedding": v, "chunk_index": c.chunk_index, "page": c.page, "text": c.text}
            for c, v in zip(chunks, vectors)
        ]
        upsert_chunks(doc_id, filename, embedded_chunks)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"Embedding model rejected the request: {e.response.text.strip()}")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Embedding model (Ollama) is unreachable")
    except Exception:
        raise HTTPException(status_code=502, detail="Vector store (Qdrant) is unreachable")

    add_document(doc_id, filename, len(embedded_chunks))

    return {"doc_id": doc_id, "filename": filename, "chunk_count": len(embedded_chunks)}


@router.get("")
async def get_documents():
    return list_documents()


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    if not remove_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        delete_by_doc_id(doc_id)
    except Exception:
        raise HTTPException(status_code=502, detail="Vector store (Qdrant) is unreachable; catalog entry was removed, chunks may remain")
    return {"deleted": doc_id}
