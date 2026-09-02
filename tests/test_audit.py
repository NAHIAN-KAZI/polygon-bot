"""Tests for app/banking/audit.py: structured audit logging for
banking-service turns (TASKS.md T-16 / SRS FR-SEC-01..04, F-07).

The stdlib logger (`logging.getLogger("banking.audit")`) is captured by
monkeypatching its bound `info` method directly, matching this codebase's
existing style of monkeypatching call sites rather than pulling in a new
test dependency (see tests/test_taxonomy.py, tests/test_chat_banking_flow.py
for the same "spy" pattern applied elsewhere).
"""
import json

import pytest

import app.banking.audit as audit_module
from app.banking.audit import log_banking_turn
from app.banking.identity import CustomerIdentity

CUSTOMER_ID = "cust-super-secret-123"

# The exact field set FR-SEC-03 calls for (plus timestamp/result_type per the
# module's own docstring). Any field outside this set — in particular a raw
# `payload`/`data` key — would violate FR-SEC-04.
EXPECTED_FIELDS = {
    "timestamp",
    "request_id",
    "session_key",
    "category",
    "service",
    "subservice",
    "adapter_name",
    "result_type",
    "outcome",
    "latency_ms",
}


def _spy():
    calls = []

    def record(msg, *args, **kwargs):
        calls.append(msg)

    record.calls = calls
    return record


@pytest.fixture
def audit_spy(monkeypatch):
    spy = _spy()
    monkeypatch.setattr(audit_module.logger, "info", spy)
    return spy


def _classification(result_type, category="account_info", service="balance", subservice=None):
    return {"type": result_type, "category": category, "service": service, "subservice": subservice}


# --- session_key -------------------------------------------------------------


def test_session_key_is_none_when_no_customer_identity(audit_spy):
    log_banking_turn(None, _classification("CLARIFICATION_REQUIRED", category=None, service=None))

    entry = json.loads(audit_spy.calls[0])
    assert entry["session_key"] is None


def test_session_key_is_hashed_not_the_raw_customer_id(audit_spy):
    identity = CustomerIdentity(customer_id=CUSTOMER_ID)

    log_banking_turn(identity, _classification("BANKING_SERVICE"))

    entry = json.loads(audit_spy.calls[0])
    session_key = entry["session_key"]
    assert isinstance(session_key, str)
    assert len(session_key) == 16
    assert all(c in "0123456789abcdef" for c in session_key)
    assert session_key != CUSTOMER_ID
    assert CUSTOMER_ID not in session_key


def test_session_key_is_deterministic_for_the_same_identity(audit_spy):
    identity = CustomerIdentity(customer_id=CUSTOMER_ID)

    log_banking_turn(identity, _classification("BANKING_SERVICE"))
    log_banking_turn(identity, _classification("BANKING_SERVICE"))

    first = json.loads(audit_spy.calls[0])["session_key"]
    second = json.loads(audit_spy.calls[1])["session_key"]
    assert first == second


# --- outcome mapping ----------------------------------------------------------


@pytest.mark.parametrize("result_type, expected_outcome", [
    ("BANKING_SERVICE", "success"),
    ("SERVICE_UNAVAILABLE", "unavailable"),
    ("AUTH_REQUIRED", "failure"),
    ("UNKNOWN_SERVICE", "failure"),
    ("CLARIFICATION_REQUIRED", "failure"),
])
def test_outcome_mapping_for_each_result_type(audit_spy, result_type, expected_outcome):
    log_banking_turn(None, _classification(result_type))

    entry = json.loads(audit_spy.calls[0])
    assert entry["result_type"] == result_type
    assert entry["outcome"] == expected_outcome


# --- adapter_name --------------------------------------------------------------


@pytest.mark.parametrize("result_type", ["BANKING_SERVICE", "SERVICE_UNAVAILABLE", "AUTH_REQUIRED"])
def test_adapter_name_populated_for_resolvable_result_types_with_valid_path(audit_spy, result_type):
    log_banking_turn(None, _classification(result_type, category="account_info", service="balance"))

    entry = json.loads(audit_spy.calls[0])
    assert entry["adapter_name"] == "real:balance"


