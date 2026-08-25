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


def add_document(doc_id: str, filename: str, chunk_count: int) -> None:
    with _lock:
        data = _load()
        data[doc_id] = {
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": chunk_count,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(data)


def list_documents() -> list[dict]:
    with _lock:
        return list(_load().values())


def remove_document(doc_id: str) -> bool:
    with _lock:
        data = _load()
        if doc_id not in data:
            return False
        del data[doc_id]
        _save(data)
        return True
