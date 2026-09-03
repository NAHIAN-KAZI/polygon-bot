"""Tests for app/banking/identity.py: JWT extraction and remote token
introspection verify_jwt (ADR-0008, amended 2026-09-03: the bank does not
hand out its JWT signing secret, so verification now asks the bank's own
/auth/v1/auth/session endpoint who a token belongs to, instead of decoding
an HS256 JWT locally).

verify_jwt makes a real httpx.AsyncClient.get() call, so httpx.AsyncClient.get
is monkeypatched directly here -- matching this codebase's existing style of
monkeypatching the async call site (see tests/test_taxonomy.py,
tests/test_real_adapters.py) rather than pulling in a new test dependency
like respx.

verify_jwt/require_customer_identity are both async def now. Following
tests/test_real_adapters.py's and tests/test_adapter_base.py's pattern, they
are driven with asyncio.run() inside sync test functions rather than adding
pytest-asyncio as a dependency (not present anywhere else in this repo).
"""
import asyncio

import httpx
import pytest

from app.banking.identity import (
    AuthRequiredError,
    CustomerIdentity,
    extract_jwt,
    require_customer_identity,
    verify_jwt,
)
from app.config import settings

TEST_BASE_URL = "https://platform.example.test"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, raise_on_json=False):
        self.status_code = status_code
        self._json_data = json_data
        self._raise_on_json = raise_on_json

    def json(self):
        if self._raise_on_json:
            raise ValueError("response body is not valid JSON")
        return self._json_data


def _install_get(monkeypatch, response=None, exception=None):
    """Patches httpx.AsyncClient.get. Returns the list of captured calls
    (each a dict of url/headers) for later assertions."""
    calls = []

    async def fake_get(self, url, *, headers=None, **kwargs):
        calls.append({"url": url, "headers": headers})
        if exception is not None:
            raise exception
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    return calls


@pytest.fixture
def platform_base_url(monkeypatch):
    """Configure settings.PLATFORM_API_BASE_URL to a known value so the
    outbound request URL can be asserted on deterministically."""
    monkeypatch.setattr(settings, "PLATFORM_API_BASE_URL", TEST_BASE_URL)
    return TEST_BASE_URL


# --- extract_jwt (unchanged by the introspection pivot) ---------------------


def test_extract_jwt_returns_token_from_valid_bearer_header():
    assert extract_jwt("Bearer abc.def.ghi") == "abc.def.ghi"


@pytest.mark.parametrize("header", [
    None,
    "",
    "abc.def.ghi",
    "Bearer",
    "Bearer ",
    "bearer abc.def.ghi",
    "Bearer  abc.def.ghi",
    "Bearer abc.def.ghi ",
    " Bearer abc.def.ghi",
    "Bearer abc def ghi",
])
def test_extract_jwt_returns_none_for_malformed_or_missing_input(header):
    assert extract_jwt(header) is None


# --- CustomerIdentity / AuthRequiredError (unchanged shapes) ----------------


def test_customer_identity_construction_and_equality():
    identity = CustomerIdentity(customer_id="cust-123")
    assert identity.customer_id == "cust-123"
    assert identity == CustomerIdentity(customer_id="cust-123")
    assert identity != CustomerIdentity(customer_id="cust-456")
    assert hash(identity) == hash(CustomerIdentity(customer_id="cust-123"))


def test_auth_required_error_is_a_distinguishable_exception_subclass():
    assert issubclass(AuthRequiredError, Exception)

    try:
        raise AuthRequiredError
    except AuthRequiredError:
        pass
    else:
        raise AssertionError("AuthRequiredError was not caught")

    with pytest.raises(AuthRequiredError):
        try:
            raise AuthRequiredError
        except ValueError:
            raise AssertionError("ValueError handler should not catch AuthRequiredError")


# --- verify_jwt: success path -------------------------------------------------


def test_verify_jwt_returns_identity_for_successful_introspection(monkeypatch, platform_base_url):
    body = {
        "phone": "01615888102",
        "userId": 64,
        "role": "USER",
        "issuedAt": "2026-09-01T00:00:00Z",
        "expiresAt": "2026-09-02T00:00:00Z",
    }
    _install_get(monkeypatch, response=FakeResponse(status_code=200, json_data=body))

    result = asyncio.run(verify_jwt("some.valid.token"))

    assert result == CustomerIdentity(customer_id="01615888102")


# --- verify_jwt: non-200 responses -------------------------------------------


def test_verify_jwt_returns_none_for_401_invalid_or_garbage_token(monkeypatch, platform_base_url):
    _install_get(
        monkeypatch,
        response=FakeResponse(status_code=401, json_data={"message": "invalid token"}),
    )

    assert asyncio.run(verify_jwt("garbage-not-a-real-token")) is None


def test_verify_jwt_returns_none_for_401_missing_token_message(monkeypatch, platform_base_url):
    _install_get(
        monkeypatch,
        response=FakeResponse(status_code=401, json_data={"message": "token is required"}),
    )

    assert asyncio.run(verify_jwt("some.token.value")) is None


@pytest.mark.parametrize("status_code", [400, 403, 404, 500, 503])
def test_verify_jwt_returns_none_for_other_non_200_statuses(monkeypatch, platform_base_url, status_code):
    _install_get(monkeypatch, response=FakeResponse(status_code=status_code, json_data={}))

    assert asyncio.run(verify_jwt("some.token.value")) is None


# --- verify_jwt: malformed/missing claims on an otherwise-200 response ------


