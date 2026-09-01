"""Tests for app/banking/identity.py: JWT extraction and the fail-closed
verify_jwt stub (ADR-0008).
"""
import pytest

from app.banking.identity import CustomerIdentity, extract_jwt, verify_jwt


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
