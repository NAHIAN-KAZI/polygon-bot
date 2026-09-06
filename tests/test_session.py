"""Tests for the in-memory session store in app/banking/session.py.

session.py keeps session state as a module-level global (_sessions), so an
autouse fixture resets it before and after every test to avoid state leaking
between tests (matching tests/test_taxonomy.py's approach for a similar
module-global store).
"""
from datetime import datetime, timedelta, timezone

import pytest

import app.banking.session as session


@pytest.fixture(autouse=True)
def reset_session_state():
    session._sessions.clear()
    yield
    session._sessions.clear()


def _turn(minutes_ago=0, message="hello", classification=None):
    timestamp = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return session.ChatTurn(timestamp=timestamp, message=message, classification=classification)


def test_get_session_returns_empty_list_for_unknown_customer():
    assert session.get_session("cust-unknown") == []


def test_record_turn_then_get_session_returns_turns_in_insertion_order():
    turn1 = _turn(message="first")
    turn2 = _turn(message="second")
    turn3 = _turn(message="third")

    session.record_turn("cust-1", turn1)
    session.record_turn("cust-1", turn2)
    session.record_turn("cust-1", turn3)

    result = session.get_session("cust-1")
    assert [t.message for t in result] == ["first", "second", "third"]


def test_recording_more_than_max_turns_caps_at_max_and_drops_oldest():
    for i in range(11):
        session.record_turn("cust-2", _turn(message=f"turn-{i}"))

    result = session.get_session("cust-2")
    assert len(result) == session.MAX_TURNS_PER_SESSION
    assert [t.message for t in result] == [f"turn-{i}" for i in range(1, 11)]


def test_different_customers_have_independent_session_state():
    session.record_turn("cust-a", _turn(message="a-only"))
    session.record_turn("cust-b", _turn(message="b-only"))

    a_messages = [t.message for t in session.get_session("cust-a")]
    b_messages = [t.message for t in session.get_session("cust-b")]

    assert a_messages == ["a-only"]
    assert b_messages == ["b-only"]


def test_session_expires_after_idle_timeout():
    old_turn = _turn(minutes_ago=31, message="stale")
    session.record_turn("cust-3", old_turn)

    assert session.get_session("cust-3") == []


def test_recording_fresh_turn_after_expiry_does_not_leak_old_turns():
    old_turn = _turn(minutes_ago=31, message="stale")
    session.record_turn("cust-4", old_turn)
    assert session.get_session("cust-4") == []

    fresh_turn = _turn(message="fresh")
    session.record_turn("cust-4", fresh_turn)

    result = session.get_session("cust-4")
    assert [t.message for t in result] == ["fresh"]


def test_chat_turn_construction_with_and_without_classification():
    timestamp = datetime.now(timezone.utc)

    turn_without = session.ChatTurn(timestamp=timestamp, message="no classification")
    assert turn_without.classification is None
    assert turn_without.message == "no classification"
    assert turn_without.timestamp == timestamp

    classification = {"category": "banking", "confidence": 0.9}
    turn_with = session.ChatTurn(timestamp=timestamp, message="classified", classification=classification)
    assert turn_with.classification == classification
    assert turn_with.message == "classified"


# --- get_classification_context (TASKS.md T-24): scoped recent-turns context ---
# --- for classify(), only surfaced when the last turn is itself an unresolved --
# --- clarification-type outcome (CLARIFICATION_REQUIRED / --------------------
# --- ACCOUNT_SELECTION_REQUIRED) — otherwise [], so unrelated past turns never -
# --- bleed into a fresh classification. ---------------------------------------


def test_get_classification_context_returns_empty_list_for_unknown_customer():
    assert session.get_classification_context("cust-unknown") == []


def test_get_classification_context_empty_when_last_turn_has_no_classification():
    session.record_turn("cust-kb", _turn(message="what is the refund policy?", classification=None))

    assert session.get_classification_context("cust-kb") == []


def test_get_classification_context_empty_when_last_turn_is_banking_service():
    session.record_turn(
        "cust-bs",
        _turn(message="what's my balance", classification={"type": "BANKING_SERVICE", "category": "account_info"}),
    )

    assert session.get_classification_context("cust-bs") == []


def test_get_classification_context_empty_when_last_turn_is_auth_required():
    session.record_turn(
        "cust-auth",
        _turn(message="what's my balance", classification={"type": "AUTH_REQUIRED", "category": "account_info"}),
    )

    assert session.get_classification_context("cust-auth") == []


def test_get_classification_context_empty_when_last_turn_is_unknown_service():
    session.record_turn(
        "cust-unknown-svc",
        _turn(message="do the thing", classification={"type": "UNKNOWN_SERVICE", "category": "x"}),
    )

    assert session.get_classification_context("cust-unknown-svc") == []


def test_get_classification_context_empty_when_last_turn_is_service_unavailable():
    session.record_turn(
        "cust-unavail",
        _turn(message="what's my balance", classification={"type": "SERVICE_UNAVAILABLE", "category": "account_info"}),
    )

    assert session.get_classification_context("cust-unavail") == []


def test_get_classification_context_returns_full_history_when_last_turn_is_clarification_required():
    session.record_turn("cust-clar", _turn(message="first", classification=None))
    session.record_turn("cust-clar", _turn(message="second", classification={"type": "BANKING_SERVICE"}))
    session.record_turn(
        "cust-clar",
        _turn(message="which account?", classification={"type": "CLARIFICATION_REQUIRED", "category": None}),
    )

    result = session.get_classification_context("cust-clar")

    assert [t.message for t in result] == ["first", "second", "which account?"]
    assert result == session.get_session("cust-clar")


def test_get_classification_context_returns_full_history_when_last_turn_is_account_selection_required():
    session.record_turn("cust-acct-sel", _turn(message="first", classification=None))
    session.record_turn("cust-acct-sel", _turn(message="second", classification={"type": "BANKING_SERVICE"}))
    session.record_turn(
        "cust-acct-sel",
        _turn(
            message="what's my balance",
            classification={"type": "ACCOUNT_SELECTION_REQUIRED", "category": "account_info"},
        ),
    )

    result = session.get_classification_context("cust-acct-sel")

    assert [t.message for t in result] == ["first", "second", "what's my balance"]
    assert result == session.get_session("cust-acct-sel")


def test_get_classification_context_empty_when_session_expired_even_if_last_turn_was_pending_clarification():
    stale_turn = _turn(
        minutes_ago=31,
        message="which account?",
        classification={"type": "CLARIFICATION_REQUIRED", "category": None},
    )
    session.record_turn("cust-expired-clar", stale_turn)

    assert session.get_classification_context("cust-expired-clar") == []
