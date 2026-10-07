import os

# Must happen before `app.config` (and anything importing it) is loaded, since
# Settings reads environment variables once at class-definition time.
os.environ.setdefault("API_KEY", "test-api-key")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

AUTH_HEADERS = {"X-API-Key": settings.API_KEY}


@pytest.fixture
def client():
    # Not entered as a context manager on purpose: this skips the app's
    # startup event (ensure_collection, a real Qdrant call), keeping these
    # regression tests independent of any live backing service.
    return TestClient(app)


@pytest.fixture(autouse=True)
def _no_generated_clarifications(monkeypatch):
    """Every customer-facing message is LLM-composed in production (T-77,
    app.conversation.composer). Tests swap in a deterministic rendering of the
    composer's inputs -- "<kind>: label: value ..." -- so they assert on what the
    message must convey (kind, facts, exact values), never on model wording, and
    never call a live Ollama. Tests of the composer itself import it directly."""
    import app.routes.chat as chat_module
    from app.conversation.composer import facts_listing

    def _render(kind, facts, must_include):
        listing = facts_listing({**facts, **(must_include or {})})
        return f"{kind}: " + listing.replace("\n", "; ")

    async def _fake_compose(kind, facts, *, message="", history=None, must_include=None):
        return _render(kind, facts, must_include)

    async def _fake_compose_stream(kind, facts, *, message="", history=None, must_include=None):
        yield _render(kind, facts, must_include)

    monkeypatch.setattr(chat_module, "compose", _fake_compose)
    monkeypatch.setattr(chat_module, "compose_stream", _fake_compose_stream)

    # Reading a reply to a pending yes/no or verification step is a model call in
    # production. Tests use the structured paths for real (payload.confirm, secret
    # shapes) and a small stand-in for typed text; tests of the reader patch httpx.
    real_reader = chat_module._read_pending_reply

    async def _fake_reader(question, message, payload):
        if (isinstance(payload, dict) and isinstance(payload.get("confirm"), bool)) \
                or chat_module._has_secret_fields(payload) \
                or chat_module._looks_like_typed_secret(message):
            return await real_reader(question, message, payload)
        text = (message or "").strip().lower().rstrip(".!")
        if text in {"yes", "y", "ok", "okay", "sure", "confirm", "go ahead", "yes please"}:
            return "confirm"
        if text in {"no", "n", "cancel", "stop", "no thanks", "don't", "nope"}:
            return "decline"
        return "other" if len(text.split()) > 3 else "unsure"

    monkeypatch.setattr(chat_module, "_read_pending_reply", _fake_reader)

    async def _no_pick(message, candidates):
        return None

    monkeypatch.setattr(chat_module, "_llm_pick_candidate", _no_pick)

    # Freeze grounding check (an extra LLM call): pass the classification through
    # unchanged in tests; tests of the check itself capture the real function.
    async def _as_classified(result, message, recent_turns):
        return result

    monkeypatch.setattr(chat_module, "_ground_freeze_request", _as_classified)

    # Slot filling for a pending question is a model call: off by default in tests
    # (the turn is classified as usual); slot-filling tests patch it explicitly.
    async def _no_fill(recent_turns, message):
        return None

    monkeypatch.setattr(chat_module, "_llm_fill_pending_fields", _no_fill)

    # Looking for still-missing required fields in the SAME message is a model call too:
    # off by default (the classification stands); tests of it capture the real function.
    async def _unchanged(result, message):
        return result

    monkeypatch.setattr(chat_module, "_fill_known_from_message", _unchanged)

    # Checking that a transfer's destination was actually written is a model call too: off
    # by default (the classification stands); tests of it capture the real function.
    async def _destination_ok(result, message):
        return result

    monkeypatch.setattr(chat_module, "_ground_transfer_destination", _destination_ok)

    # Checking that a request names both an action and what it is for is a model call too:
    # off by default (the classification stands); tests of it capture the real function.
    async def _action_ok(result, message):
        return result

    monkeypatch.setattr(chat_module, "_ground_requested_action", _action_ok)

    # Telling "unfreeze" apart from "freeze" is a model call: off by default (never an
    # undo request); tests of it patch httpx or this function explicitly.
    async def _no_undo(messages):
        return None

    monkeypatch.setattr(chat_module, "_undo_request", _no_undo)

    # Streamed reply: tests use the non-streamed path (same prompt and checks),
    # which they already fake via httpx.AsyncClient.post.
    async def _one_piece(message, service, subservice, data):
        yield await chat_module._synthesize_reply(message, service, subservice, data)

    monkeypatch.setattr(chat_module, "_stream_reply", _one_piece)

    # Stage-1 domain pick: default to "no domain" (full single-stage prompt) so
    # classify() tests see exactly one Ollama call; two-stage tests patch it.
    import app.banking.routing as routing_module

    async def _no_domain(message, recent_turns):
        return None

    monkeypatch.setattr(routing_module, "_pick_domain", _no_domain)


@pytest.fixture
def isolated_catalog(monkeypatch, tmp_path):
    """Point the document catalog at a throwaway file so tests never touch
    the real /app/data/documents.json and don't leak state between tests."""
    catalog_path = tmp_path / "documents.json"
    monkeypatch.setattr(settings, "DOCS_METADATA_PATH", str(catalog_path))
    return catalog_path
