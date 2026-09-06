"""In-memory session store keyed by customer identity (ADR-0005, ADR-0006).

Swappable behind get_session/record_turn (FR-IDENT-06) so a durable/shared
store can replace the module-level dict later without changing callers.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

SESSION_IDLE_TIMEOUT = timedelta(minutes=30)
MAX_TURNS_PER_SESSION = 10


@dataclass(frozen=True)
class ChatTurn:
    timestamp: datetime
    message: str
    classification: dict | None = None


@dataclass
class _SessionEntry:
    last_active_at: datetime
    turns: list[ChatTurn] = field(default_factory=list)


_sessions: dict[str, _SessionEntry] = {}


def _is_expired(entry: _SessionEntry) -> bool:
    return datetime.now(timezone.utc) - entry.last_active_at > SESSION_IDLE_TIMEOUT


def get_session(customer_id: str) -> list[ChatTurn]:
    entry = _sessions.get(customer_id)
    if entry is None or _is_expired(entry):
        return []
    return list(entry.turns)


def record_turn(customer_id: str, turn: ChatTurn) -> None:
    entry = _sessions.get(customer_id)
    if entry is None or _is_expired(entry):
        entry = _SessionEntry(last_active_at=turn.timestamp)
        _sessions[customer_id] = entry

    entry.turns.append(turn)
    if len(entry.turns) > MAX_TURNS_PER_SESSION:
        entry.turns = entry.turns[-MAX_TURNS_PER_SESSION:]
    entry.last_active_at = turn.timestamp


_PENDING_CLARIFICATION_TYPES = {"CLARIFICATION_REQUIRED", "ACCOUNT_SELECTION_REQUIRED"}


def get_classification_context(customer_id: str) -> list[ChatTurn]:
    """Recent turns to feed into classify(), scoped to the actual intended use case:
    resolving a customer's answer to a clarifying question we just asked them. Returns
    the session's turns only if the most recent one is itself an unresolved
    clarification-type outcome — otherwise returns [], since unrelated past turns must
    never bleed into a fresh classification (found live: a contaminated session turned
    3 different questions into 3 identical wrong answers)."""
    turns = get_session(customer_id)
    if not turns:
        return []
    last_classification = turns[-1].classification or {}
    if last_classification.get("type") not in _PENDING_CLARIFICATION_TYPES:
        return []
    return turns
