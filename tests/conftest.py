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
    """Missing-field clarifying questions are LLM-worded in production
    (app.routes.chat._generate_clarification_question), falling back to the
    deterministic templates on any failure. Tests default to that fallback so they
    stay deterministic and never call a live Ollama; tests of the generator itself
    capture the real function at import time and/or re-patch it explicitly."""
    import app.routes.chat as chat_module

    async def _disabled(*args, **kwargs):
        return None

    monkeypatch.setattr(chat_module, "_generate_clarification_question", _disabled)

    # Same for the LLM rewording of fact-based replies and the LLM account pick:
    # tests see the code-decided facts verbatim and never call a live Ollama.
    async def _identity(facts, customer_message):
        return facts

    async def _no_pick(message, candidates):
        return None

    monkeypatch.setattr(chat_module, "_phrase", _identity)
    monkeypatch.setattr(chat_module, "_llm_pick_candidate", _no_pick)

    # Freeze grounding check (an extra LLM call): pass the classification through
    # unchanged in tests; tests of the check itself capture the real function.
    async def _as_classified(result, message, recent_turns):
        return result

    monkeypatch.setattr(chat_module, "_ground_freeze_request", _as_classified)

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
