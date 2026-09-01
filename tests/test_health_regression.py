"""Regression test for GET /health, per INTEGRATION.md: no auth required,
returns {"status": "ok"|"degraded", "ollama": bool, "qdrant": bool}.
"""
import app.main as main_module


def test_health_requires_no_api_key_and_reports_ok_when_both_services_up(client, monkeypatch):
    async def fake_check_ollama():
        return True

    def fake_check_qdrant():
        return True

    monkeypatch.setattr(main_module, "check_ollama", fake_check_ollama)
    monkeypatch.setattr(main_module, "check_qdrant", fake_check_qdrant)

    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "ollama": True, "qdrant": True}


def test_health_reports_degraded_when_a_dependency_is_down(client, monkeypatch):
    async def fake_check_ollama():
        return False

    def fake_check_qdrant():
        return True

    monkeypatch.setattr(main_module, "check_ollama", fake_check_ollama)
    monkeypatch.setattr(main_module, "check_qdrant", fake_check_qdrant)

    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["ollama"] is False
