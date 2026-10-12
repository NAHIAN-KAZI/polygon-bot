"""/demo-login: the demo portal's test-account login. API-key protected, 404 unless
DEMO_LOGIN_USERNAME/PASSWORD are set, and the password never appears in a response."""
import httpx
import pytest

from app.config import settings
from tests.conftest import AUTH_HEADERS


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._body


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_LOGIN_USERNAME", "tester")
    monkeypatch.setattr(settings, "DEMO_LOGIN_PASSWORD", "s3cret-pw")
    monkeypatch.setattr(settings, "PLATFORM_API_BASE_URL", "https://platform.test")


def _platform_replies(monkeypatch, reply):
    seen = {}

    async def fake_post(self, url, *args, **kwargs):
        seen["url"], seen["json"] = url, kwargs.get("json")
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return seen


def test_requires_api_key(client, configured):
    assert client.get("/demo-login").status_code == 401
    assert client.post("/demo-login").status_code == 401


def test_not_configured_is_404(client, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_LOGIN_USERNAME", "")
    monkeypatch.setattr(settings, "DEMO_LOGIN_PASSWORD", "")
    assert client.get("/demo-login", headers=AUTH_HEADERS).status_code == 404
    assert client.post("/demo-login", headers=AUTH_HEADERS).status_code == 404


def test_info_returns_username_only(client, configured):
    resp = client.get("/demo-login", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"username": "tester"}


def test_login_returns_token_and_never_the_password(client, configured, monkeypatch):
    seen = _platform_replies(monkeypatch, _Resp(200, {"token": {"accessToken": "jwt-abc", "refreshToken": "r"}}))
    resp = client.post("/demo-login", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"accessToken": "jwt-abc", "username": "tester"}
    assert "s3cret-pw" not in resp.text
    assert seen["url"] == "https://platform.test/auth/v1/auth/login"
    assert seen["json"] == {"username": "tester", "password": "s3cret-pw"}


def test_platform_rejection_is_502(client, configured, monkeypatch):
    _platform_replies(monkeypatch, _Resp(401, {"message": "Invalid credentials"}))
    resp = client.post("/demo-login", headers=AUTH_HEADERS)
    assert resp.status_code == 502
    assert "Invalid credentials" in resp.json()["detail"]
    assert "s3cret-pw" not in resp.text


def test_missing_token_is_502(client, configured, monkeypatch):
    _platform_replies(monkeypatch, _Resp(200, {"user": {}}))
    assert client.post("/demo-login", headers=AUTH_HEADERS).status_code == 502


def test_platform_unreachable_is_502(client, configured, monkeypatch):
    _platform_replies(monkeypatch, httpx.ConnectError("down"))
    resp = client.post("/demo-login", headers=AUTH_HEADERS)
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Platform login is unreachable"


# --- /demo-config: API key autofill for the demo portal --------------------------


def test_demo_config_off_by_default_is_404(client, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_PORTAL_AUTOFILL_API_KEY", False)
    resp = client.get("/demo-config")
    assert resp.status_code == 404
    assert settings.API_KEY not in resp.text


def test_demo_config_enabled_returns_key_without_auth(client, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_PORTAL_AUTOFILL_API_KEY", True)
    resp = client.get("/demo-config")
    assert resp.status_code == 200
    assert resp.json() == {"apiKey": settings.API_KEY}


def test_demo_config_enabled_but_no_key_is_404(client, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_PORTAL_AUTOFILL_API_KEY", True)
    monkeypatch.setattr(settings, "API_KEY", "")
    assert client.get("/demo-config").status_code == 404
