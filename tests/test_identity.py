"""Tests for app/banking/identity.py: JWT extraction and the fail-closed
verify_jwt stub (ADR-0008).
"""
import pytest

from app.banking import identity as identity_module
from app.banking.identity import (
    AuthRequiredError,
    CustomerIdentity,
    extract_jwt,
    require_customer_identity,
    verify_jwt,
)


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


def test_verify_jwt_never_raises_and_always_returns_none():
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


def test_require_customer_identity_raises_for_well_formed_token_due_to_stub_verify_jwt():
    # verify_jwt is currently a fail-closed stub (ADR-0008) that always
    # returns None, so even a well-formed Bearer token is rejected today.
    # This assertion will need to flip once real JWT verification lands.
    with pytest.raises(AuthRequiredError):
        require_customer_identity("Bearer some.jwt.token")


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
