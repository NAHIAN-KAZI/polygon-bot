"""Structured audit logging for banking-service turns.

Implements SRS §3.6 (FR-SEC-01..04) / FEATURES.md F-07: exactly one
structured JSON log line is emitted per banking-service turn — every branch
other than a pure knowledge-base question (Clarification, UnknownService,
AUTH_REQUIRED, SERVICE_UNAVAILABLE, BANKING_SERVICE) — via a dedicated
stdlib logger, ``banking.audit``.

FR-SEC-03 fields logged: request ID, session key (a hash of the JWT subject
claim — see ``_session_key``), category, service, subservice, adapter name
invoked, outcome (success/failure/unavailable), and latency in milliseconds.
A ``timestamp`` and the raw ``result_type`` are also included since they are
not sensitive and make each line self-sufficient for reconstruction
(NFR-OBS-01) without contradicting FR-SEC-03's field list.

FR-SEC-04 — deliberately never logged, by anyone calling this module: the
raw JWT, the raw ``X-API-Key``, the customer's raw identifier/subject claim,
the original message text, or full adapter response/payload bodies. Callers
must pass only the already-classified routing fields (category/service/
subservice/result type) — never the request body or adapter result data.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from app.banking import adapter_map
from app.banking.identity import CustomerIdentity

logger = logging.getLogger("banking.audit")

Outcome = Literal["success", "failure", "unavailable"]

# Maps each of the 5 `result.type` values the chat contract can emit for a
# banking-service turn (SRS §3.5 FR-CONTRACT-03) onto FR-SEC-03's coarser
# outcome enum.
_OUTCOME_BY_RESULT_TYPE: dict[str, Outcome] = {
    "BANKING_SERVICE": "success",
    "SERVICE_UNAVAILABLE": "unavailable",
    "AUTH_REQUIRED": "failure",
    "UNKNOWN_SERVICE": "failure",
    "CLARIFICATION_REQUIRED": "failure",
}

# Only these result types reflect a resolved taxonomy path where reporting
# "adapter name invoked" is meaningful. CLARIFICATION_REQUIRED never has a
# category/service yet, and UNKNOWN_SERVICE's category/service are — by
# definition — not a valid taxonomy path, so no real adapter maps to them.
_ADAPTER_RESOLVABLE_RESULT_TYPES = {"BANKING_SERVICE", "SERVICE_UNAVAILABLE", "AUTH_REQUIRED"}


def _session_key(customer_identity: CustomerIdentity | None) -> str | None:
    """FR-SEC-03's "session key" is the JWT subject claim, or a hash of it.
    We always hash rather than log it raw (FR-SEC-04) — the real JWT
    subject-claim shape is still an open item (SRS Appendix B #1), so
    hashing our stand-in `customer_id` is the safer default either way.
    """
    if customer_identity is None:
        return None
    digest = hashlib.sha256(customer_identity.customer_id.encode("utf-8")).hexdigest()
    return digest[:16]


def _adapter_name(
    result_type: str | None,
    category: str | None,
    service: str | None,
    subservice: str | None,
) -> str | None:
    if result_type not in _ADAPTER_RESOLVABLE_RESULT_TYPES or not category or not service:
        return None
    try:
        return adapter_map.get_adapter_name(category, service, subservice)
    except Exception:
        return None


def log_banking_turn(
    customer_identity: CustomerIdentity | None,
    turn_classification: dict,
    *,
    latency_ms: float | None = None,
) -> None:
    """Emit exactly one structured JSON audit log line for a banking-service
    turn (FR-SEC-03/F-07).

    Call once per turn, at every branch other than a pure KB question, right
    after that branch's `turn_classification` dict (``type``/``category``/
    ``service``/``subservice``) has been built.

    Never pass raw JWTs, API keys, message text, or adapter response bodies
    in — only the routing fields already present on `turn_classification`.
    """
    result_type = turn_classification.get("type")
    category = turn_classification.get("category")
    service = turn_classification.get("service")
    subservice = turn_classification.get("subservice")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": uuid.uuid4().hex,
        "session_key": _session_key(customer_identity),
        "category": category,
        "service": service,
        "subservice": subservice,
        "adapter_name": _adapter_name(result_type, category, service, subservice),
        "result_type": result_type,
        "outcome": _OUTCOME_BY_RESULT_TYPE.get(result_type, "failure"),
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
    }
    logger.info(json.dumps(entry))
