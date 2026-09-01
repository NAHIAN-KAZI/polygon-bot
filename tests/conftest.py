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


@pytest.fixture
def isolated_catalog(monkeypatch, tmp_path):
    """Point the document catalog at a throwaway file so tests never touch
    the real /app/data/documents.json and don't leak state between tests."""
    catalog_path = tmp_path / "documents.json"
    monkeypatch.setattr(settings, "DOCS_METADATA_PATH", str(catalog_path))
    return catalog_path
