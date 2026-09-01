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
