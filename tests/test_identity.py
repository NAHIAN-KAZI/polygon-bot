"""Tests for app/banking/identity.py: JWT extraction and real HS256
verify_jwt verification (ADR-0008, amended 2026-09-03).
"""
import time

import jwt
import pytest

from app.banking import identity as identity_module
from app.banking.identity import (
    AuthRequiredError,
    CustomerIdentity,
    extract_jwt,
    require_customer_identity,
    verify_jwt,
)
from app.config import settings

TEST_SECRET = "test-secret"
TEST_ISSUER = "internet-banking"


def _make_token(secret=TEST_SECRET, sub="cust-123", iss=TEST_ISSUER, exp_delta=900, **extra_claims):
    """Mint an HS256 JWT for tests. exp_delta is seconds from now; pass a
    negative value to produce an already-expired token. Pass exp_delta=None
    to omit the exp claim entirely."""
    claims = dict(extra_claims)
    if sub is not None:
        claims["sub"] = sub
    if iss is not None:
        claims["iss"] = iss
    if exp_delta is not None:
        claims["exp"] = int(time.time()) + exp_delta
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
def configured_secret(monkeypatch):
    """Configure JWT_HS256_SECRET (and issuer) as the codebase's existing
    monkeypatch-settings convention (see conftest.py's isolated_catalog)."""
    monkeypatch.setattr(settings, "JWT_HS256_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "JWT_ISSUER", TEST_ISSUER)
    return settings


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


def test_verify_jwt_never_raises_and_always_returns_none_when_secret_unconfigured():
    # settings.JWT_HS256_SECRET is left at its real default (empty string) in
    # this test, so verify_jwt fails closed per NFR-SEC-01 before it ever
    # attempts to decode any of these — well-formed, garbage, or otherwise.
    candidate_tokens = [
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "",
        "not-a-jwt-at-all",
        "Bearer abc.def.ghi",
        "....",
        "a" * 10000,
    ]
    for token in candidate_tokens:
        result = verify_jwt(token)
        assert result is None


def test_verify_jwt_never_raises_on_malformed_tokens_when_secret_configured(configured_secret):
    # Same malformed/garbage inputs as above, but now with a real secret
    # configured so verify_jwt actually attempts to decode them. PyJWT's
    # DecodeError/InvalidTokenError family must all funnel to None, never
    # propagate as an exception.
    candidate_tokens = [
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "",
        "not-a-jwt-at-all",
        "Bearer abc.def.ghi",
        "....",
        "a" * 10000,
        _make_token()[:20],  # truncated JWT
    ]
    for token in candidate_tokens:
        result = verify_jwt(token)
        assert result is None


def test_customer_identity_construction_and_equality():
    identity = CustomerIdentity(customer_id="cust-123")
    assert identity.customer_id == "cust-123"
    assert identity == CustomerIdentity(customer_id="cust-123")
    assert identity != CustomerIdentity(customer_id="cust-456")
    assert hash(identity) == hash(CustomerIdentity(customer_id="cust-123"))


def test_require_customer_identity_raises_for_missing_header():
    with pytest.raises(AuthRequiredError):
        require_customer_identity(None)


def test_require_customer_identity_raises_for_empty_header():
    with pytest.raises(AuthRequiredError):
        require_customer_identity("")


def test_require_customer_identity_raises_for_header_without_bearer_prefix():
    with pytest.raises(AuthRequiredError):
        require_customer_identity("garbage")


def test_require_customer_identity_raises_for_well_formed_but_unverifiable_token():
    # Real JWT verification has landed (ADR-0008 amendment 2026-09-03), but
    # settings.JWT_HS256_SECRET is left at its real default (empty) in this
    # test, so verify_jwt still fails closed per NFR-SEC-01 and even a
    # syntactically well-formed Bearer token is rejected.
    with pytest.raises(AuthRequiredError):
        require_customer_identity("Bearer some.jwt.token")


def test_require_customer_identity_raises_end_to_end_for_wrong_secret_token(configured_secret):
    # End-to-end (extract -> verify -> raise) check that a token signed with
    # the wrong secret is rejected even once a real secret is configured.
    token = _make_token(secret="a-different-secret")
    with pytest.raises(AuthRequiredError):
        require_customer_identity(f"Bearer {token}")


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


def test_require_customer_identity_returns_identity_on_successful_verification(monkeypatch):
    expected_identity = CustomerIdentity(customer_id="cust-789")
    monkeypatch.setattr(identity_module, "verify_jwt", lambda token: expected_identity)

    result = require_customer_identity("Bearer some.jwt.token")

    assert result == expected_identity


# --- Real HS256 verify_jwt behavior (ADR-0008 amendment 2026-09-03) --------


def test_verify_jwt_returns_identity_for_valid_token_correct_secret_and_issuer(configured_secret):
    token = _make_token(sub="cust-123")
    assert verify_jwt(token) == CustomerIdentity(customer_id="cust-123")


def test_verify_jwt_returns_none_for_expired_token(configured_secret):
    token = _make_token(exp_delta=-3600)  # expired an hour ago, beyond leeway
    assert verify_jwt(token) is None


def test_verify_jwt_returns_none_for_wrong_secret(configured_secret):
    token = _make_token(secret="not-the-configured-secret")
    assert verify_jwt(token) is None


def test_verify_jwt_returns_none_for_wrong_issuer(configured_secret):
    token = _make_token(iss="some-other-issuer")
    assert verify_jwt(token) is None


def test_verify_jwt_returns_none_when_issuer_check_disabled_and_no_iss_configured(monkeypatch):
    # settings.JWT_ISSUER == "" disables the issuer check entirely, per the
    # implementation's `if settings.JWT_ISSUER:` guard. A token with no iss
    # claim at all must still verify successfully in that mode.
    monkeypatch.setattr(settings, "JWT_HS256_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "JWT_ISSUER", "")
    token = _make_token(iss=None)
    assert verify_jwt(token) == CustomerIdentity(customer_id="cust-123")


def test_verify_jwt_returns_none_for_token_missing_sub_claim(configured_secret):
    token = _make_token(sub=None)
    assert verify_jwt(token) is None


def test_verify_jwt_returns_none_for_token_with_non_string_sub(configured_secret):
    token = jwt.encode(
        {"sub": 1234567890, "iss": TEST_ISSUER, "exp": int(time.time()) + 900},
        TEST_SECRET,
        algorithm="HS256",
    )
    assert verify_jwt(token) is None


@pytest.mark.parametrize("token", [
    "",
    "not-a-jwt-at-all",
    "Bearer abc.def.ghi",
    "....",
    "a" * 10000,
])
def test_verify_jwt_returns_none_for_malformed_tokens_with_secret_configured(configured_secret, token):
    assert verify_jwt(token) is None


def test_verify_jwt_returns_none_for_truncated_jwt_with_secret_configured(configured_secret):
    full_token = _make_token()
    truncated = full_token[: len(full_token) // 2]
    assert verify_jwt(truncated) is None


def test_verify_jwt_fail_closed_default_rejects_validly_signed_token_when_secret_unconfigured():
    # Critical regression check (NFR-SEC-01): settings.JWT_HS256_SECRET is
    # NOT monkeypatched here and stays at its real default (empty string).
    # A token that is validly signed -- with literally any secret -- must
    # still be rejected, proving the empty-secret gate can't be bypassed by
    # presenting a well-formed, correctly-signed JWT. This is what keeps the
    # other test files that monkeypatch verify_jwt directly or construct
    # CustomerIdentity without going through it safe from this change.
    assert settings.JWT_HS256_SECRET == ""
    token = _make_token(secret="anything-at-all")
    assert verify_jwt(token) is None


def test_require_customer_identity_returns_identity_end_to_end_with_real_verification(configured_secret):
    token = _make_token(sub="cust-456")
    identity = require_customer_identity(f"Bearer {token}")
    assert identity == CustomerIdentity(customer_id="cust-456")
