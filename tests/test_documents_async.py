"""Large uploads are indexed in the background so the request answers at once (T-129)."""
import asyncio

import httpx
import pytest

import app.routes.documents as documents_module
from app import catalog
from app.chunking import chunk_document

from tests.conftest import AUTH_HEADERS

MD = b"# Bank\n\n## Cards\n\n### Visa Infinite\n\nA premium card.\n\nSource: https://x/visa\n"


async def _embed(texts):
    return [[0.1] * 384 for _ in texts]


@pytest.fixture
def stored(isolated_catalog, monkeypatch):
    log = {"upserts": [], "deleted": [], "progress": []}
    monkeypatch.setattr(documents_module, "embed_texts", _embed)
    monkeypatch.setattr(documents_module, "upsert_chunks", lambda doc_id, filename, chunks: log["upserts"].append(doc_id))
    monkeypatch.setattr(documents_module, "delete_by_doc_id", lambda doc_id: log["deleted"].append(doc_id))
    monkeypatch.setattr(documents_module, "_schedule_product_cards", lambda *a: None)
    return log


def run_background(doc_id, filename="kb.md", data=MD):
    chunks = chunk_document(filename, data)
    catalog.add_document(doc_id, filename, len(chunks), status="indexing")

    async def go():
        documents_module._index_in_background(doc_id, filename, chunks)
        await asyncio.gather(*documents_module._background)

    asyncio.run(go())
    return next(d for d in catalog.list_documents() if d["doc_id"] == doc_id)


def test_the_async_flag_answers_202_at_once_with_an_indexing_status(client, stored):
    resp = client.post("/documents?async=true", headers=AUTH_HEADERS, files={"file": ("kb.md", MD, "text/markdown")})
    assert resp.status_code == 202
    body = resp.json()
    assert set(body) == {"doc_id", "filename", "chunk_count", "status"} and body["status"] == "indexing"
    listed = next(d for d in client.get("/documents", headers=AUTH_HEADERS).json() if d["doc_id"] == body["doc_id"])
    assert listed["filename"] == "kb.md" and listed["status"] in ("indexing", "ready")


def test_a_document_with_more_chunks_than_the_limit_is_indexed_in_the_background_without_the_flag(client, stored, monkeypatch):
    monkeypatch.setattr(documents_module.settings, "ASYNC_UPLOAD_CHUNKS", 0)
    resp = client.post("/documents", headers=AUTH_HEADERS, files={"file": ("kb.md", MD, "text/markdown")})
    assert resp.status_code == 202 and resp.json()["status"] == "indexing"


def test_a_small_document_still_answers_200_with_the_unchanged_keys(client, stored):
    resp = client.post("/documents", headers=AUTH_HEADERS, files={"file": ("kb.md", MD, "text/markdown")})
    assert resp.status_code == 200 and set(resp.json()) == {"doc_id", "filename", "chunk_count"}
    assert next(d for d in client.get("/documents", headers=AUTH_HEADERS).json())["status"] == "ready"


def test_background_indexing_ends_ready_with_the_real_chunk_count_and_no_progress_left(stored):
    entry = run_background("d1")
    assert entry["status"] == "ready" and entry["chunk_count"] >= 1 and entry.get("progress") is None
    assert stored["upserts"] == ["d1"]


def test_progress_is_reported_in_batches(stored, monkeypatch):
    seen = []
    real = catalog.update_document
    monkeypatch.setattr(documents_module, "update_document",
                        lambda doc_id, **f: (seen.append(f.get("progress")), real(doc_id, **f))[1])
    monkeypatch.setattr(documents_module.settings, "EMBED_BATCH", 1)
    run_background("d1", data=b"# A\n\n## B\n\n### One\n\n" + b"x " * 200 + b"\n\n### Two\n\n" + b"y " * 200 + b"\n")
    reported = [p for p in seen if p]
    assert reported and reported[-1]["done"] == reported[-1]["total"] and reported[0]["done"] < reported[0]["total"]


def test_a_background_failure_is_a_failed_status_with_the_reason_and_nothing_replaced(stored, monkeypatch):
    catalog.add_document("old", "kb.md", 3)

    async def down(texts):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(documents_module, "embed_texts", down)
    entry = run_background("new")
    assert entry["status"] == "failed" and "unreachable" in entry["error"]
    assert {d["doc_id"] for d in catalog.list_documents()} == {"old", "new"} and stored["deleted"] == []


def test_a_finished_background_index_replaces_the_old_copy_but_not_one_still_indexing(stored):
    catalog.add_document("old", "kb.md", 3)
    catalog.add_document("busy", "kb.md", 3, status="indexing")
    run_background("new")
    ids = {d["doc_id"] for d in catalog.list_documents()}
    assert ids == {"busy", "new"} and stored["deleted"] == ["old"]


def test_after_a_restart_documents_still_marked_indexing_are_failed(isolated_catalog):
    catalog.add_document("a", "a.md", 5, status="indexing")
    catalog.add_document("b", "b.md", 5)
    assert catalog.fail_interrupted() == 1
    by_id = {d["doc_id"]: d for d in catalog.list_documents()}
    assert by_id["a"]["status"] == "failed" and "interrupted" in by_id["a"]["error"] and by_id["b"]["status"] == "ready"
    assert catalog.fail_interrupted() == 0


def test_entries_stored_before_statuses_existed_are_listed_as_ready(isolated_catalog):
    import json
    with open(documents_module.settings.DOCS_METADATA_PATH, "w") as f:
        json.dump({"x": {"doc_id": "x", "filename": "old.md", "chunk_count": 2, "uploaded_at": "2026-01-01"}}, f)
    assert catalog.list_documents()[0]["status"] == "ready"