def test_verify_jwt_returns_none_when_phone_field_missing(monkeypatch, platform_base_url):
    _install_get(
        monkeypatch,
        response=FakeResponse(status_code=200, json_data={"userId": 64, "role": "USER"}),
    )

    assert asyncio.run(verify_jwt("some.token.value")) is None


@pytest.mark.parametrize("phone_value", [None, 1615888102, 12.5, [], {}])
def test_verify_jwt_returns_none_when_phone_is_not_a_string(monkeypatch, platform_base_url, phone_value):
    _install_get(
        monkeypatch,
        response=FakeResponse(status_code=200, json_data={"phone": phone_value}),
    )

    assert asyncio.run(verify_jwt("some.token.value")) is None


def test_verify_jwt_returns_none_when_phone_is_empty_string(monkeypatch, platform_base_url):
    # "" is a str but falsy -- covered by the `if not phone` guard, distinct
    # from the non-string branch above.
    _install_get(
        monkeypatch,
        response=FakeResponse(status_code=200, json_data={"phone": ""}),
    )

    assert asyncio.run(verify_jwt("some.token.value")) is None


def test_verify_jwt_returns_none_when_response_body_is_not_valid_json(monkeypatch, platform_base_url):
    _install_get(
        monkeypatch,
        response=FakeResponse(status_code=200, raise_on_json=True),
    )

    assert asyncio.run(verify_jwt("some.token.value")) is None


# --- verify_jwt: network errors, must never raise ----------------------------


@pytest.mark.parametrize("exc", [
    httpx.ConnectError("connection refused"),
    httpx.TimeoutException("request timed out"),
    httpx.ReadTimeout("read timed out"),
])
def test_verify_jwt_returns_none_on_network_error(monkeypatch, platform_base_url, exc):
    _install_get(monkeypatch, exception=exc)

    assert asyncio.run(verify_jwt("some.token.value")) is None


# --- verify_jwt: falsy token short-circuits, no HTTP call --------------------


@pytest.mark.parametrize("token", ["", None])
def test_verify_jwt_short_circuits_for_falsy_token_without_http_call(monkeypatch, platform_base_url, token):
    calls = _install_get(monkeypatch, response=FakeResponse(status_code=200, json_data={"phone": "x"}))

    assert asyncio.run(verify_jwt(token)) is None
    assert calls == []


# --- verify_jwt: outbound request shape --------------------------------------


def test_verify_jwt_builds_correct_outbound_request(monkeypatch, platform_base_url):
    calls = _install_get(
        monkeypatch,
        response=FakeResponse(status_code=200, json_data={"phone": "01615888102"}),
    )

    asyncio.run(verify_jwt("abc.def.ghi"))

    # Only httpx.AsyncClient.get was monkeypatched (not .post/.request), so a
    # captured call here also proves the request used GET.
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == f"{TEST_BASE_URL}/auth/v1/auth/session"
    assert call["headers"] == {"Authorization": "Bearer abc.def.ghi"}


# --- require_customer_identity -----------------------------------------------


def test_require_customer_identity_returns_identity_for_valid_token(monkeypatch, platform_base_url):
    _install_get(
        monkeypatch,
        response=FakeResponse(status_code=200, json_data={"phone": "01615888102"}),
    )

    result = asyncio.run(require_customer_identity("Bearer abc.def.ghi"))

    assert result == CustomerIdentity(customer_id="01615888102")


def test_require_customer_identity_raises_for_missing_header():
    with pytest.raises(AuthRequiredError):
        asyncio.run(require_customer_identity(None))


def test_require_customer_identity_raises_for_empty_header():
    with pytest.raises(AuthRequiredError):
        asyncio.run(require_customer_identity(""))


def test_require_customer_identity_raises_for_header_without_bearer_prefix():
    with pytest.raises(AuthRequiredError):
        asyncio.run(require_customer_identity("garbage"))


def test_require_customer_identity_raises_when_introspection_rejects_token(monkeypatch, platform_base_url):
    _install_get(
        monkeypatch,
        response=FakeResponse(status_code=401, json_data={"message": "invalid token"}),
    )

    with pytest.raises(AuthRequiredError):
        asyncio.run(require_customer_identity("Bearer abc.def.ghi"))


def test_require_customer_identity_raises_on_network_error(monkeypatch, platform_base_url):
    _install_get(monkeypatch, exception=httpx.ConnectError("connection refused"))

    with pytest.raises(AuthRequiredError):
        asyncio.run(require_customer_identity("Bearer abc.def.ghi"))


def test_require_customer_identity_end_to_end_success(monkeypatch, platform_base_url):
    calls = _install_get(
        monkeypatch,
        response=FakeResponse(status_code=200, json_data={"phone": "01615888102"}),
    )

    identity = asyncio.run(require_customer_identity("Bearer abc.def.ghi"))

    assert identity == CustomerIdentity(customer_id="01615888102")
    assert len(calls) == 1
    assert calls[0]["headers"] == {"Authorization": "Bearer abc.def.ghi"}


# Note: identity.py does not currently import `logging` or emit any log
# records at all (its docstring promise of "never logs the raw token" is
# structurally true because there is no logging call to leak it from). This
# file has no pre-existing log-capture fixture of its own (unlike
# tests/test_audit.py's `audit_spy`, which targets a different module's
# logger), so per the task instructions a dedicated "no raw token in logs"
# test is skipped here rather than inventing new capture infra for one check
# with nothing to assert against.