@pytest.mark.parametrize("result_type", ["CLARIFICATION_REQUIRED", "UNKNOWN_SERVICE"])
def test_adapter_name_is_none_for_non_resolvable_result_types(audit_spy, result_type):
    log_banking_turn(None, _classification(result_type, category="account_info", service="balance"))

    entry = json.loads(audit_spy.calls[0])
    assert entry["adapter_name"] is None


def test_adapter_name_is_none_when_category_or_service_missing(audit_spy):
    log_banking_turn(None, _classification("AUTH_REQUIRED", category=None, service=None))

    entry = json.loads(audit_spy.calls[0])
    assert entry["adapter_name"] is None


def test_adapter_name_is_none_when_underlying_lookup_raises(audit_spy, monkeypatch):
    def boom(category, service, subservice=None):
        raise ValueError("taxonomy lookup blew up")

    monkeypatch.setattr(audit_module.adapter_map, "get_adapter_name", boom)

    log_banking_turn(None, _classification("BANKING_SERVICE"))

    entry = json.loads(audit_spy.calls[0])
    assert entry["adapter_name"] is None


# --- shape / FR-SEC-04 no-sensitive-data guarantees ---------------------------


def test_emitted_line_is_valid_json_with_exactly_the_expected_field_set(audit_spy):
    identity = CustomerIdentity(customer_id=CUSTOMER_ID)

    log_banking_turn(identity, _classification("BANKING_SERVICE"), latency_ms=42.0)

    raw = audit_spy.calls[0]
    entry = json.loads(raw)  # raises if not valid JSON
    assert set(entry.keys()) == EXPECTED_FIELDS


def test_emitted_line_never_contains_raw_customer_id_or_message_text(audit_spy):
    identity = CustomerIdentity(customer_id=CUSTOMER_ID)
    raw_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjdXN0LXN1cGVyLXNlY3JldC0xMjMifQ.signature"
    message_text = "please transfer $500 to my savings account right now"

    # Only routing fields ever get passed to log_banking_turn — but assert
    # the guarantee holds against the actual emitted line regardless.
    log_banking_turn(identity, _classification("BANKING_SERVICE"), latency_ms=10)

    raw = audit_spy.calls[0]
    assert CUSTOMER_ID not in raw
    assert raw_jwt not in raw
    assert message_text not in raw

    entry = json.loads(raw)
    assert "payload" not in entry
    assert "data" not in entry
    assert "message" not in entry
    assert "jwt" not in entry
    assert "token" not in entry


def test_no_extra_unexpected_keys_beyond_the_documented_field_set(audit_spy):
    log_banking_turn(None, _classification("UNKNOWN_SERVICE"))

    entry = json.loads(audit_spy.calls[0])
    assert entry.keys() - EXPECTED_FIELDS == set()


# --- latency_ms ----------------------------------------------------------------


def test_latency_ms_is_none_when_omitted(audit_spy):
    log_banking_turn(None, _classification("CLARIFICATION_REQUIRED", category=None, service=None))

    entry = json.loads(audit_spy.calls[0])
    assert entry["latency_ms"] is None


def test_latency_ms_rounds_to_two_decimal_places(audit_spy):
    log_banking_turn(None, _classification("BANKING_SERVICE"), latency_ms=123.4567)

    entry = json.loads(audit_spy.calls[0])
    assert entry["latency_ms"] == 123.46


def test_latency_ms_passes_through_when_already_precise(audit_spy):
    log_banking_turn(None, _classification("BANKING_SERVICE"), latency_ms=7)

    entry = json.loads(audit_spy.calls[0])
    assert entry["latency_ms"] == 7.0


# --- exactly-one-log-line invariant ------------------------------------------


def test_log_banking_turn_emits_exactly_one_log_line(audit_spy):
    log_banking_turn(None, _classification("BANKING_SERVICE"))

    assert len(audit_spy.calls) == 1


def test_category_service_subservice_pass_through_from_turn_classification(audit_spy):
    log_banking_turn(
        None,
        _classification("BANKING_SERVICE", category="pay_transfer", service="transfer_funds", subservice="internal"),
    )

    entry = json.loads(audit_spy.calls[0])
    assert entry["category"] == "pay_transfer"
    assert entry["service"] == "transfer_funds"
    assert entry["subservice"] == "internal"
