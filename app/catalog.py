import json
import os
import threading
from datetime import datetime, timezone

from app.config import settings

_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(settings.DOCS_METADATA_PATH):
        return {}
    with open(settings.DOCS_METADATA_PATH, "r") as f:
        return json.load(f)


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(settings.DOCS_METADATA_PATH), exist_ok=True)
    with open(settings.DOCS_METADATA_PATH, "w") as f:
        json.dump(data, f, indent=2)


def add_document(doc_id: str, filename: str, chunk_count: int, status: str = "ready") -> None:
    """Register a document. `status` is "ready" (searchable), "indexing" (being embedded in the background) or
    "failed" (see `error`)."""
    with _lock:
        data = _load()
        data[doc_id] = {
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": chunk_count,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
        }
        _save(data)


def update_document(doc_id: str, **fields) -> None:
    """Change fields of a registered document (status, progress, error, chunk_count); a removed one is left alone."""
    with _lock:
        data = _load()
        if doc_id in data:
            data[doc_id].update(fields)
            _save(data)


def fail_interrupted() -> int:
    """After a restart, a document still marked "indexing" lost its background task: mark it failed."""
    with _lock:
        data = _load()
        stuck = [d for d in data.values() if d.get("status") == "indexing"]
        for d in stuck:
            d["status"] = "failed"
            d["error"] = "Indexing was interrupted by a restart; upload the document again."
        if stuck:
            _save(data)
        return len(stuck)


def list_documents() -> list[dict]:
    """Every document; entries stored before statuses existed are ready."""
    with _lock:
        return [{"status": "ready", **d} for d in _load().values()]


def remove_document(doc_id: str) -> bool:
    with _lock:
        data = _load()
        if doc_id not in data:
            return False
        del data[doc_id]
        _save(data)
        return True
