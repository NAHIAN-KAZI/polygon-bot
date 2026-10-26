"""Regression tests for the pre-banking-extension behavior of the /documents
endpoints, per INTEGRATION.md and app/routes/documents.py.

Embedding (Ollama) and vector upsert/delete (Qdrant) are mocked at the call
sites used by app/routes/documents.py; chunking runs for real since it's
pure text processing with no external dependency for .txt/.md input. The
document catalog is redirected to a throwaway file per test via the
`isolated_catalog` fixture so no test touches real catalog state.
"""
import app.routes.documents as documents_module

from tests.conftest import AUTH_HEADERS


async def _fake_embed_texts(texts):
    return [[0.1] * 384 for _ in texts]


def _fake_upsert_chunks(doc_id, filename, chunks):
    return None


def _fake_delete_by_doc_id(doc_id):
    return None


def _install_fakes(monkeypatch):
    monkeypatch.setattr(documents_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(documents_module, "upsert_chunks", _fake_upsert_chunks)
    monkeypatch.setattr(documents_module, "delete_by_doc_id", _fake_delete_by_doc_id)


def test_upload_txt_document_returns_200_with_metadata(client, isolated_catalog, monkeypatch):
    _install_fakes(monkeypatch)

    files = {"file": ("notes.txt", b"This is a simple test document about refunds.", "text/plain")}
    resp = client.post("/documents", headers=AUTH_HEADERS, files=files)

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"doc_id", "filename", "chunk_count"}
    assert body["filename"] == "notes.txt"
    assert body["chunk_count"] >= 1


def test_upload_markdown_document_returns_200_with_metadata(client, isolated_catalog, monkeypatch):
    _install_fakes(monkeypatch)

    content = b"# Heading\n\nSome markdown content about accounts.\n"
    files = {"file": ("handbook.md", content, "text/markdown")}
    resp = client.post("/documents", headers=AUTH_HEADERS, files=files)

    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "handbook.md"
    assert body["chunk_count"] >= 1


def test_upload_unsupported_extension_returns_400(client, isolated_catalog, monkeypatch):
    _install_fakes(monkeypatch)

    files = {"file": ("malware.exe", b"binary-ish-data", "application/octet-stream")}
    resp = client.post("/documents", headers=AUTH_HEADERS, files=files)

    assert resp.status_code == 400


def test_upload_without_api_key_returns_401(client, isolated_catalog, monkeypatch):
    _install_fakes(monkeypatch)

    files = {"file": ("notes.txt", b"hello", "text/plain")}
    resp = client.post("/documents", files=files)

    assert resp.status_code == 401


def test_list_documents_returns_a_list(client, isolated_catalog):
    resp = client.get("/documents", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_delete_existing_document_returns_200(client, isolated_catalog, monkeypatch):
    _install_fakes(monkeypatch)

    files = {"file": ("notes.txt", b"Some content about accounts.", "text/plain")}
    upload_resp = client.post("/documents", headers=AUTH_HEADERS, files=files)
    doc_id = upload_resp.json()["doc_id"]

    delete_resp = client.delete(f"/documents/{doc_id}", headers=AUTH_HEADERS)

    assert delete_resp.status_code == 200

    listing = client.get("/documents", headers=AUTH_HEADERS).json()
    assert all(d["doc_id"] != doc_id for d in listing)


def test_delete_nonexistent_document_returns_404(client, isolated_catalog):
    resp = client.delete("/documents/does-not-exist", headers=AUTH_HEADERS)

    assert resp.status_code == 404


# --- re-upload replaces the old copy (T-111) --------------------------------------------------------------


def _track(monkeypatch):
    deleted, stored = [], []
    monkeypatch.setattr(documents_module, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(documents_module, "upsert_chunks", lambda doc_id, filename, chunks: stored.append((doc_id, chunks)))
    monkeypatch.setattr(documents_module, "delete_by_doc_id", lambda doc_id: deleted.append(doc_id))
    return deleted, stored


def test_uploading_the_same_filename_again_replaces_the_old_copy(client, isolated_catalog, monkeypatch):
    deleted, _stored = _track(monkeypatch)
    files = lambda body: {"file": ("faq.md", body, "text/markdown")}  # noqa: E731
    first = client.post("/documents", headers=AUTH_HEADERS, files=files(b"## A\n\nfirst version of the text"))
    second = client.post("/documents", headers=AUTH_HEADERS, files=files(b"## A\n\nsecond version of the text"))
    assert set(second.json()) == {"doc_id", "filename", "chunk_count"}      # the response contract is unchanged
    assert deleted == [first.json()["doc_id"]]
    listed = client.get("/documents", headers=AUTH_HEADERS).json()
    assert [d["doc_id"] for d in listed] == [second.json()["doc_id"]]


def test_a_different_filename_is_not_replaced(client, isolated_catalog, monkeypatch):
    deleted, _stored = _track(monkeypatch)
    client.post("/documents", headers=AUTH_HEADERS, files={"file": ("a.md", b"## A\n\ntext one", "text/markdown")})
    client.post("/documents", headers=AUTH_HEADERS, files={"file": ("b.md", b"## B\n\ntext two", "text/markdown")})
    assert deleted == []
    assert len(client.get("/documents", headers=AUTH_HEADERS).json()) == 2


def test_a_failed_reupload_leaves_the_old_copy_in_place(client, isolated_catalog, monkeypatch):
    deleted, _stored = _track(monkeypatch)
    first = client.post("/documents", headers=AUTH_HEADERS, files={"file": ("faq.md", b"## A\n\nfirst", "text/markdown")})

    def boom(doc_id, filename, chunks):
        raise RuntimeError("vector store down")

    monkeypatch.setattr(documents_module, "upsert_chunks", boom)
    failed = client.post("/documents", headers=AUTH_HEADERS, files={"file": ("faq.md", b"## A\n\nsecond", "text/markdown")})
    assert failed.status_code == 502
    assert deleted == []
    assert [d["doc_id"] for d in client.get("/documents", headers=AUTH_HEADERS).json()] == [first.json()["doc_id"]]


def test_the_chunk_metadata_reaches_the_vector_store(client, isolated_catalog, monkeypatch):
    _deleted, stored = _track(monkeypatch)
    client.post("/documents", headers=AUTH_HEADERS, files={"file": ("kb.md", b"## Cards\n\n### Visa Card\n\nA card for everyday spending anywhere.\n\nSource: http://x/visa\n", "text/markdown")})
    chunk = stored[0][1][0]
    assert (chunk["product"], chunk["group"], chunk["source_url"]) == ("Visa Card", "Cards", "http://x/visa")
    assert chunk["heading_path"] == ["Cards", "Visa Card"] and chunk["section"] == "Visa Card"
