import copy
import difflib
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.auth import require_api_key
from app.banking import audit
from app.banking.adapters import fulfill_banking_service
from app.banking.adapters.base import (
    AdapterAccountSelectionRequiredError,
    AdapterAuthError,
    AdapterRejectedError,
    AdapterUnavailableError,
    AdapterValidationError,
)
from app.banking.identity import extract_jwt, verify_jwt
from app.banking.routing import (
    AMOUNT_GUIDANCE,
    SERVICE_DESCRIPTIONS,
    BankingService,
    Clarification,
    KbQuestion,
    UnknownService,
    _subservice_ids,
    classify,
    fee_transaction_types,
    _CLARIFICATION_FALLBACK,
)
from app.banking import ui_actions
from app.banking.session import ChatTurn, get_classification_context, get_session, record_turn
from app.banking.taxonomy import get_taxonomy, is_valid_path
from app.config import settings
from app.conversation.composer import (
    _FOREIGN_CURRENCY, build_messages, check_reply, compose, compose_stream, facts_listing, generate_chat,
    unsupported_numbers,
)
from app.embeddings import embed_text
from app.llm import build_prompt, stream_generate
from app.vectorstore import search

# OTP send/verify are deliberately unauthenticated, un-routed platform endpoints (no
# taxonomy triple / adapter_map entry), so they're imported directly.
from app.banking.adapters.real import (
    ADDRESS_FIELDS,
    COMPLAINT_CATEGORIES,
    _is_card_row,
    lookup_recipient,
    send_otp,
    verify_otp,
)

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])

logger = logging.getLogger("chat.requests")


# T-57: the only 3 payload field names that must NEVER reach a log line (request-entry
# logger, per-turn success/failure logger, or anywhere else) -- the OTP code, and either
# re-auth factor accepted by FreezeCardAdapter. `verificationToken` is deliberately NOT
# in this set: it is a short-lived, single-use, bank-issued artifact (not a customer
# secret like a PIN/password), and FR-SEC-04/this task's own log guarantee never named
# it as a 4th field to redact.
_SECRET_PAYLOAD_KEYS = ("pin", "password", "otp")


def _redact_secrets(payload):
    """Copy of `payload` (recursing into nested dicts/lists) with pin/password/otp
    values replaced by a fixed placeholder, for LOGGING only. Never mutates `payload`
    -- the real dict used for the actual OTP/freeze calls is always the original,
    unredacted one; only this copy is ever handed to a logger."""
    if isinstance(payload, dict):
        return {
            key: "[redacted]" if key in _SECRET_PAYLOAD_KEYS else _redact_secrets(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_redact_secrets(item) for item in payload]
    return payload


def _strip_secrets(payload):
    """Copy of `payload` with pin/password/otp keys REMOVED entirely (not
    placeholdered -- a stored "[redacted]" PIN must never be replayable as a real
    value), for anything persisted in session state or echoed back in a `result`
    event. Never mutates `payload`."""
    if isinstance(payload, dict):
        return {
            key: _strip_secrets(value)
            for key, value in payload.items()
            if key not in _SECRET_PAYLOAD_KEYS
        }
    if isinstance(payload, list):
        return [_strip_secrets(item) for item in payload]
    return payload


def _has_secret_fields(payload: dict | None) -> bool:
    return isinstance(payload, dict) and any(payload.get(key) for key in _SECRET_PAYLOAD_KEYS)


def _looks_like_typed_secret(message: str) -> bool:
    """Could this message carry an OTP, PIN or password typed into the chat box? A
    run of 4+ digits anywhere, or a single 4+ char token containing a digit. Shape
    check only -- it protects the secret, it doesn't read intent."""
    text = message.strip()
    if re.search(r"\d{4,}", text):
        return True
    return len(text) >= 4 and not any(ch.isspace() for ch in text) and any(ch.isdigit() for ch in text)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=settings.MAX_TOP_K)
    category: str | None = None
    service: str | None = None
    subservice: str | None = None
    payload: dict | None = None

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


# T-49: deterministic, code-level payload-completeness check for banking services whose
# adapter requires specific payload fields — pre-empts (does not replace) each adapter's
# own guard (e.g. FeesAdapter.fulfill in app/banking/adapters/real.py:299-305), so an
# incomplete payload gets a clarifying question instead of hitting the adapter and
# surfacing as a generic SERVICE_UNAVAILABLE. Adding a future required-payload service is
# a one-line addition here (plus a question builder in _PAYLOAD_CLARIFICATION_BUILDERS
# below) — not new branching logic in _chat_stream.
_REQUIRED_PAYLOAD_FIELDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("fees", "fee_quote"): ("transactionType", "amount"),
    # T-56: transfer/bank_transfer (own_account/city_account/other_bank) and
    # transfer/wallet_transfer (bkash/nagad/rocket/upay) never call a real
    # adapter -- see _chat_stream's dedicated no-adapter branch below -- but
    # still need a complete payload before that deterministic confirmation
    # summary can be built.
    ("transfer", "bank_transfer"): ("accountNumber", "amount"),
    ("transfer", "wallet_transfer"): ("walletNumber", "amount"),
    # T-57: card freeze (category "card_services", real service id
    # "frezz_unfrezz" per ADR-0013 -- not a Polygon-Bot slug). `cardId` is
    # deliberately NOT listed here -- it's resolved via the cards-list
    # adapter (0/1/2+ handling, see _chat_stream's dedicated pre-check
    # before this guard ever runs), never via a plain clarifying question.
    # Only "reason" is a genuine fill-in-the-blank field at this point.
    ("card_services", "frezz_unfrezz"): ("reason",),
    # T-60: beneficiary add (category "polygon_services", distinct service id
    # "beneficiary_add" -- the existing "beneficiary" id stays the read-only
    # list operation, untouched). Mirrors the real CreateBeneficiaryRequest's
    # only two fields this conversational flow currently supports end-to-end
    # (cURL reference 14.20) -- see the beneficiary_add confirmation-question
    # builder below for the OTHER_BANK/ACCOUNT_NUMBER default this flow
    # assumes (its one supported serviceType today).
    ("beneficiary_management", "beneficiary_add"): ("nickname", "accountNumber"),
    # T-61: raise a dispute (category "service_requests", service "raise_dispute" --
    # distinct from the existing read-only "disputes" list service; shares the same
    # real endpoint contract, POST service-request/v1/disputes, per cURL reference
    # 2.2/3.3/8.2 for ATM_SUPPORT/CARD_ISSUE/FAILED_TRANSFER respectively). Like T-56's
    # transfer branch, this never calls the real adapter -- see the dedicated
    # no-adapter-call branch in _chat_stream below -- so the fields gathered here are
    # only the ones a customer can plausibly supply conversationally: accountNumber and
    # transactionReferenceNo (real, required field names per RegisterDisputeRequest) plus
    # remarks (real field name, used here as the free-text reason, same role T-57's
    # "reason" played for card freeze). The real contract's other two required fields,
    # `category` (a fixed enum the doc itself says has no good ATM-specific fit -- "that
    # choice is an ASSUMPTION") and `otpType`/`verificationToken` (step-up/OTP artifacts),
    # are deliberately excluded from conversational gather, same reasoning T-56 used to
    # exclude PIN/OTP from the transfer gather -- those only ever get resolved in the app,
    # never here, since this flow never submits the dispute itself.
    ("service_requests", "raise_dispute"): ("accountNumber", "transactionReferenceNo", "remarks"),
    # T-75 (user-approved 2026-10-04): complaint/nickname/address act after an explicit
    # yes; email/mobile after a verified OTP. update_address needs at least ONE address
    # field (see _missing_payload_fields); report_lost_card and update_profile_image are
    # redirect-only and need nothing gathered beyond the card.
    ("support", "submit_complaint"): ("description",),
    ("profile_update", "update_nickname"): ("nickName",),
    ("profile_update", "update_email"): ("newEmail",),
    ("profile_update", "update_mobile"): ("newPhone",),
}

_ADDRESS_KEY = ("profile_update", "update_address")
_BENEFICIARY_ADD_KEY = ("beneficiary_management", "beneficiary_add")


def _missing_payload_fields(category: str, service: str, payload: dict | None) -> list[str]:
    """Returns the required fields (per _REQUIRED_PAYLOAD_FIELDS) missing or falsy from
    `payload` for this (category, service) pair. Empty list if this pair has no required
    fields, or if all required fields are present. `payload=None` is treated as `{}`."""
    if (category, service) == _ADDRESS_KEY:
        return [] if any((payload or {}).get(f) for f in ADDRESS_FIELDS) else ["newAddress"]
    if (category, service) == _BENEFICIARY_ADD_KEY and (payload or {}).get("serviceType") == "OTHER_BANK":
        # Bank contract (BeneficiaryServiceImpl.validateByServiceType): an other-bank
        # beneficiary needs the bank, branch and routing number too.
        required = ("nickname", "accountNumber", "bankName", "branchName", "routingNumber")
        return [f for f in required if not (payload or {}).get(f)]
    required = _REQUIRED_PAYLOAD_FIELDS.get((category, service))
    if not required:
        return []
    # What the bank already knows is never asked of the customer, even if the lookup failed:
    # the app screen lets them pick the account and transaction.
    required = tuple(f for f in required if f not in _BANK_KNOWN_FIELDS.get((category, service), ()))
    payload = payload or {}
    return [field for field in required if not payload.get(field)]


# T-56: transfer/bank_transfer and transfer/wallet_transfer subservice ->
# customer-facing display name maps, shared by both the clarification-question
# builders below and the no-adapter confirmation summary built once the
# payload is complete (see _transfer_summary_reply in _chat_stream).


# Generated (LLM-worded) missing-field clarifications. User requirement: clarifying
# questions must not be identical fixed boilerplate every time. Only the *wording* is
# generated -- _missing_payload_fields still decides deterministically which fields are
# missing, and that list is handed to the model as a fixed instruction. Security
# confirmations (freeze OTP prompt, beneficiary-add yes/no) are deliberately NOT
# generated -- they stay fixed text.


# Plain-English descriptions of each gatherable field, as it should be *asked for*.
_CLARIFICATION_FIELD_DESCRIPTIONS: dict[str, str] = {
    "transactionType": "which kind of transfer the fee is for (for example a bank transfer, bKash, Nagad, Rocket)",
    "amount": "how much money (in taka)",
    "accountNumber": "the account number",
    "walletNumber": "the mobile wallet number to send to",
    "reason": "the reason for freezing the card",
    "nickname": "a name to save the beneficiary under",
    "transactionReferenceNo": "the transaction reference number",
    "remarks": "what went wrong with the transaction (the reason for the dispute)",
    "description": "what the complaint is about",
    "nickName": "the new nickname they want",
    "newAddress": "which address to change (present or permanent) and the full new address",
    "newEmail": "the new email address",
    "newPhone": "the new mobile number (11 digits, starting with 01)",
    "bankName": "the name of the beneficiary's bank",
    "branchName": "the bank branch",
    "routingNumber": "the branch routing number",
}


def _known_field_phrases(payload: dict | None) -> list[str]:
    """Already-known payload values, rendered for the prompt via an explicit
    whitelist -- never the raw payload (so pin/password/otp/verificationToken/cardId
    can never reach the model). Account/wallet numbers are masked to their last 4."""
    payload = payload or {}
    phrases: list[str] = []
    transaction_type = payload.get("transactionType")
    if transaction_type:
        phrases.append(f"transfer type: {str(transaction_type).replace('_', ' ')}")
    amount = payload.get("amount")
    if amount:
        phrases.append(f"amount: Tk {amount}")
    for field, label in (("accountNumber", "account number"), ("walletNumber", "wallet number")):
        value = payload.get(field)
        if value:
            last4 = re.sub(r"\D", "", str(value))[-4:] or str(value)[-4:]
            phrases.append(f"{label} ending {last4}")
    card_last4 = payload.get("cardLast4")
    if card_last4:
        phrases.append(f"card ending {str(card_last4)[-4:]}")
    for field, label in (
        ("nickname", "beneficiary name"),
        ("transactionSummary", "transaction"),
        ("reason", "reason"),
        ("remarks", "dispute reason"),
    ):
        value = payload.get(field)
        if value:
            phrases.append(f"{label}: {_DIGIT_RUN_RE.sub(_mask_digit_run, str(value))[:200]}")
    return phrases


# Template/placeholder artifacts ("XXXX", "[amount]", "<number>", "{x}") -- seen live.


# Numbers, taka amounts and card/account endings a reworded reply must keep verbatim.
_PHRASE_FACT_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _number_keeps_its_label(number: str, facts: str, text: str) -> bool:
    """Every place `number` follows a word in the facts ("ending 0293", "Tk 500.00"),
    the rewording must keep that word right before it at least once."""
    labels = set(re.findall(r"(\w+)\W{1,2}" + re.escape(number), facts))
    return all(re.search(re.escape(label) + r"\W{1,2}" + re.escape(number), text, re.IGNORECASE) for label in labels)


def _ask_say(category: str, service: str, subservice: str | None, payload: dict | None,
             missing_fields: list[str]) -> tuple:
    """Facts for asking the missing details of a known service (T-77): what the
    customer wants (the service's own description), what's missing, what's already
    known, and real options from the live taxonomy where the field has them."""
    described = SERVICE_DESCRIPTIONS.get((category, service))
    options = None
    if "transactionType" in missing_fields:
        options = [_subservice_name("transfer", svc, sub) or sub
                   for svc in ("bank_transfer", "wallet_transfer")
                   for sub in (_subservice_ids("transfer", svc))]
    return _say(
        "ask",
        request=(described[0] if described else _service_name(category, service)),
        transfer_type=_subservice_name(category, service, subservice) if subservice else None,
        missing=[_CLARIFICATION_FIELD_DESCRIPTIONS.get(f, f.replace("_", " ")) for f in missing_fields],
        already_known=_known_field_phrases(payload) or None,
        options=options,
    )


async def _read_pending_reply(question: str | None, message: str, payload: dict | None) -> str:
    """How the customer answered a pending yes/no or verification step (T-77: the
    model reads it -- no phrase lists): "confirm", "decline", "unsure" or "other" (a
    different request). The app's buttons send payload.confirm (true/false), decided
    without the model. Text shaped like a typed code/password is never shown to a
    model: "secret" (stays in the secure-form step). A "confirm" only counts when the
    model quotes the customer's own words for it (grounded); anything else that isn't
    clearly a decline or a new request is "unsure", so nothing runs on a guess."""
    if isinstance(payload, dict) and isinstance(payload.get("confirm"), bool):
        return "confirm" if payload["confirm"] else "decline"
    if _has_secret_fields(payload) or _looks_like_typed_secret(message):
        return "secret"
    prompt = (
        f'A bank assistant asked the customer: "{question or "a yes/no question"}"\n'
        f'The customer replied: "{message}"\n\n'
        "Did the customer: confirm (agree to go ahead), decline (say no / cancel / stop), "
        "unsure (hesitant, unclear, or asking about the same thing), or other (a different "
        "request or question)? Copy the customer's words that show it. "
        'Respond only with JSON: {"answer": "confirm|decline|unsure|other", "quote": "<words>"}'
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False,
                    "format": "json", "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0},
                },
            )
            resp.raise_for_status()
            parsed = json.loads(resp.json().get("response") or "{}")
    except Exception:
        return "unsure"
    answer = str(parsed.get("answer") or "").strip().lower() if isinstance(parsed, dict) else ""
    if answer == "confirm" and not _grounded(_quoted(parsed.get("quote")), message):
        return "unsure"
    return answer if answer in ("confirm", "decline", "unsure", "other") else "unsure"


# Keyed by (category, service) -- the exact pair driving the generic BankingService




_ADDRESS_LABELS = {
    "presentAddress": "present address", "permanentAddress": "permanent address",
    "district": "district", "division": "division",
}


# Changes that run after an explicit yes (card freeze uses the OTP step instead).
_CONFIRM_CHANGE_KEYS = frozenset({
    ("beneficiary_management", "beneficiary_add"),
    ("support", "submit_complaint"),
    ("profile_update", "update_nickname"),
    ("profile_update", "update_address"),
})


# T-57: OTP + PIN/password step-up for card freeze. Flow, all deterministic (no LLM
# ever sees any of this): card + reason gathered -> send_otp(phone from the
# customer's own verified JWT identity, NEVER from request input) -> OTP_REQUIRED
# pending state -> the customer's next request carries `payload.otp` + exactly one of
# `payload.pin`/`payload.password` (structured fields only -- never parsed from
# message text) -> verify_otp -> FreezeCardAdapter (reasonCode=OTHER). pin/password/
# otp are never logged, never persisted in session state, never echoed in a result.
_FREEZE_KEY = ("card_services", "frezz_unfrezz")
_OTP_PENDING_TYPE = "OTP_REQUIRED"


def _say(kind: str, must: dict | None = None, **facts) -> tuple:
    """What a message must convey: a composer kind, structured facts (never sentences),
    and exact values that must appear attached to their labels (T-77)."""
    return (kind, {k.replace("_", " "): v for k, v in facts.items() if v not in (None, "")}, must or {})


class _TurnOutcome:
    """One fully-decided turn outcome; `say` is what the message must convey. The
    caller composes the words, emits token + result, logs, audits and records it."""

    def __init__(
        self,
        result_type: str,
        say: tuple,
        category: str | None,
        service: str | None,
        subservice: str | None,
        *,
        result_payload: dict | None = None,
        routing: dict | None = None,
        stored: dict | None = None,
    ):
        self.result_type = result_type
        self.say = say
        self.token = ""  # set by _emit_outcome once composed
        self.category = category
        self.service = service
        self.subservice = subservice
        self.result_payload = result_payload
        self.routing = routing
        # Extra keys persisted on the session turn's classification (payload,
        # question, server-side-only verificationToken) -- never secrets.
        self.stored = stored or {}

    def classification(self) -> dict:
        return {
            "type": self.result_type,
            "category": self.category,
            "service": self.service,
            "subservice": self.subservice,
            **self.stored,
        }


def _clean_secret(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _freeze_otp_pending(
    category: str,
    service: str,
    subservice: str | None,
    payload: dict | None,
    say: tuple,
    *,
    status: str,
    otp_required: bool = True,
    verification_token: str | None = None,
    attempts_remaining: int | None = None,
) -> _TurnOutcome:
    """OTP_REQUIRED outcome (pending state). `verification_token` (only after a
    verified OTP followed by a wrong PIN/password, when the bank says the token is
    still valid) is kept server-side in session state only -- never sent to the
    client."""
    public_payload = _strip_secrets(dict(payload or {}))
    public_payload.pop("verificationToken", None)
    result_payload = {
        **public_payload,
        "otpRequired": otp_required,
        "credentialOptions": ["pin", "password"],
        "verificationStatus": status,
    }
    if attempts_remaining is not None:
        result_payload["attemptsRemaining"] = attempts_remaining
    stored = {"payload": public_payload, "question": ""}  # filled with the composed text
    if verification_token:
        stored["verificationToken"] = verification_token
    return _TurnOutcome(
        _OTP_PENDING_TYPE, say, category, service, subservice,
        result_payload=result_payload, stored=stored,
    )


def _freeze_not_executed(
    category: str, service: str, subservice: str | None, say: tuple, status: str
) -> _TurnOutcome:
    """Terminal, nothing-was-frozen outcome (flow ends; the next message is a fresh
    request)."""
    return _TurnOutcome(
        "BANKING_SERVICE", say, category, service, subservice,
        result_payload={"executed": False, "verificationStatus": status},
    )


def _service_name(category: str | None, service: str | None) -> str:
    """The service's own name from the live taxonomy (data), for the composer."""
    for cat in get_taxonomy().get("categories", []):
        if cat.get("id") == category:
            for svc in cat.get("services", []):
                if svc.get("id") == service:
                    return svc.get("name") or str(service)
    return str(service or "that service").replace("_", " ")


def _service_unavailable(category, service, subservice) -> _TurnOutcome:
    changes = ((category, service) in _CONFIRM_CHANGE_KEYS or (category, service) == _FREEZE_KEY
               or category in ("profile_update", "beneficiary_management", "support"))
    return _TurnOutcome(
        "SERVICE_UNAVAILABLE",
        _say("unavailable", service=_service_name(category, service),
             request_kind="a change to their account" if changes else "a lookup, nothing was being changed"),
        category, service, subservice,
    )


def _login_needed(category, service, subservice) -> _TurnOutcome:
    return _TurnOutcome("AUTH_REQUIRED", _say("login_needed", request=_service_name(category, service)),
                        category, service, subservice)


def _card_must(payload: dict | None) -> dict:
    last4 = (payload or {}).get("cardLast4")
    return {"card ending": last4} if last4 else {}


_FREEZE_FACTS = {
    "action": "freeze (temporarily block) the card",
    "code_sent_to": "their registered phone number",
    "enter_in_the_app_secure_form": ["the one-time code", "either the card PIN or the login password (only one of them)"],
    "what_freezing_does": "stops all payments and withdrawals with the card; it can be unfrozen later in the app",
    "to_stop": "reply cancel",
}


def _freeze_verify_say(payload: dict | None, problem: str | None = None) -> tuple:
    return _say("verify", _card_must(payload), **_FREEZE_FACTS,
                reason_given=(payload or {}).get("reason"), problem=problem)


async def _send_freeze_otp(
    customer_identity,
    category: str,
    service: str,
    subservice: str | None,
    payload: dict | None,
    lead: str | None = None,
) -> _TurnOutcome:
    """Sends (or re-sends) the OTP to the customer's OWN phone -- always
    customer_identity.customer_id (the phone from the bank's own JWT introspection,
    see app/banking/identity.py), never a request/payload value -- and returns the
    OTP_REQUIRED prompt. Fixed text (security step, never LLM-generated)."""
    try:
        await send_otp(customer_identity.customer_id)
    except AdapterValidationError as exc:
        if exc.reason == "SEND_THROTTLED":
            return _freeze_not_executed(
                category, service, subservice,
                _say("not_done", _card_must(payload), what="freezing the card",
                     why="too many verification codes were requested recently",
                     next_step="wait a few minutes, then ask again", card_status="not frozen"),
                "SEND_THROTTLED",
            )
        return _service_unavailable(category, service, subservice)
    except AdapterUnavailableError:
        return _service_unavailable(category, service, subservice)

    return _freeze_otp_pending(
        category, service, subservice, payload, _freeze_verify_say(payload, lead),
        status="OTP_RESENT" if lead else "OTP_SENT",
    )


async def _handle_freeze_otp_reply(
    customer_identity, jwt: str | None, pending: dict, message: str, submitted: dict | None,
    declined: bool = False,
) -> _TurnOutcome:
    """Resolves the customer's reply to a pending OTP_REQUIRED freeze step. Reads
    otp/pin/password ONLY from the structured `submitted` payload -- `message` is only
    read for a cancel/new request (secret-shaped text never reaches a
    model), never parsed for secrets."""
    category = pending.get("category")
    service = pending.get("service")
    subservice = pending.get("subservice")
    stored_payload = dict(pending.get("payload") or {})
    stored_token = pending.get("verificationToken")
    submitted = submitted if isinstance(submitted, dict) else {}
    otp = _clean_secret(submitted.get("otp"))
    pin = _clean_secret(submitted.get("pin"))
    password = _clean_secret(submitted.get("password"))

    def reask(problem: str, status: str, **kw) -> _TurnOutcome:
        return _freeze_otp_pending(
            category, service, subservice, stored_payload,
            _freeze_verify_say(stored_payload, problem), status=status,
            otp_required=kw.pop("otp_required", not stored_token),
            verification_token=kw.pop("verification_token", stored_token),
            **kw,
        )

    if not (otp or pin or password) and declined:
        return _TurnOutcome(
            "BANKING_SERVICE", _say("declined", _card_must(stored_payload), what="freezing the card"),
            category, service, subservice,
            result_payload={"executed": False, "cancelled": True},
        )

    if pin and password:
        return reask("both a PIN and a password were entered; only one of them is needed",
                     "CREDENTIALS_INVALID_COMBINATION")
    if not otp and not stored_token:
        return reask("the code hasn't been entered yet; it goes in the app's secure form, "
                     "never in the chat", "CREDENTIALS_MISSING")
    if not (pin or password):
        return reask("the card PIN or the login password is still needed with the code",
                     "CREDENTIALS_MISSING")

    verification_token = stored_token
    if otp:
        try:
            verification_token = await verify_otp(customer_identity.customer_id, otp)
        except AdapterValidationError as exc:
            if exc.reason == "OTP_INCORRECT":
                remaining = exc.attempts_remaining
                attempts = f"; attempts left: {remaining}" if remaining is not None else ""
                return reask(
                    f"the code entered was not correct{attempts}; re-enter the same code "
                    "(no new code is needed) with the PIN or password",
                    "OTP_INCORRECT", otp_required=True, verification_token=None,
                    attempts_remaining=remaining,
                )
            if exc.reason == "OTP_EXPIRED":
                return await _send_freeze_otp(
                    customer_identity, category, service, subservice, stored_payload,
                    lead="the earlier code expired, so a new one was sent",
                )
            if exc.reason == "OTP_BLOCKED":
                return _freeze_not_executed(
                    category, service, subservice,
                    _say("not_done", _card_must(stored_payload), what="freezing the card",
                         why="too many incorrect codes were entered, so verification is blocked for a while",
                         next_step="wait about 5 minutes, then ask again", card_status="not frozen"),
                    "OTP_BLOCKED",
                )
            return _service_unavailable(category, service, subservice)
        except AdapterUnavailableError:
            return _service_unavailable(category, service, subservice)

    # The real call payload -- the only place pin/password/verificationToken are
    # combined. Never logged, never stored.
    freeze_payload = {**_strip_secrets(stored_payload), "verificationToken": verification_token}
    if pin:
        freeze_payload["pin"] = pin
    else:
        freeze_payload["password"] = password

    try:
        adapter_result = await fulfill_banking_service(
            customer_identity, jwt, category, service, subservice, freeze_payload
        )
    except AdapterValidationError as exc:
        if exc.reason == "INVALID_CREDENTIALS":
            return reask(
                "the PIN or password was not correct; the code is still valid, so only the "
                "PIN or password needs re-entering", "INVALID_CREDENTIALS", otp_required=False,
                verification_token=verification_token,
            )
        if exc.reason == "INVALID_VERIFICATION_TOKEN":
            return await _send_freeze_otp(
                customer_identity, category, service, subservice, stored_payload,
                lead="the verification expired, so a new code was sent",
            )
        if exc.reason == "PIN_OR_PASSWORD_REQUIRED":
            return reask(
                "exactly one of the card PIN or the login password is needed",
                "CREDENTIALS_INVALID_COMBINATION",
                verification_token=verification_token,
            )
        return _service_unavailable(category, service, subservice)
    except AdapterAuthError:
        return _login_needed(category, service, subservice)
    except AdapterUnavailableError:
        return _service_unavailable(category, service, subservice)

    # Only what the frontend needs to show the outcome. The bank answers the freeze
    # with the full card record (full card number, CIF, phone, linked account
    # number) -- none of that is passed on (seen live 2026-10-03).
    card = adapter_result.data.get("data") if isinstance(adapter_result.data, dict) else None
    card = card if isinstance(card, dict) else {}
    executed_data = {
        "executed": True,
        "cardId": stored_payload.get("cardId"),
        "cardLast4": stored_payload.get("cardLast4"),
        "status": card.get("status"),
    }
    return _TurnOutcome(
        "BANKING_SERVICE",
        _say("done", _card_must(stored_payload), what="the card was frozen",
             can_it_be_undone="yes, it can be unfrozen in the app"),
        category, service, subservice,
        result_payload=executed_data,
        routing={"category": category, "service": service, "subservice": subservice, "action": "redirect"},
    )


# --- T-75: customer-requested changes (user-approved 2026-10-04) -------------------
_REPORT_LOST_KEY = ("card_requests", "report_lost_card")
_PHOTO_KEY = ("profile_update", "update_profile_image")
_EMAIL_KEY = ("profile_update", "update_email")
_MOBILE_KEY = ("profile_update", "update_mobile")
_CONTACT_KEYS = (_EMAIL_KEY, _MOBILE_KEY)
_CARD_PICK_KEYS = (_FREEZE_KEY, _REPORT_LOST_KEY)
_REASON_CODES = ("LOST", "STOLEN", "DAMAGED", "EXPIRED", "OTHER")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_BD_MOBILE_RE = re.compile(r"01[3-9]\d{8}")


def _bd_mobile(value: object) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("880"):
        digits = digits[2:]
    return digits if _BD_MOBILE_RE.fullmatch(digits) else None


def _normalize_change_request(result):
    """Format checks on what the classifier extracted for T-75 services. A value
    that isn't valid is dropped, so the customer is asked for it again instead of
    the bank rejecting it (or a wrong value being saved)."""
    if not isinstance(result, BankingService):
        return result
    key = (result.category, result.service)
    payload = dict(result.payload or {})
    if key == ("support", "submit_complaint"):
        category = str(payload.get("category") or "").strip().upper()
        payload["category"] = category if category in COMPLAINT_CATEGORIES else "OTHER"
        if payload.get("description"):
            payload["description"] = str(payload["description"]).strip()[:2000]
    elif key == ("profile_update", "update_nickname"):
        nickname = str(payload.get("nickName") or "").strip().strip('"')
        payload["nickName"] = nickname if 0 < len(nickname) <= 50 else None
    elif key == _EMAIL_KEY:
        email = str(payload.get("newEmail") or "").strip().lower()
        payload["newEmail"] = email if _EMAIL_RE.fullmatch(email) else None
    elif key == _MOBILE_KEY:
        payload["newPhone"] = _bd_mobile(payload.get("newPhone"))
    elif key == _REPORT_LOST_KEY:
        code = str(payload.get("reasonCode") or "").strip().upper()
        payload["reasonCode"] = code if code in _REASON_CODES else None
    else:
        return result
    payload = {k: v for k, v in payload.items() if v not in (None, "")}
    return BankingService(result.category, result.service, result.subservice, payload or None)


# Changes and card actions are never "followed up" by reusing old details.
_NO_FOLLOW_UP_KEYS = frozenset({
    _FREEZE_KEY, _REPORT_LOST_KEY, _PHOTO_KEY, _EMAIL_KEY, _MOBILE_KEY,
    ("support", "submit_complaint"), ("profile_update", "update_nickname"), _ADDRESS_KEY,
    ("beneficiary_management", "beneficiary_add"),
})
# Words inside <...> placeholders of the routing prompt's patterns. A payload value
# equal to one was copied from the prompt, not said by the customer (live: a
# nickname became "new value").


def _transfer_target(transaction_type: str | None) -> tuple[str, str] | None:
    """(service, subservice) of the transfer a fee quote's type belongs to."""
    if transaction_type in _wallet_ids():
        return "wallet_transfer", transaction_type
    if transaction_type in _subservice_ids("transfer", "bank_transfer"):
        return "bank_transfer", transaction_type
    return None


def _service_routing(category, service, subservice, request_payload: dict | None) -> dict:
    """routing for a successful service result. A fee quote also offers to start the
    matching transfer ("start_transfer", pre-filled) -- a customer asking a fee is often
    about to send, and this way a fee question never blocks a transfer."""
    routing = {"category": category, "service": service, "subservice": subservice, "action": "redirect"}
    if (category, service) == ("fees", "fee_quote"):
        target = _transfer_target((request_payload or {}).get("transactionType"))
        if target:
            routing.update(
                action="start_transfer",
                transfer={"category": "transfer", "service": target[0], "subservice": target[1],
                          "prefill": {"amount": (request_payload or {}).get("amount")}},
            )
    return routing


def _clean_extracted_fields(result):
    """Drop extracted values that can't be real: copied prompt placeholders, an
    "account number" with no digits ("Nagad", "e"), a wallet number that isn't a
    mobile number ("3000"). Dropped -> the customer is asked for it."""
    if not isinstance(result, BankingService) or not result.payload:
        return result
    payload = {}
    for key, value in result.payload.items():
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("<") and text.endswith(">"):  # a prompt placeholder, not a value
                continue
            if key == "accountNumber" and len(re.sub(r"\D", "", text)) < 6:
                continue
            # A reference is an id (live: the model put "bKash transaction on 29 September"
            # here, which skipped the real transaction lookup).
            if key == "transactionReferenceNo" and re.search(r"\s", text):
                continue
            if key == "walletNumber":
                value = _bd_mobile(text)
                if not value:
                    continue
        payload[key] = value
    if payload == result.payload:
        return result
    return BankingService(result.category, result.service, result.subservice, payload or None)


def _report_lost_card_outcome(category, service, subservice, payload: dict | None) -> _TurnOutcome:
    """Lost/stolen card: never calls the bank (user decision 2026-10-04). The customer
    reports it -- and the card is destroyed/replaced -- themselves on the app's own
    screen; this explains the consequence (caution) and hands over the pre-filled
    request."""
    payload = payload or {}
    say = _say(
        "caution", _card_must(payload),
        reason=(payload.get("reasonCode") or "").lower() or None,
        reporting_means="the card is closed for good and a replacement card is issued",
        can_it_be_undone="no",
        where_it_happens="the report screen in the app, which opens next; the customer confirms it there",
        gentler_option="freeze the card for now instead; freezing can be undone",
    )
    return _TurnOutcome(
        "BANKING_SERVICE", say, category, service, subservice,
        result_payload={
            "cardId": payload.get("cardId"), "cardLast4": payload.get("cardLast4"),
            "reasonCode": payload.get("reasonCode"), "executed": False,
        },
        routing={"category": category, "service": service, "subservice": subservice,
                 "action": "report_lost_card"},
    )


def _profile_photo_outcome(category, service, subservice) -> _TurnOutcome:
    return _TurnOutcome(
        "BANKING_SERVICE",
        _say("redirect", screen="the profile photo screen in the app",
             why="photos are uploaded there, not in the chat"),
        category, service, subservice,
        result_payload={"executed": False},
        routing={"category": category, "service": service, "subservice": subservice,
                 "action": "update_profile_image"},
    )


_UI_AMOUNT_FIELDS = ("amount", "requestedLimit", "newLimit")


def _ui_prefill(action: "ui_actions.UiAction", payload: dict | None, message: str) -> dict:
    """The optional fields the screen can start with: only values the customer actually wrote
    (an amount is a number they wrote times a power of ten; digits appear in their message; free
    text is in their own words). Anything else the classifier guessed is dropped."""
    out: dict = {}
    wrote_digits = re.sub(r"\D", "", message or "")
    for field, _meaning in action.prefill:
        value = (payload or {}).get(field)
        if value in (None, "", [], {}):
            continue
        text = str(value).strip()
        if field in _UI_AMOUNT_FIELDS:
            if not _amount_supported(value, message):
                continue
        elif field.endswith("Last4") or field == "recipientMobile":
            digits = re.sub(r"\D", "", text)
            digits = digits[-4:] if field.endswith("Last4") else digits
            if not digits or digits not in wrote_digits:
                continue
            value = digits
        elif not _grounded(text, message):
            continue
        out[field] = value
    return out


def _ui_action_outcome(action: "ui_actions.UiAction", payload: dict | None, message: str) -> _TurnOutcome:
    """A request the chat does not carry out (T-79): no bank call. The app gets the screen to open
    (with whatever the customer already said), or the information to show; the reply is composed."""
    prefill = _ui_prefill(action, payload, message)
    ui = {"kind": action.kind, "title": action.name, "screen": action.screen, "route": action.route,
          "prefill": prefill or None, "needs": action.needs}
    if action.kind == "screen":
        say = _say("redirect", screen=f"the {action.name} screen in the app, which opens next",
                   what_they_will_do_there=action.needs, already_filled_in=prefill or None,
                   done_in_chat="no; they finish it in the app")
    elif action.kind == "unavailable":
        say = _say("not_done", what=action.name, why=action.needs, changed="nothing")
    else:
        say = _say("not_in_chat", request=action.name, what_to_know=action.needs,
                   where="inside the app")
    return _TurnOutcome(
        "APP_ACTION", say, ui_actions.CATEGORY, action.id, None,
        result_payload={"ui": ui, "executed": False},
        routing={"category": ui_actions.CATEGORY, "service": action.id, "subservice": None,
                 "action": action.id},
    )


def _contact_otp_phone(customer_identity, key: tuple[str, str], payload: dict | None) -> str | None:
    """Where the code goes: always the customer's CURRENT registered phone (from the
    verified JWT, never request input). The bank binds the verification token to the
    current phone for both email and mobile changes (UserAuthServiceImpl.updateMobile/
    updateEmail check otp phone == user.getPhone()); the bank's own app does the same."""
    return customer_identity.customer_id


def _contact_change(key: tuple[str, str], payload: dict | None) -> tuple[str, dict]:
    """(what is being changed, exact new value) for the composer."""
    payload = payload or {}
    if key == _EMAIL_KEY:
        return "the email address on their profile", {"new email": payload.get("newEmail")}
    return "the mobile number registered with the bank", {"new mobile number": payload.get("newPhone")}


def _contact_verify_say(key, payload, problem: str | None = None) -> tuple:
    what, must = _contact_change(key, payload)
    return _say("verify", must, action=f"change {what}", code_sent_to="their current registered phone number",
                enter_in_the_app_secure_form="the one-time code", to_stop="reply cancel", problem=problem)


def _contact_otp_pending(category, service, payload, say, status, attempts=None) -> _TurnOutcome:
    public = {k: v for k, v in _strip_secrets(dict(payload or {})).items() if k in ("newEmail", "newPhone")}
    result_payload = {**public, "otpRequired": True, "credentialOptions": [], "verificationStatus": status}
    if attempts is not None:
        result_payload["attemptsRemaining"] = attempts
    return _TurnOutcome(
        _OTP_PENDING_TYPE, say, category, service, None,
        result_payload=result_payload, stored={"payload": public, "question": ""},
    )


async def _send_contact_otp(customer_identity, category, service, payload, lead: str | None = None) -> _TurnOutcome:
    key = (category, service)
    phone = _contact_otp_phone(customer_identity, key, payload)
    if not phone:
        return _service_unavailable(category, service, None)
    try:
        await send_otp(phone)
    except AdapterValidationError as exc:
        if exc.reason == "SEND_THROTTLED":
            what, must = _contact_change(key, payload)
            return _TurnOutcome(
                "BANKING_SERVICE",
                _say("not_done", must, what=f"changing {what}",
                     why="too many verification codes were requested recently",
                     next_step="wait a few minutes, then ask again"),
                category, service, None,
                result_payload={"executed": False, "verificationStatus": "SEND_THROTTLED"},
            )
        if exc.reason == "INVALID_PHONE":
            return _TurnOutcome(
                "CLARIFICATION_REQUIRED",
                _say("ask", problem="the new mobile number given isn't a valid Bangladeshi mobile number",
                     missing=["the new mobile number"], format="11 digits starting with 01"),
                None, None, None,
            )
        return _service_unavailable(category, service, None)
    except AdapterUnavailableError:
        return _service_unavailable(category, service, None)
    return _contact_otp_pending(category, service, payload, _contact_verify_say(key, payload, lead),
                                "OTP_RESENT" if lead else "OTP_SENT")


async def _handle_contact_otp_reply(
    customer_identity, jwt: str | None, pending: dict, message: str, submitted: dict | None,
    declined: bool = False,
) -> _TurnOutcome:
    """Pending email/mobile change: the code comes ONLY from the structured form
    payload (`otp`), never from chat text; nothing here is logged or sent to an LLM."""
    category, service = pending.get("category"), pending.get("service")
    key = (category, service)
    stored = dict(pending.get("payload") or {})
    otp = _clean_secret((submitted if isinstance(submitted, dict) else {}).get("otp"))

    if not otp and declined:
        what, must = _contact_change(key, stored)
        return _TurnOutcome(
            "BANKING_SERVICE", _say("declined", must, what=f"changing {what}"), category, service, None,
            result_payload={"executed": False, "cancelled": True},
        )
    if not otp:
        return _contact_otp_pending(
            category, service, stored,
            _contact_verify_say(key, stored, "the code hasn't been entered yet; it goes in the app's "
                                             "secure form, never in the chat"),
            "CREDENTIALS_MISSING",
        )
    phone = _contact_otp_phone(customer_identity, key, stored)
    try:
        verification_token = await verify_otp(phone, otp)
    except AdapterValidationError as exc:
        if exc.reason == "OTP_INCORRECT":
            remaining = exc.attempts_remaining
            left = f"; attempts left: {remaining}" if remaining is not None else ""
            return _contact_otp_pending(
                category, service, stored,
                _contact_verify_say(key, stored, f"the code entered was not correct{left}; re-enter the same code"),
                "OTP_INCORRECT", remaining,
            )
        if exc.reason == "OTP_EXPIRED":
            return await _send_contact_otp(customer_identity, category, service, stored,
                                           lead="the earlier code expired, so a new one was sent")
        return _service_unavailable(category, service, None)
    except AdapterUnavailableError:
        return _service_unavailable(category, service, None)

    try:
        await fulfill_banking_service(
            customer_identity, jwt, category, service, None,
            {**stored, "verificationToken": verification_token},
        )
    except AdapterAuthError:
        return _login_needed(category, service, None)
    except AdapterRejectedError as exc:
        what, must = _contact_change(key, stored)
        return _TurnOutcome(
            "BANKING_SERVICE",
            _say("refused_by_bank", must, request=f"change {what}", bank_message=exc.bank_message),
            category, service, None,
            result_payload={"executed": False, "bankMessage": exc.bank_message},
        )
    except AdapterUnavailableError:
        what, must = _contact_change(key, stored)
        return _TurnOutcome(
            "SERVICE_UNAVAILABLE",
            _say("unavailable", must, request=f"change {what}", also_possible="change it in the app"),
            category, service, None,
        )
    what, must = _contact_change(key, stored)
    return _TurnOutcome(
        "BANKING_SERVICE",
        _say("done", must, what=f"{what} was changed",
             signed_out="yes, for security; they need to log in again" if key == _MOBILE_KEY else None),
        category, service, None,
        result_payload={"executed": True, **{k: v for k, v in stored.items() if k in ("newEmail", "newPhone")}},
        routing={"category": category, "service": service, "subservice": None, "action": "redirect"},
    )


_WRITTEN_NUMBER_RE = re.compile(r"\d+(?:,\d{2,3})*(?:\.\d+)?")


def _amount_supported(amount, text: str) -> bool:
    """The model's amount is a number the customer wrote times a power of ten
    ("1.5 lakh" -> 150000, "50k" -> 50000, "75,000" -> 75000). Generic arithmetic,
    no unit-word list in code (T-77): the prompts (AMOUNT_GUIDANCE) teach the model the unit words. Catches an invented or mis-scaled amount, NOT a dropped
    unit ("50k" -> 50 passes: 10^0 is a legitimate "50 taka"); the amount is always
    echoed back in the confirmation, so the customer sees it before anything proceeds."""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    for written in _WRITTEN_NUMBER_RE.findall(text or ""):
        base = float(written.replace(",", ""))
        if base <= 0:
            continue
        ratio = value / base
        if any(abs(ratio - 10 ** k) < 1e-6 * 10 ** k for k in range(0, 9)):
            return True
    return False


def _check_amount(result, message: str):
    """Drop an amount the customer didn't write (so they're asked), keep the rest."""
    if not (isinstance(result, BankingService) and result.payload and "amount" in result.payload):
        return result
    if _amount_supported(result.payload["amount"], message):
        return result
    payload = {k: v for k, v in result.payload.items() if k != "amount"}
    return BankingService(result.category, result.service, result.subservice, payload or None)


def _wallet_ids() -> list[str]:
    """Wallet providers as the live taxonomy lists them (transfer/wallet_transfer)."""
    return _subservice_ids("transfer", "wallet_transfer")


def _transfer_type_options() -> str:
    """Valid transfer-type ids with the taxonomy's own names, for the model."""
    names = []
    for kind in fee_transaction_types():
        name = (_subservice_name("transfer", "bank_transfer", kind)
                or _subservice_name("transfer", "wallet_transfer", kind) or kind.replace("_", " "))
        names.append(f"{kind} = {name}")
    return "; ".join(names)


async def _llm_fill_pending_fields(recent_turns: list[ChatTurn], message: str) -> BankingService | None:
    """Slot filling (T-76/T-77). When we just asked for missing details of a KNOWN
    service -- or the customer follows up on a request we just answered ("and for
    nagad?", "2 lakh") -- the model fills only that service's fields instead of
    re-classifying a one-word reply from scratch (live: "bkash" after a fee question
    became gifts_received). Values are checked: a transfer type must be a live id, a
    wallet must be one the customer named, an amount must be a number they wrote times
    a power of ten. Nothing filled -> None, so a change of topic goes to classify()."""
    if not recent_turns:
        return None
    last = recent_turns[-1].classification or {}
    key = (last.get("category"), last.get("service"))
    if not all(key):
        return None
    if last.get("type") == "BANKING_SERVICE":
        required = _REQUIRED_PAYLOAD_FIELDS.get(key)
        if not required or key in _NO_FOLLOW_UP_KEYS:
            return None
        last = {**last, "missingFields": list(required), "payload": last.get("request") or {},
                "question": f"(follow-up to their last request: {_service_name(*key)})"}
    elif last.get("type") != "CLARIFICATION_REQUIRED":
        return None
    fields = list(last.get("missingFields") or [])
    if not fields:
        return None
    return await _fill_fields(key, last.get("subservice"), dict(last.get("payload") or {}), fields,
                              str(last.get("question")), message)


# Fields that are free text in the customer's own words: a value must come from what they wrote.
_OWN_WORDS_FIELDS = ("remarks", "reason", "description", "nickname", "nickName")
# Fields the bank already knows (looked up from their own data), so they're never asked of the customer.
_BANK_KNOWN_FIELDS = {("service_requests", "raise_dispute"): ("accountNumber", "transactionReferenceNo")}


async def _fill_known_from_message(result, message: str):
    """The customer often says it all in one message ("my money didn't reach my bKash
    account on 10 Feb"), but the classifier only fills some fields. Before asking for
    a missing required field, let the model look for it in the SAME message -- so the
    bot never asks what they already told it. Returns the result unchanged when nothing
    more is found."""
    if not isinstance(result, BankingService):
        return result
    key = (result.category, result.service)
    required = _REQUIRED_PAYLOAD_FIELDS.get(key)
    if not required or key in _NO_FOLLOW_UP_KEYS:
        return result
    payload = dict(result.payload or {})
    skip = _BANK_KNOWN_FIELDS.get(key, ())
    missing = [f for f in required if not payload.get(f) and f not in skip]
    if not missing:
        return result
    filled = await _fill_fields(key, result.subservice, payload, missing,
                                "(the customer's request; nothing has been asked yet)", message)
    return filled if filled is not None else result


async def _fill_fields(key: tuple, subservice, payload: dict, fields: list[str], question: str,
                       message: str) -> BankingService | None:
    """The model fills only `fields` from `message`; every value is checked (a transfer type is
    a live id, a wallet was named, an amount is a number they wrote times a power of ten, free
    text comes from their own words). Nothing filled -> None."""
    valid_types = fee_transaction_types() if "transactionType" in fields else []
    lines = []
    for field in fields:
        line = f'- "{field}": {_CLARIFICATION_FIELD_DESCRIPTIONS.get(field, field)}'
        if field == "transactionType" and valid_types:
            line += f" — use one of these ids: {_transfer_type_options()}"
        if field == "amount":
            line += f" — {AMOUNT_GUIDANCE}"
        lines.append(line)
    prompt = (
        f"A bank chat assistant asked the customer: \"{question}\"\n"
        "It needs these details:\n" + "\n".join(lines) + "\n\n"
        f"The customer replied: \"{_LONG_DIGITS_RE.sub(_mask_digit_run, message)}\"\n\n"
        "Fill ONLY the details the reply actually gives; leave out anything it doesn't. "
        "If the reply is about something else entirely, return {}. "
        "Respond only with a JSON object of the filled details."
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False,
                    "format": "json", "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0},
                },
            )
            resp.raise_for_status()
            extracted = json.loads(resp.json().get("response") or "{}")
    except Exception:
        extracted = {}
    filled: dict = {}
    if isinstance(extracted, dict):
        wallets = _wallet_ids()
        for field in fields:
            value = extracted.get(field)
            if value in (None, "", [], {}):
                continue
            if field == "amount" and not _amount_supported(value, message):
                continue
            if field == "transactionType":
                value = re.sub(r"[\s-]+", "_", str(value).strip().lower())
                if value not in valid_types:
                    continue
                # a wallet must be one the customer actually named (grounding)
                if value in wallets and not _grounded(
                        _subservice_name("transfer", "wallet_transfer", value) or value, message):
                    continue
            if field in _OWN_WORDS_FIELDS and not _grounded(str(value), message):
                continue
            filled[field] = value
    if not filled:
        return None
    return BankingService(key[0], key[1], subservice, {**payload, **filled})


def _candidate_number(candidate: dict) -> str:
    return str(
        candidate.get("accountNumber") or candidate.get("identifier")
        or candidate.get("cardNumber") or ""
    )


_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")


def _foreign_script(reply: str, message: str) -> bool:
    """Bengali script in a reply to a customer who wrote none (replies are English)."""
    return bool(_BENGALI_RE.search(reply or "")) and not _BENGALI_RE.search(message or "")


def _carry_forward_gathered(result, recent_turns: list[ChatTurn]):
    """The customer answered our missing-field question and the answer routes to the
    SAME service: keep what they told us before (nickname, account number, ...) and
    let the new answer add to or override it. Without this, a 3-step gather lost
    earlier answers whenever the classifier re-read only the latest message."""
    if not (isinstance(result, BankingService) and recent_turns):
        return result
    last = recent_turns[-1].classification or {}
    if last.get("type") not in ("CLARIFICATION_REQUIRED", "BANKING_SERVICE"):
        return result
    if (last.get("category"), last.get("service")) != (result.category, result.service):
        return result
    # A clarification stores what was gathered so far; an answered turn stores the
    # request it answered (a follow-up changes one detail and keeps the rest).
    stored_source = last.get("payload") if last.get("type") == "CLARIFICATION_REQUIRED" else last.get("request")
    stored = {k: v for k, v in (stored_source or {}).items() if v not in (None, "")}
    if not stored:
        return result
    return BankingService(result.category, result.service, result.subservice or last.get("subservice"),
                          {**stored, **(result.payload or {})})


_SELECTION_TYPES = ("ACCOUNT_SELECTION_REQUIRED", "TRANSACTION_SELECTION_REQUIRED")
_DISPUTE_KEY = ("service_requests", "raise_dispute")
_MAX_TRANSACTION_CHOICES = 8


def _transaction_choice(txn: dict) -> dict:
    """A recent transaction as a pickable option -- no account number in it, so a
    typed account number can never be mistaken for a pick."""
    return {k: txn.get(k) for k in ("transactionId", "txnTime", "type", "amount", "transactionType")}


async def _prefill_from_bank(customer_identity, jwt, category, service, subservice,
                             payload: dict | None, context: str) -> tuple[dict, "_TurnOutcome | None"]:
    """Never ask the customer for what the bank already knows. Fills, from their own
    data: a dispute's account (one account -> used; several -> "which one?") and its
    transaction (the model matches their description against recent transactions;
    no clear match -> they pick from the list); an own-account transfer's
    destination (their other account). Returns (payload, outcome-to-send or None)."""
    payload = dict(payload or {})
    key = (category, service)
    own_transfer = key == ("transfer", "bank_transfer") and subservice == "own_account"
    if key != _DISPUTE_KEY and not own_transfer:
        return payload, None

    async def accounts() -> list[dict]:
        result = await fulfill_banking_service(customer_identity, jwt, "account_info", "accounts", None, None)
        data = result.data.get("data") if isinstance(result.data, dict) else None
        rows = data.get("accounts") if isinstance(data, dict) else None
        return [a for a in rows or [] if isinstance(a, dict) and not _is_card_row(a)]

    def pick(kind: str, say: tuple, candidates: list[dict]) -> "_TurnOutcome":
        return _TurnOutcome(
            kind, say, category, service, subservice,
            result_payload={"transactions" if kind.startswith("TRANSACTION") else "accounts": candidates},
            stored={"question": "", "candidates": candidates, "payload": _strip_secrets(payload)},
        )

    try:
        if own_transfer and not payload.get("accountNumber"):
            mine = await accounts()
            if len(mine) < 2:
                return payload, _TurnOutcome(
                    "BANKING_SERVICE",
                    _say("not_done", what="moving money between their own accounts",
                         why="they have only one account with the bank",
                         other_option="sending it to someone else (another account or a mobile wallet)"),
                    category, service, subservice, result_payload={"executed": False},
                )
            return payload, pick("ACCOUNT_SELECTION_REQUIRED",
                                 _say("choose", question_about="which of their accounts should receive the money",
                                      options=[_describe_selection_account(a) for a in mine]), mine)

        if key == _DISPUTE_KEY and not payload.get("accountNumber"):
            mine = await accounts()
            if len(mine) == 1:
                payload["accountNumber"] = mine[0].get("accountNumber")
            elif len(mine) > 1:
                return payload, pick("ACCOUNT_SELECTION_REQUIRED",
                                     _say("choose", question_about="which account the problem transaction was on",
                                          options=[_describe_selection_account(a) for a in mine]), mine)

        if key == _DISPUTE_KEY and payload.get("accountNumber") and not payload.get("transactionReferenceNo"):
            result = await fulfill_banking_service(
                customer_identity, jwt, "polygon_services", "transaction_history", None,
                {"accountNumber": payload["accountNumber"], "size": _MAX_TRANSACTION_CHOICES},
            )
            txns = result.data.get("transactions") if isinstance(result.data, dict) else None
            choices = [_transaction_choice(t) for t in txns or [] if isinstance(t, dict) and t.get("transactionId")]
            if choices:
                described = " ".join(x for x in (context, payload.get("remarks")) if x)
                index = await _llm_pick_candidate(described, choices) if described else None
                if index is not None:
                    payload.update(_selection_payload(choices[index]))
                else:
                    return payload, pick(
                        "TRANSACTION_SELECTION_REQUIRED",
                        _say("choose", question_about="which recent transaction the problem is about",
                             options=[_describe_selection_account(c) for c in choices]),
                        choices,
                    )
    except AdapterAuthError:
        return payload, _login_needed(category, service, subservice)
    except AdapterUnavailableError:
        return payload, None  # can't look it up right now: fall back to asking
    return payload, None


def _normalize_fee_type(result, message: str = ""):
    """fees/fee_quote: transactionType must be EXACTLY one of the bank's live transfer
    ids (the model is given them); anything else is dropped so the customer is asked
    (T-77: no substring/keyword mapping). A wallet must be one the customer named."""
    if not (isinstance(result, BankingService) and (result.category, result.service) == ("fees", "fee_quote")):
        return result
    payload = dict(result.payload or {})
    raw = payload.get("transactionType")
    if not raw:
        return result
    valid = fee_transaction_types()
    if not valid:  # taxonomy not loaded: nothing to check against
        return result
    value = re.sub(r"[\s-]+", "_", str(raw).strip().lower())
    named = value in valid and not (
        value in _wallet_ids() and message
        and not _grounded(_subservice_name("transfer", "wallet_transfer", value) or value, message))
    if named:
        payload["transactionType"] = value
    else:
        payload.pop("transactionType")
    return BankingService(result.category, result.service, result.subservice, payload or None)


def _quoted(value) -> str | None:
    text = value.strip() if isinstance(value, str) else ""
    # The model sometimes repeats the quote ("X X"); keep one copy.
    half = len(text) // 2
    if text and text[:half].strip() == text[half:].strip():
        text = text[:half].strip()
    return text if text and text.lower() not in ("null", "none", "n/a") else None


async def _freeze_request_facts(messages: list[str]) -> tuple[str | None, str | None]:
    """(reason, block_request) as the customer themselves wrote them, each None if
    they didn't. Extraction, not a yes/no judgement: llama3.1:8b answered "false"
    to "did they say why?" even for "my card was stolen", but quotes reliably.
    Any failure returns (None, None)."""
    said = "\n".join(f'- "{_LONG_DIGITS_RE.sub(_mask_digit_run, m)}"' for m in messages)
    prompt = (
        "A bank customer wrote these chat messages (English, Bangla or Banglish):\n"
        f"{said}\n\n"
        "1. reason: the exact words, copied from their messages, that say what happened "
        "to the card (for example that it was lost, stolen or used by someone else). Only "
        "asking to freeze or block is not a reason. null if they didn't say.\n"
        "2. block_request: the exact words, copied from their messages, asking to freeze, "
        "block or lock the card, or reporting it lost/stolen/misused. A card that just "
        "doesn't work, or a request to reset a PIN or unblock, is NOT a block request. "
        "null if none.\n"
        "Saying the card was lost, stolen or misused counts for BOTH fields (copy those "
        "words into each).\n"
        'Respond only with JSON: {"reason": "<text>" or null, "block_request": "<text>" or null}'
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0},
                },
            )
            resp.raise_for_status()
            parsed = json.loads(resp.json().get("response") or "{}")
    except Exception:
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    said_text = " ".join(messages)
    return (
        _grounded(_quoted(parsed.get("reason")), said_text),
        _grounded(_quoted(parsed.get("block_request")), said_text),
    )


async def _undo_request(messages: list[str]) -> str | None:
    """The customer's own words asking for a blocked card to be made usable again
    (unfreeze, unblock, reactivate, release), or None. The bank's service is named
    "freeze/unfreeze", so the classifier sends both here; this is the one place that
    tells them apart, by extracting a quote (which the 8B does reliably) rather than
    judging yes/no. Any failure returns None."""
    said = "\n".join(f'- "{_LONG_DIGITS_RE.sub(_mask_digit_run, m)}"' for m in messages)
    prompt = (
        f"A bank customer wrote these chat messages:\n{said}\n\n"
        "Copy, exactly as written, the words in which the customer asks for a blocked or frozen "
        "card to be made usable again (unfreeze, unblock, reactivate, release). Use null when "
        "they do not ask for that.\n"
        'Reply only with JSON: {"undo_request": "<words>" or null}'
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json",
                      "think": settings.OLLAMA_THINK,
                      "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0}},
            )
            resp.raise_for_status()
            parsed = json.loads(resp.json().get("response") or "{}")
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return _grounded(_quoted(parsed.get("undo_request")), " ".join(messages))


def _grounded(quote: str | None, said: str) -> str | None:
    """Keep a quote only if most of its words really appear in what the customer
    wrote -- the model otherwise invents "my card was stolen" for "freeze my card"."""
    if not quote:
        return None
    words = re.findall(r"\w+", quote.lower())
    said_words = set(re.findall(r"\w+", said.lower()))
    if not words:
        return None
    return quote if sum(w in said_words for w in words) / len(words) >= 0.7 else None


# A hint (not a sentence) for the composer, plus what they could mean: the generic clarification
# block in _chat_stream words it once, for this message.
_CARD_PROBLEM_HINT = "what is happening with their card (freezing or reporting is for a lost, stolen or misused card)"
_CARD_PROBLEM_OPTIONS = ("a lost or stolen card", "freezing a card", "card details and requests")


async def _ground_freeze_request(result, message: str, recent_turns: list[ChatTurn]):
    """Freeze only. The classifier invents a plausible reason ("lost") and routes
    vague card problems ("my card isn't working", "reset my PIN") to freeze. Keep the
    freeze only if the customer asked to block the card or said why; the reason is
    the customer's own words, never the classifier's guess."""
    key = (result.category, result.service) if isinstance(result, BankingService) else None
    if key not in (_FREEZE_KEY, ("card_requests", "report_lost_card")):
        return result
    messages = [t.message for t in (recent_turns or [])[-2:] if t.message] + [message]
    if key == _FREEZE_KEY and await _undo_request([message]):
        # Unfreezing is done in the app: hand over to that app action (never start a freeze for it).
        return BankingService(ui_actions.CATEGORY, "card_unfreeze", None, None)
    reason, block_request = await _freeze_request_facts(messages)
    if key != _FREEZE_KEY:
        # Report lost/stolen (redirect to destroy + replace): only when the customer's
        # own words say what happened -- "my card isn't working" went here live.
        if reason or block_request:
            return result
        return Clarification(_CARD_PROBLEM_HINT, _CARD_PROBLEM_OPTIONS)
    if not reason and not block_request:
        return Clarification(_CARD_PROBLEM_HINT, _CARD_PROBLEM_OPTIONS)
    payload = dict(result.payload or {})
    payload.pop("reason", None)
    if reason:
        payload["reason"] = reason
    return BankingService(result.category, result.service, result.subservice, payload or None)


async def _llm_pick_candidate(message: str, candidates: list[dict]) -> int | None:
    """Ask the model which numbered option (if any) the customer's reply picks.
    Options are shown masked (type + last 4 only). Returns a 0-based index, or
    None when the reply doesn't clearly pick exactly one option."""
    options = "\n".join(
        f"{i}. {_describe_selection_account(c)}" for i, c in enumerate(candidates, start=1)
    )
    prompt = (
        "A bank customer was asked which of these they meant:\n"
        f"{options}\n\n"
        f"The customer replied: \"{_LONG_DIGITS_RE.sub(_mask_digit_run, message)}\"\n\n"
        "If the reply clearly picks exactly one option (by its type, its last digits, its "
        "position, or any other wording, in English, Bangla or Banglish), answer with that "
        "option's number. If the reply is a different question, is unclear, or could mean "
        "more than one option, answer null. Respond only with JSON: {\"choice\": <number or null>}"
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0},
                },
            )
            resp.raise_for_status()
            choice = json.loads(resp.json().get("response") or "{}").get("choice")
    except Exception:
        return None
    if isinstance(choice, int) and not isinstance(choice, bool) and 1 <= choice <= len(candidates):
        return choice - 1
    return None


def _selection_payload(candidate: dict) -> dict:
    """Payload fields that tell the original service's resolver which account/card
    was picked (each resolver in real.py skips its lookup when these are present)."""
    if "transactionId" in candidate:
        return {"transactionReferenceNo": candidate["transactionId"],
                "transactionSummary": _describe_selection_account(candidate)}
    if "cardNumber" in candidate:
        return {"cardId": candidate.get("id"), "cardLast4": _candidate_number(candidate)[-4:]}
    if "identifier" in candidate and "accountNumber" not in candidate:
        return {"id": candidate.get("identifier")}
    picked = {"accountNumber": candidate.get("accountNumber")}
    if candidate.get("id") is not None:
        picked["id"] = candidate.get("id")
    return picked


async def _try_account_selection_completion(
    recent_turns: list[ChatTurn], message: str, req_payload: dict | None
) -> BankingService | None:
    """If the last turn asked the customer to pick one of several accounts/cards,
    resolve their reply to exactly one stored candidate and resume the original
    request with it. An exact id from the frontend's picker, or the exact last
    digits of one candidate's number, is matched directly (data, not wording);
    anything else is read by the model (_llm_pick_candidate). Returns None when the
    reply doesn't pick exactly one candidate -- a new request falls through to
    classify()."""
    if not recent_turns:
        return None
    last = recent_turns[-1].classification or {}
    if last.get("type") not in _SELECTION_TYPES or not last.get("candidates"):
        return None
    candidates = [c for c in last["candidates"] if isinstance(c, dict)]
    chosen = None

    if req_payload:
        picked = {str(req_payload.get(k)) for k in ("accountNumber", "id", "identifier", "cardId", "transactionId")
                  if req_payload.get(k) is not None}
        matches = [c for c in candidates
                   if picked & {str(c.get(k)) for k in ("accountNumber", "id", "identifier", "transactionId")}]
        if len(matches) == 1:
            chosen = matches[0]

    lowered = message.lower()
    if chosen is None:
        for digits in re.findall(r"\d{4,}", lowered):
            matches = [c for c in candidates if _candidate_number(c).endswith(digits[-4:])]
            if len(matches) == 1:
                chosen = matches[0]
                break

    if chosen is None:
        index = await _llm_pick_candidate(message, candidates)
        if index is None:
            return None
        chosen = candidates[index]
    return BankingService(
        category=last.get("category"),
        service=last.get("service"),
        subservice=last.get("subservice"),
        payload={**(last.get("payload") or {}), **_selection_payload(chosen)},
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _result_event(
    result_type: str,
    category: str | None,
    service: str | None,
    subservice: str | None,
    payload: dict | None = None,
    routing: dict | None = None,
) -> str:
    return _sse(
        "result",
        {
            "type": result_type,
            "category": category,
            "service": service,
            "subservice": subservice,
            "payload": payload,
            "routing": routing,
            "version": "1.0",
        },
    )


def _mask_number(value: object, keep: int = 4) -> str | None:
    s = str(value) if value is not None else ""
    if len(s) <= keep:
        return s or None
    return "•" * (len(s) - keep) + s[-keep:]


def _format_bdt(amount: object) -> str | None:
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return None
    return f"৳{n:,.0f}"


# The bank platform returns money in POISHA (1 taka = 100 poisha) everywhere
# except merchant/v1/qr/* (taka) -- confirmed against the bank app's own
# Money.fromPoisha parsing. These are the response keys that carry money.
_POISHA_KEYS = frozenset({
    "balanceAfterThisTransaction", "amountSent", "totalFee", "totalYouPay",
    "balance", "amount", "totalAmount", "principalAmount", "charge", "vat", "total",
    "openingBalance", "closingBalance", "creditLimit", "totalOutstanding",
    "availableCredit", "unbilledAmount", "statementDueAmount", "minimumDueAmount",
    "disputedAmount", "amountPaid", "remainingOutstanding", "balanceAtIssuance",
    "current", "bankMax", "riskAdjustedMax", "used", "usedToday", "currentDailyLimit",
    "bankMaxDailyLimit", "riskAdjustedMaxDailyLimit", "requestedDailyLimit",
})
_TAKA_SERVICES = frozenset({"qr_payment_history"})


def _format_poisha(amount: object) -> str | None:
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return None
    return f"৳{n / 100:,.2f}"


def _tk_text(amount: object, divisor: int = 100) -> str | None:
    """Money as plain text for LLM prompts. Never the ৳ sign: llama3.1 misreads
    U+09F3 as a digit and wrote "৳31,002,..." for a ৳1,002,... balance."""
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return None
    return f"Tk {n / divisor:,.2f}"


def _is_numeric(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    return isinstance(value, str) and re.fullmatch(r"-?\d+(\.\d+)?", value.strip()) is not None


_DIGIT_RUN_RE = re.compile(r"\d{6,}")
_LONG_DIGITS_RE = re.compile(r"\d{8,}")


def _mask_digit_run(match: re.Match) -> str:
    digits = match.group()
    return "•" * (len(digits) - 4) + digits[-4:]


def _redact_for_prompt(data: dict, service: str | None = None) -> dict:
    """Deep copy of `data` with sensitive raw fields stripped/masked before it
    is embedded in the LLM prompt, and every money field converted to a
    ready-to-say taka string so the model never has to interpret poisha.
    Never mutates `data` itself — the raw dict is still returned unchanged to
    the frontend via the `result` payload."""
    divisor = 1 if service in _TAKA_SERVICES else 100
    try:
        redacted = copy.deepcopy(data)

        def walk(node):
            if isinstance(node, dict):
                for key in [k for k in node if k.endswith("Formatted")]:
                    del node[key]
                # Known money keys, plus any key the bank names "...Poisha" (live:
                # card products' issuanceFeePoisha was read as 57,888 taka).
                for key in (_POISHA_KEYS & node.keys()) | {k for k in node if k.endswith("Poisha")}:
                    if _is_numeric(node[key]):
                        node[key] = _tk_text(node[key], 100 if key.endswith("Poisha") else divisor)
                if "accountNumber" in node:
                    node["accountNumber"] = node.get("accountNumberMasked", "[masked]")
                if "identifier" in node:
                    node["identifier"] = node.get("identifierMasked", "[masked]")
                # Identity numbers are dropped outright: a "[redacted]" placeholder
                # just made the model announce "your CIF is [redacted]".
                for key in ("cifNumber", "cif", "nid"):
                    node.pop(key, None)
                # Any other bare digit run long enough to be an account/card/phone
                # number (e.g. a card's linkedAccountNumber) keeps only its last 4.
                for key, value in node.items():
                    if isinstance(value, str) and _LONG_DIGITS_RE.fullmatch(value):
                        node[key] = _mask_digit_run(re.match(r"\d+", value))
                for key in ("description", "fromToAccount"):
                    value = node.get(key)
                    if isinstance(value, str):
                        node[key] = _DIGIT_RUN_RE.sub(_mask_digit_run, value)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(redacted)
        return redacted
    except Exception:
        return data


def _compact_for_prompt(node):
    """Fewer prompt tokens, same facts: drop link fields (icon URLs) the reply never
    uses. On the M40 every ~250 prompt tokens cost ~1 s. Nulls stay ("not set" is an
    answer), and so do empty lists ("none"). Every list of records also gets its total."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                continue
            out[key] = _compact_for_prompt(value)
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                # A count the model can state, so it never has to count nested rows itself.
                out[f"{key} (total)"] = len(value)
        return out
    if isinstance(node, list):
        return [_compact_for_prompt(item) for item in node]
    return node


def _label_running_balances(data):
    """A transaction's own `balance` is the balance right after it, not the current
    balance. Live, "balance and last transactions" was answered "current balance is
    Tk 95,000.00" from a transaction row while the real balance was Tk 90,000.00.
    Renamed for the reply only."""
    if isinstance(data, list):
        return [_label_running_balances(item) for item in data]
    if not isinstance(data, dict):
        return data
    out = {}
    for key, value in data.items():
        if key in ("transactions", "records", "statements") and isinstance(value, list):
            value = [
                {("balanceAfterThisTransaction" if k == "balance" else k): v for k, v in row.items()}
                if isinstance(row, dict) else row
                for row in value
            ]
        out[key] = _label_running_balances(value)
    return out


def _fee_quote_for_prompt(data: dict) -> dict:
    """The bank's fee quote has fees.total (the FEE) next to totalAmount (what the
    customer PAYS); live, the reply read "total" as the fee total and said a Tk 15,000
    transfer would cost "Tk 0.00" in total. Unambiguous names for the reply only."""
    if not isinstance(data, dict):
        return data
    fees = data.get("fees") if isinstance(data.get("fees"), dict) else {}
    return {
        "whatThisIs": "a fee ESTIMATE only — no money has been sent; nothing has happened yet. "
                      "Describe it as what they WOULD pay if they send this amount.",
        "amountSent": data.get("principalAmount"),
        "charge": fees.get("charge"),
        "vat": fees.get("vat"),
        "totalFee": fees.get("total"),
        "totalYouPay": data.get("totalAmount"),
    }


def _accounts_for_prompt(data: dict) -> dict:
    """The accounts payload lists each account twice: under `accounts` (core record,
    whose `balance` is not the live balance -- 0 live while the real one was
    Tk 90,000) and under `ledgerAccounts` (the accounting ledger, same source as the
    balance service). Live, the reply quoted Tk 0.00 and counted two accounts. For
    the reply only: each account takes its ledger balance and the matching ledger
    entry is dropped. The frontend payload is untouched."""
    inner = data.get("data") if isinstance(data, dict) else None
    if not isinstance(inner, dict):
        return data
    accounts = inner.get("accounts") if isinstance(inner.get("accounts"), list) else []
    # Linked credit/prepaid cards are listed as "card-<n>" rows with balance 0 since
    # 2026-10-04 -- they're cards (see the cards service), not accounts to count.
    accounts = [a for a in accounts if not _is_card_row(a)]
    ledgers = inner.get("ledgerAccounts") if isinstance(inner.get("ledgerAccounts"), list) else []
    by_number = {str(l.get("identifier")): l for l in ledgers if isinstance(l, dict)}
    merged, used = [], set()
    for account in accounts:
        if not isinstance(account, dict):
            continue
        account = dict(account)
        ledger = by_number.get(str(account.get("accountNumber")))
        if ledger is not None:
            account["balance"] = ledger.get("balance")
            used.add(str(account.get("accountNumber")))
        merged.append(account)
    rest = [l for l in ledgers if isinstance(l, dict) and str(l.get("identifier")) not in used]
    view = dict(inner)
    view["accounts"] = merged
    if rest:
        view["ledgerAccounts"] = rest
    else:
        view.pop("ledgerAccounts", None)
    return {**data, "data": view}


def _reply_prompt(message: str, service: str, subservice: str | None, data: dict) -> tuple[list[dict], str, dict]:
    """(chat messages, data_json, redacted) for the data-answering reply -- shared by the
    streamed and non-streamed paths so both send the model the identical prompt."""
    if (subservice or service) == "accounts":
        data = _accounts_for_prompt(data)
    if (subservice or service) == "fee_quote":
        data = _fee_quote_for_prompt(data)
    data = _label_running_balances(data)
    redacted = _redact_for_prompt(data, subservice or service)
    data_json = json.dumps(_compact_for_prompt(redacted), default=str, ensure_ascii=False,
                           separators=(",", ":"))
    messages = build_messages(
        "answer", {"what you know about their account": _compact_for_prompt(redacted)},
        message, None, {})
    return messages, data_json, redacted


async def _synthesize_reply(message: str, service: str, subservice: str | None, data: dict) -> str:
    """LLM-written reply answering the customer's actual question from the real
    fetched data only. Every 3+-digit number in the reply must exist in that data;
    a reply that fails the check is regenerated once at temperature 0, and only if
    that also fails (or Ollama is down) does the deterministic summary stand in."""
    messages, data_json, redacted = _reply_prompt(message, service, subservice, data)
    for temperature in (0.2, 0.0):
        text = await generate_chat(messages, temperature)
        if text is None:
            break
        if text and check_reply(text, data_json, {}) is None:
            return text
    return _data_fallback(redacted)


# End of a sentence: . ! ? or a newline, followed by whitespace ("90,000.00." mid-number never matches).
_SENTENCE_END_RE = re.compile(r"[.!?\n](?=\s)")


async def _stream_reply(message: str, service: str, subservice: str | None, data: dict):
    """Same reply as _synthesize_reply, streamed so the customer sees it as it is
    written (a transaction list took ~14 s to finish on the M40). Text is released a
    whole sentence at a time, and every released 3+-digit number has passed the same
    check against the data. If the model goes wrong before anything
    was sent, the non-streamed path (retry + deterministic fallback) answers instead;
    if it goes wrong mid-way, generation stops and the deterministic facts finish
    the reply -- no unverified number is ever sent."""
    messages, data_json, redacted = _reply_prompt(message, service, subservice, data)
    full, sent = "", 0
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "messages": messages,
                    "stream": True,
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.2, "num_predict": 400},
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    full += (chunk.get("message") or {}).get("content") or ""
                    done = bool(chunk.get("done"))
                    ends = [m.end() for m in _SENTENCE_END_RE.finditer(full)]
                    cut = len(full) if done else (ends[-1] if ends else 0)
                    safe = full[:cut]
                    if any(sym in safe for sym in _FOREIGN_CURRENCY) or unsupported_numbers(safe, data_json):
                        raise ValueError("unsupported number in streamed reply")
                    piece = safe[sent:]
                    if sent == 0:
                        piece = piece.lstrip()
                    if piece:
                        yield piece
                        sent = cut
                    if done:
                        break
    except Exception:
        if sent == 0:
            yield await _synthesize_reply(message, service, subservice, data)
        else:
            gap = "" if full[:sent].endswith((" ", "\n")) else " "
            yield gap + _data_fallback(redacted)
        return
    if sent == 0:
        yield await _synthesize_reply(message, service, subservice, data)


def _enrich_payload(service: str, subservice: str | None, data: dict) -> dict:
    """Add masked/formatted display fields to a real-adapter payload, additive only
    (never removes/overwrites raw fields). Defensive against missing/malformed
    shapes — never raises. Returns data unchanged for shapes it doesn't recognize."""
    key = subservice or service
    try:
        enriched = copy.deepcopy(data)
    except Exception:
        return data

    try:
        if key == "balance":
            if isinstance(enriched, dict):
                enriched["balanceFormatted"] = _format_poisha(enriched.get("balance"))
            return enriched

        if key == "accounts":
            inner = enriched.get("data") if isinstance(enriched, dict) else None
            if isinstance(inner, dict):
                accounts = inner.get("accounts")
                if isinstance(accounts, list):
                    for a in accounts:
                        if isinstance(a, dict):
                            a["accountNumberMasked"] = _mask_number(a.get("accountNumber"))
                ledger_accounts = inner.get("ledgerAccounts")
                if isinstance(ledger_accounts, list):
                    for led in ledger_accounts:
                        if isinstance(led, dict):
                            led["identifierMasked"] = _mask_number(led.get("identifier"))
                            led["balanceFormatted"] = _format_poisha(led.get("balance"))
            return enriched

        if key == "transaction_history":
            transactions = enriched.get("transactions") if isinstance(enriched, dict) else None
            if isinstance(transactions, list):
                for t in transactions:
                    if isinstance(t, dict):
                        t["accountNumberMasked"] = _mask_number(t.get("accountNumber"))
                        t["amountFormatted"] = _format_poisha(t.get("amount"))
            return enriched
    except Exception:
        return data

    return data


def _data_fallback(data) -> str:
    """Degraded mode (the model's replies kept failing the number check): the data's
    top-level facts as plain 'label: value' lines -- no prose, no template."""
    flat = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                flat[key] = f"{len(value)} item(s)"
            elif not isinstance(value, dict):
                flat[key] = value
    return facts_listing(flat)


def _describe_selection_account(a: dict) -> str:
    """Builds one human-readable option for _account_selection_reply(). Three
    shapes reach here: _resolve_account_number's regular bank accounts
    (accountType/accountNumber) and _resolve_ledger_account_identifier's
    FD/DPS ledger accounts (identifier/chartOfAccountName), both raised as
    AdapterAccountSelectionRequiredError -- and, as of T-57, a plain card
    dict from CardsAdapter's list (cardType/cardNumber) when the card-freeze
    flow finds 2+ cards and needs the customer to pick one (not raised as
    that exception -- resolved directly in _chat_stream, see the
    card_services/frezz_unfrezz branch). Each shape needs its own description
    built from the fields it actually has."""
    if "transactionId" in a:
        amount = _tk_text(a.get("amount")) if _is_numeric(a.get("amount")) else str(a.get("amount") or "")
        when = str(a.get("txnTime") or "")[:10]
        kind = str(a.get("type") or "").lower()
        return f"{amount} {a.get('transactionType') or ''} {kind} on {when}".replace("  ", " ").strip()
    if "accountType" in a or "accountNumber" in a:
        account_type = a.get("accountType", "account").title()
        account_number = str(a.get("accountNumber", ""))
        return f"{account_type} account ending {account_number[-4:]}"
    if "cardType" in a or "cardNumber" in a:
        card_type = str(a.get("cardType") or "card").title()
        card_number = str(a.get("cardNumber") or "")
        return f"{card_type} card ending {card_number[-4:]}"
    chart_of_account_name = a.get("chartOfAccountName") or "Account"
    identifier = str(a.get("identifier") or "")
    return f"{chart_of_account_name} ending {identifier[-6:]}"


def _match_beneficiaries(name_query: str, beneficiaries: list[dict]) -> list[dict]:
    """Deterministic (no LLM) case-insensitive match of `name_query` against each
    beneficiary's `nickname`/`accountHolderName`. Substring/prefix matches are
    preferred; if none are found, falls back to `difflib` fuzzy matching over the
    same fields. Skips entries missing both fields rather than raising."""
    query = (name_query or "").strip().lower()
    if not query or not isinstance(beneficiaries, list):
        return []

    substring_matches: dict[int, dict] = {}
    fuzzy_pool: dict[str, dict] = {}
    for b in beneficiaries:
        if not isinstance(b, dict):
            continue
        names = []
        for field in ("nickname", "accountHolderName"):
            value = b.get(field)
            if isinstance(value, str) and value.strip():
                names.append(value.strip().lower())
        if not names:
            continue
        if any(query in name or name.startswith(query) for name in names):
            substring_matches[id(b)] = b
            continue
        for name in names:
            fuzzy_pool.setdefault(name, b)

    if substring_matches:
        return list(substring_matches.values())

    close_names = difflib.get_close_matches(query, fuzzy_pool.keys(), n=5, cutoff=0.6)
    fuzzy_matches: dict[int, dict] = {}
    for name in close_names:
        b = fuzzy_pool[name]
        fuzzy_matches[id(b)] = b
    return list(fuzzy_matches.values())


def _resolve_beneficiary_destination(beneficiary: dict) -> dict | None:
    """Mirrors the mobile app's `beneficiarySendRoute()` switch on `serviceType`
    (see beneficiary-to-transfer-flow.md) — `None` means no deterministic
    destination (e.g. CARD_PAYMENT), same as that function's `null` case."""
    service_type = beneficiary.get("serviceType")
    if service_type == "OWN_BANK":
        return {"action": "own_bank_transfer"}
    if service_type == "OTHER_BANK":
        return {"action": "other_bank_transfer"}
    if service_type == "MFS":
        provider = beneficiary.get("mfsProvider")
        if provider:
            return {"action": "wallet_transfer", "provider": str(provider).lower()}
        return None
    return None


def _subservice_name(category: str | None, service: str | None, subservice: str | None) -> str | None:
    """A sub-service's own name from the live taxonomy (e.g. "Other Bank Transfer")."""
    for cat in get_taxonomy().get("categories", []):
        if cat.get("id") != category:
            continue
        for svc in cat.get("services", []):
            if svc.get("id") == service:
                for sub in svc.get("subServices") or []:
                    if sub.get("id") == subservice:
                        return sub.get("name")
    return None


def _tail(value) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-4:] if len(digits) >= 4 else None


def _confirm_say(key: tuple, payload: dict | None) -> tuple:
    """Facts for the yes/no before a change (T-77: no template)."""
    payload = payload or {}
    common = {"to_confirm": "say yes", "to_cancel": "say no"}
    if key == ("beneficiary_management", "beneficiary_add"):
        must = {"nickname": payload.get("nickname"), "account ending": _tail(payload.get("accountNumber"))}
        return _say("confirm", must, change="save a new beneficiary for future transfers",
                    account_holder=payload.get("accountHolderName"),
                    bank=payload.get("bankName") or ("Polygon Bank" if payload.get("serviceType") == "OWN_BANK" else None),
                    branch=payload.get("branchName"), what_it_means="nothing is sent now; it is only saved", **common)
    if key == ("support", "submit_complaint"):
        text = str(payload.get("description") or "")
        must = {"complaint": text} if len(text) <= 120 else {}
        return _say("confirm", must, change="submit a complaint to the bank",
                    complaint_type=str(payload.get("category") or "OTHER").replace("_", " ").lower(),
                    complaint_text=text if len(text) > 120 else None,
                    what_happens_next="it appears under My Tickets", **common)
    if key == ("profile_update", "update_nickname"):
        return _say("confirm", {"nickname": payload.get("nickName")}, change="change their nickname",
                    what_it_means="only the name shown in the app changes", **common)
    if key == _ADDRESS_KEY:
        must = {_ADDRESS_LABELS[f]: payload[f] for f in _ADDRESS_LABELS if payload.get(f)}
        return _say("confirm", must, change="update the address on their profile", **common)
    if key == _FREEZE_KEY:
        return _say("confirm", _card_must(payload), change="temporarily freeze this card so it can't be used for payments",
                    their_reason=payload.get("reason"),
                    what_happens_next="a verification code is sent to their phone, then they enter it with their PIN or "
                                      "password in the app's secure form", **common)
    return _say("confirm", change=_service_name(*key), **common)


def _done_say(key: tuple, payload: dict | None) -> tuple:
    payload = payload or {}
    if key == ("beneficiary_management", "beneficiary_add"):
        return _say("done", {"nickname": payload.get("nickname")}, what="the beneficiary was saved",
                    next_option="they can now send money to them")
    if key == ("support", "submit_complaint"):
        return _say("done", what="the complaint was submitted", where_to_follow_it="My Tickets in the app")
    if key == ("profile_update", "update_nickname"):
        return _say("done", {"nickname": payload.get("nickName")}, what="the nickname was changed")
    if key == _ADDRESS_KEY:
        return _say("done", {_ADDRESS_LABELS[f]: payload[f] for f in _ADDRESS_LABELS if payload.get(f)},
                    what="the address was updated")
    return _say("done", what=f"{_service_name(*key)} completed")


def _transfer_summary_say(service: str, subservice: str | None, payload: dict) -> tuple:
    """No transfer is executed in chat (ADR-0008): the customer finishes it in the app."""
    amount = payload.get("amount")
    must = {"amount": f"Tk {amount}"} if amount is not None else {}
    if service == "wallet_transfer":
        must["wallet number"] = payload.get("walletNumber")
    else:
        must["account ending"] = _tail(payload.get("accountNumber"))
    return _say("summary", must, transfer_type=_subservice_name("transfer", service, subservice) or subservice,
                where_to_finish="the transfer screen in the app, which opens next",
                done_in_chat="no; they confirm and send it in the app")


def _dispute_summary_say(payload: dict) -> tuple:
    """The dispute is never submitted in chat: the customer finishes it in the app."""
    return _say("summary", {"account ending": _tail(payload.get("accountNumber"))},
                request="raise a dispute about a transaction",
                transaction=payload.get("transactionSummary"),
                their_reason=payload.get("remarks"),
                where_to_finish="the dispute screen in the app, which opens next",
                done_in_chat="no; they submit it in the app")


def _choose_say(question_about: str, items: list[dict]) -> tuple:
    return _say("choose", question_about=question_about,
                options=[_describe_selection_account(i) for i in items])


def _beneficiary_name(beneficiary: dict) -> str | None:
    return beneficiary.get("nickname") or beneficiary.get("accountHolderName")


def _trim_beneficiary(beneficiary: dict) -> dict:
    return {
        "id": beneficiary.get("id"),
        "nickname": beneficiary.get("nickname"),
        "accountHolderName": beneficiary.get("accountHolderName"),
        "serviceType": beneficiary.get("serviceType"),
        "mfsProvider": beneficiary.get("mfsProvider"),
    }


async def _kb_stream(req: ChatRequest, request_id: str):
    top_k = req.top_k or settings.DEFAULT_TOP_K
    try:
        query_vector = await embed_text(req.message)
        hits = search(query_vector, top_k)
    except httpx.HTTPStatusError as e:
        detail = f"Embedding model rejected the request: {e.response.text.strip()}"
        logger.warning(json.dumps({"request_id": request_id, "stage": "embedding", "detail": detail}))
        yield _sse("error", {"detail": detail})
        return
    except httpx.HTTPError:
        detail = "Embedding model (Ollama) is unreachable"
        logger.warning(json.dumps({"request_id": request_id, "stage": "embedding", "detail": detail}))
        yield _sse("error", {"detail": detail})
        return
    except Exception:
        detail = "Vector store (Qdrant) is unreachable"
        logger.error(json.dumps({"request_id": request_id, "stage": "vector_search", "detail": detail}))
        yield _sse("error", {"detail": detail})
        return

    logger.info(json.dumps({
        "request_id": request_id,
        "hit_count": len(hits),
        "top_score": hits[0]["score"] if hits else None,
    }))

    prompt = build_prompt(req.message, hits)
    answer_parts: list[str] = []
    try:
        async for token in stream_generate(prompt):
            answer_parts.append(token)
            yield _sse("token", {"token": token})
    except httpx.HTTPError:
        detail = "Generation model (Ollama) failed or became unreachable mid-stream"
        logger.error(json.dumps({"request_id": request_id, "stage": "generation", "detail": detail}))
        yield _sse("error", {"detail": detail})
        return

    logger.info(json.dumps({"request_id": request_id, "answer": "".join(answer_parts)}))

    grounded = len(hits) > 0
    sources: list[str] | None = None
    if grounded:
        sources = []
        for c in hits:
            filename = c.get("filename")
            if filename and filename not in sources:
                sources.append(filename)
    yield _result_event(
        "KB_ANSWER",
        None,
        None,
        None,
        payload={"grounded": grounded, "hitCount": len(hits), "sources": sources},
    )

    yield _sse("done", {})


_REDACTED_SUBMISSION = "[redacted: verification submission]"


def _history(turns: list[ChatTurn] | None) -> list[tuple[str, str]]:
    """Recent conversation for the composer: what the customer said and what the
    assistant asked/said, oldest first. Verification submissions are never included."""
    out: list[tuple[str, str]] = []
    for turn in (turns or [])[-3:]:
        if turn.message and not turn.message.startswith("[redacted"):
            out.append(("Customer", turn.message))
        said = (turn.classification or {}).get("question")
        if said:
            out.append(("Assistant", said))
    return out


def _safe_for_model(message: str, payload: dict | None) -> str:
    """The customer's text as the composer may see it: never a typed code/password."""
    if _has_secret_fields(payload) or _looks_like_typed_secret(message):
        return "(the customer submitted the secure verification form)"
    return message


async def _emit_outcome(
    outcome: _TurnOutcome, request_id: str, customer_identity, turn_started_at: float,
    *, message: str = "", history: list[tuple[str, str]] | None = None,
):
    """Composes the outcome's message (streamed), then the result event, plus its
    per-turn log line and audit line. Logged payload is always secret-redacted."""
    kind, facts, must = outcome.say
    text = ""
    async for piece in compose_stream(kind, facts, message=message, history=history, must_include=must):
        text += piece
        yield _sse("token", {"token": piece})
    outcome.token = text
    if "question" in outcome.stored:
        outcome.stored["question"] = text
    logger.info(json.dumps({
        "request_id": request_id,
        "type": outcome.result_type,
        "token": outcome.token,
        "payload": _redact_secrets(outcome.result_payload),
    }, default=str))
    audit.log_banking_turn(
        customer_identity,
        outcome.classification(),
        latency_ms=(time.monotonic() - turn_started_at) * 1000,
        request_id=request_id,
    )
    yield _result_event(
        outcome.result_type, outcome.category, outcome.service, outcome.subservice,
        payload=outcome.result_payload, routing=outcome.routing,
    )


def _session_safe_classification(classification: dict | None) -> dict | None:
    """Turn classification as persisted in session state: pin/password/otp stripped
    from any stored payload (defence in depth -- the freeze-OTP helpers already never
    put them there)."""
    if not isinstance(classification, dict):
        return classification
    return _strip_secrets(classification)


async def _chat_stream(req: ChatRequest, authorization: str | None):
    request_id = uuid.uuid4().hex
    token = extract_jwt(authorization)
    turn_started_at = time.monotonic()
    customer_identity = await verify_jwt(token) if token else None

    session_turns: list[ChatTurn] = get_session(customer_identity.customer_id) if customer_identity else []
    # T-77: every message is composed with the conversation so far, from text that
    # can never contain a typed code/password.
    history = _history(session_turns)
    composer_message = _safe_for_model(req.message, req.payload)
    # What is written to the session and the log: a typed code/password is never kept,
    # at any step (a code typed into a yes/no step is as sensitive as one at an OTP step).
    stored_message = (_REDACTED_SUBMISSION if _has_secret_fields(req.payload) or _looks_like_typed_secret(req.message)
                      else req.message)

    async def say_text(say: tuple) -> str:
        kind, facts, must = say
        return await compose(kind, facts, message=composer_message, history=history, must_include=must)
    last_session_classification = (session_turns[-1].classification or {}) if session_turns else {}

    # T-57: a pending freeze OTP step. Applies to a plain follow-up, or to an explicit
    # resubmit of the SAME category+service that carries otp/pin/password (frontends
    # may echo the routing fields back) -- any other explicit category+service is a
    # fresh request, same rule as the yes/no confirmation gate below.
    pending_otp: dict | None = None
    pending_reading = "unsure"
    if last_session_classification.get("type") == _OTP_PENDING_TYPE:
        explicit_pair = (req.category, req.service) if (req.category and req.service) else None
        pending_pair = (last_session_classification.get("category"), last_session_classification.get("service"))
        if explicit_pair is None or (explicit_pair == pending_pair and _has_secret_fields(req.payload)):
            pending_otp = last_session_classification
        # A plain chat message with no form submission only stays inside the freeze
        # step when it's a cancel or looks like a code/password typed into the chat
        # box (never logged or sent to an LLM). Anything else means the customer has
        # moved on: the freeze is dropped and the message is handled normally.
        if pending_otp is not None and explicit_pair is None:
            pending_reading = await _read_pending_reply(
                pending_otp.get("question"), req.message, req.payload)
            if pending_reading == "other":
                pending_otp = None

    logger.info(json.dumps({
        "request_id": request_id,
        # While an OTP step is pending, the free-text message is never logged: a
        # customer may type their code/PIN into the chat box instead of the form.
        "message": "[redacted: pending verification]" if pending_otp is not None else stored_message,
        "session_id": req.session_id,
        "top_k": req.top_k,
        "category": req.category,
        "service": req.service,
        "subservice": req.subservice,
        "payload": _redact_secrets(req.payload),
        "auth_present": token is not None,
    }))

    if pending_otp is not None:
        otp_handler = (
            _handle_contact_otp_reply
            if (pending_otp.get("category"), pending_otp.get("service")) in _CONTACT_KEYS
            else _handle_freeze_otp_reply
        )
        outcome = await otp_handler(customer_identity, token, pending_otp, req.message, req.payload,
                                    declined=(pending_reading == "decline"))
        # Composed from facts like every message; exact values (card ending, new
        # email/number) are validated attached to their labels.
        async for chunk in _emit_outcome(outcome, request_id, customer_identity, turn_started_at, message=composer_message, history=history):
            yield chunk
        yield _sse("done", {})
        record_turn(
            customer_identity.customer_id,
            ChatTurn(
                timestamp=datetime.now(timezone.utc),
                message=_REDACTED_SUBMISSION,
                classification=_session_safe_classification(outcome.classification()),
            ),
        )
        return

    recent_turns = get_classification_context(customer_identity.customer_id) if customer_identity else []
    reply_context = req.message

    # T-57/T-60: deterministic re-confirmation gate, checked before classify() is ever
    # called (same reasoning as _try_deterministic_payload_completion below -- this is
    # a free-text reply to a question WE just asked, never a fresh classification) and
    # independent of get_classification_context's gating (CONFIRMATION_REQUIRED is
    # deliberately not one of session.py's _PENDING_CLARIFICATION_TYPES -- a reply to
    # this pending state must never reach classify() at all, so recent_turns is
    # correctly empty for it; get_session is read directly here instead). Only applies
    # to a plain free-text message -- an explicit category+service request is always
    # treated as a fresh request, never as answering a pending confirmation.
    pending_confirmation: dict | None = None
    if (
        customer_identity is not None
        and not (req.category and req.service)
        and last_session_classification.get("type") == "CONFIRMATION_REQUIRED"
        and (last_session_classification.get("category"), last_session_classification.get("service"))
        in (_CONFIRM_CHANGE_KEYS | {_FREEZE_KEY})
    ):
        pending_confirmation = last_session_classification
        confirmation_reading = await _read_pending_reply(
            pending_confirmation.get("question"), req.message, req.payload)
        # A different request means the customer moved on: the pending change is
        # dropped -- never executed -- and the message is handled as a new request.
        if confirmation_reading == "other":
            pending_confirmation = None

    if pending_confirmation is not None:
        outcome = {"confirm": "affirmative", "decline": "negative"}.get(confirmation_reading, "unclear")
        conf_category = pending_confirmation.get("category")
        conf_service = pending_confirmation.get("service")
        conf_subservice = pending_confirmation.get("subservice")
        conf_payload = pending_confirmation.get("payload")
        conf_question = pending_confirmation.get("question") or "Shall I proceed? (yes/no)"
        confirmation_turn_classification: dict

        if outcome == "negative":
            decline_token = await say_text(_say("declined", what=_service_name(conf_category, conf_service)))
            yield _sse("token", {"token": decline_token})
            yield _result_event(
                "BANKING_SERVICE", conf_category, conf_service, conf_subservice,
                payload={"executed": False, "cancelled": True},
            )
            confirmation_turn_classification = {
                "type": "BANKING_SERVICE",
                "category": conf_category,
                "service": conf_service,
                "subservice": conf_subservice,
            }
            logger.info(json.dumps({"request_id": request_id, "type": "BANKING_SERVICE", "token": decline_token}))
            audit.log_banking_turn(
                customer_identity,
                confirmation_turn_classification,
                latency_ms=(time.monotonic() - turn_started_at) * 1000,
                request_id=request_id,
            )
        elif outcome == "unclear":
            reask_token = await say_text(_confirm_say((conf_category, conf_service), conf_payload))
            yield _sse("token", {"token": reask_token})
            yield _result_event("CONFIRMATION_REQUIRED", conf_category, conf_service, conf_subservice, payload=conf_payload)
            confirmation_turn_classification = {
                "type": "CONFIRMATION_REQUIRED",
                "category": conf_category,
                "service": conf_service,
                "subservice": conf_subservice,
                "payload": conf_payload,
                "question": conf_question,
            }
            logger.info(json.dumps({"request_id": request_id, "type": "CONFIRMATION_REQUIRED", "token": reask_token}))
            audit.log_banking_turn(
                customer_identity,
                confirmation_turn_classification,
                latency_ms=(time.monotonic() - turn_started_at) * 1000,
                request_id=request_id,
            )
        elif (conf_category, conf_service) == _FREEZE_KEY:
            # An explicit yes: only now is the verification code sent. The freeze itself
            # still only runs from the OTP_REQUIRED gate at the top of this function.
            freeze_outcome = await _send_freeze_otp(
                customer_identity, conf_category, conf_service, conf_subservice, conf_payload)
            async for chunk in _emit_outcome(freeze_outcome, request_id, customer_identity, turn_started_at,
                                             message=composer_message, history=history):
                yield chunk
            confirmation_turn_classification = freeze_outcome.classification()
        else:
            try:
                adapter_result = await fulfill_banking_service(
                    customer_identity, token, conf_category, conf_service, conf_subservice, conf_payload
                )
            except AdapterAuthError:
                confirm_auth_token = await say_text(_say("login_needed", request=_service_name(conf_category, conf_service)))
                yield _sse("token", {"token": confirm_auth_token})
                yield _result_event("AUTH_REQUIRED", conf_category, conf_service, conf_subservice)
                confirmation_turn_classification = {
                    "type": "AUTH_REQUIRED",
                    "category": conf_category,
                    "service": conf_service,
                    "subservice": conf_subservice,
                }
                logger.info(json.dumps({"request_id": request_id, "type": "AUTH_REQUIRED", "token": confirm_auth_token}))
                audit.log_banking_turn(
                    customer_identity,
                    confirmation_turn_classification,
                    latency_ms=(time.monotonic() - turn_started_at) * 1000,
                    request_id=request_id,
                )
            except AdapterUnavailableError as exc:
                # A readable refusal from the bank (e.g. "already saved", missing
                # field) is passed on verbatim; nothing was changed either way.
                if isinstance(exc, AdapterRejectedError):
                    # Not "nothing changed": live, the address PATCH saved and still answered
                    # 409 "A record with the given value already exists".
                    confirm_unavailable_token = await say_text(_say(
                        "refused_by_bank", request=_service_name(conf_category, conf_service),
                        bank_message=exc.bank_message, was_it_saved="unknown; check in the app"))
                else:
                    confirm_unavailable_token = await say_text(_say("unavailable", service=_service_name(conf_category, conf_service)))
                yield _sse("token", {"token": confirm_unavailable_token})
                yield _result_event("SERVICE_UNAVAILABLE", conf_category, conf_service, conf_subservice)
                confirmation_turn_classification = {
                    "type": "SERVICE_UNAVAILABLE",
                    "category": conf_category,
                    "service": conf_service,
                    "subservice": conf_subservice,
                }
                logger.info(json.dumps({
                    "request_id": request_id, "type": "SERVICE_UNAVAILABLE", "token": confirm_unavailable_token,
                }))
                audit.log_banking_turn(
                    customer_identity,
                    confirmation_turn_classification,
                    latency_ms=(time.monotonic() - turn_started_at) * 1000,
                    request_id=request_id,
                )
            else:
                executed_data = (
                    dict(adapter_result.data) if isinstance(adapter_result.data, dict) else {"result": adapter_result.data}
                )
                executed_data["executed"] = True
                success_token = await say_text(_done_say((conf_category, conf_service), conf_payload))
                yield _sse("token", {"token": success_token})
                yield _result_event(
                    "BANKING_SERVICE", conf_category, conf_service, conf_subservice,
                    payload=executed_data,
                    routing={
                        "category": conf_category, "service": conf_service, "subservice": conf_subservice,
                        "action": "redirect",
                    },
                )
                confirmation_turn_classification = {
                    "type": "BANKING_SERVICE",
                    "category": conf_category,
                    "service": conf_service,
                    "subservice": conf_subservice,
                }
                logger.info(json.dumps({
                    "request_id": request_id, "type": "BANKING_SERVICE", "token": success_token,
                    "payload": _redact_secrets(executed_data),
                }, default=str))
                audit.log_banking_turn(
                    customer_identity,
                    confirmation_turn_classification,
                    latency_ms=(time.monotonic() - turn_started_at) * 1000,
                    request_id=request_id,
                )

        yield _sse("done", {})
        record_turn(
            customer_identity.customer_id,
            ChatTurn(
                timestamp=datetime.now(timezone.utc),
                message=stored_message,
                classification=_session_safe_classification(confirmation_turn_classification),
            ),
        )
        return

    if req.category and req.service:
        if is_valid_path(req.category, req.service, req.subservice):
            result = BankingService(
                category=req.category,
                service=req.service,
                subservice=req.subservice,
                payload=req.payload,
            )
        else:
            result = UnknownService(
                category=req.category, service=req.service, subservice=req.subservice
            )
    else:
        fill_context = recent_turns
        result = await _try_account_selection_completion(recent_turns, req.message, req.payload)
        if result is None:
            if (not recent_turns and session_turns
                    and last_session_classification.get("type") == "BANKING_SERVICE"
                    and last_session_classification.get("request") is not None):
                fill_context = session_turns[-1:]  # a follow-up to the answered request
            result = await _llm_fill_pending_fields(fill_context, req.message)
        if result is not None:
            # A bare follow-up ("500", "the savings one") answered our question; the reply
            # must still answer what the customer originally asked.
            reply_context = f"{fill_context[-1].message} (follow-up answer: {req.message})"
        if result is None:
            # Nothing pending, but the last turn was ANSWERED: hand it over as context so
            # a follow-up that only changes a detail ("and for nagad?") stays on it.
            classify_context = recent_turns
            # Only after a fee quote (for "ok send it"): passing every answered turn
            # derailed new requests live (a beneficiary add after a dispute answer).
            if (not recent_turns and session_turns
                    and last_session_classification.get("type") == "BANKING_SERVICE"
                    and (last_session_classification.get("category"),
                         last_session_classification.get("service")) == ("fees", "fee_quote")
                    and last_session_classification.get("request") is not None):
                classify_context = session_turns[-1:]
            result = await classify(req.message, recent_turns=classify_context)
            if isinstance(result, BankingService) and req.payload is not None:
                result = BankingService(
                    category=result.category,
                    service=result.service,
                    subservice=result.subservice,
                    payload=req.payload,
                )
            result = _check_amount(result, req.message)
            result = _carry_forward_gathered(result, classify_context)
            result = await _ground_freeze_request(result, req.message, recent_turns)
            result = _normalize_fee_type(result, req.message)
            result = await _fill_known_from_message(result, req.message)

    result = _clean_extracted_fields(result)
    result = _normalize_change_request(result)
    turn_classification: dict | None = None

    if isinstance(result, KbQuestion):
        async for chunk in _kb_stream(req, request_id):
            yield chunk
        if customer_identity is not None:
            record_turn(
                customer_identity.customer_id,
                ChatTurn(timestamp=datetime.now(timezone.utc), message=stored_message, classification=None),
            )
        return

    if isinstance(result, Clarification) and _foreign_script(result.question, req.message):
        # Live: Banglish typed in Latin letters came back as garbled Bengali script.
        result = Clarification(question=_CLARIFICATION_FALLBACK)
    if isinstance(result, Clarification):
        # Always worded by the composer for THIS message: the classifier's own question is only
        # a hint of what is unclear, and the options (the services it could have meant) let the
        # reply offer concrete choices instead of "what do you need?".
        hint = None if result.question == _CLARIFICATION_FALLBACK else result.question
        result = Clarification(question=await say_text(_say(
            "clarify", what_is_unclear=hint or "what the customer would like to do",
            could_mean=list(result.options) or None,
            can_help_with=None if result.options else [
                "balance and transactions", "transfers and fees", "cards",
                "disputes and complaints", "profile details"])), options=result.options)
    if isinstance(result, Clarification):
        yield _sse("token", {"token": result.question})
        yield _result_event("CLARIFICATION_REQUIRED", None, None, None)
        turn_classification = {
            "type": "CLARIFICATION_REQUIRED",
            "category": None,
            "service": None,
            "subservice": None,
            "question": result.question,
        }
        logger.info(json.dumps({"request_id": request_id, "type": "CLARIFICATION_REQUIRED", "token": result.question}))
        audit.log_banking_turn(
            customer_identity,
            turn_classification,
            latency_ms=(time.monotonic() - turn_started_at) * 1000,
            request_id=request_id,
        )

    elif isinstance(result, UnknownService):
        unknown_service_token = await say_text(_say("not_in_chat", request=_service_name(result.category, result.service)))
        yield _sse("token", {"token": unknown_service_token})
        yield _result_event("UNKNOWN_SERVICE", result.category, result.service, result.subservice)
        turn_classification = {
            "type": "UNKNOWN_SERVICE",
            "category": result.category,
            "service": result.service,
            "subservice": result.subservice,
        }
        logger.info(json.dumps({"request_id": request_id, "type": "UNKNOWN_SERVICE", "token": unknown_service_token}))
        audit.log_banking_turn(
            customer_identity,
            turn_classification,
            latency_ms=(time.monotonic() - turn_started_at) * 1000,
            request_id=request_id,
        )

    elif isinstance(result, BankingService):
        category, service, subservice, payload = (
            result.category,
            result.service,
            result.subservice,
            result.payload,
        )

        if customer_identity is None:
            auth_required_token = await say_text(_say("login_needed", request=_service_name(category, service)))
            yield _sse("token", {"token": auth_required_token})
            yield _result_event("AUTH_REQUIRED", category, service, subservice)
            turn_classification = {
                "type": "AUTH_REQUIRED",
                "category": category,
                "service": service,
                "subservice": subservice,
            }
            logger.info(json.dumps({"request_id": request_id, "type": "AUTH_REQUIRED", "token": auth_required_token}))
            audit.log_banking_turn(
                customer_identity,
                turn_classification,
                latency_ms=(time.monotonic() - turn_started_at) * 1000,
                request_id=request_id,
            )
        else:
            if (category, service) in _CARD_PICK_KEYS and not (payload or {}).get("cardId"):
                # T-57: resolve which card before anything else -- cardId is
                # deliberately NOT part of _REQUIRED_PAYLOAD_FIELDS (unlike "reason"
                # below), since filling it in needs a real adapter call + 0/1/2+
                # branching, not a plain clarifying question. Mirrors
                # _resolve_account_number's "payload already has one -> skip the
                # call entirely" shortcut (the `not ... .get("cardId")` guard above).
                payload = dict(payload or {})
                try:
                    cards_result = await fulfill_banking_service(
                        customer_identity, token, "account_info", "cards", None, None
                    )
                except AdapterAuthError:
                    freeze_cards_auth_token = await say_text(_say("login_needed", request=_service_name(category, service)))
                    yield _sse("token", {"token": freeze_cards_auth_token})
                    yield _result_event("AUTH_REQUIRED", category, service, subservice)
                    turn_classification = {
                        "type": "AUTH_REQUIRED",
                        "category": category,
                        "service": service,
                        "subservice": subservice,
                    }
                    logger.info(json.dumps({
                        "request_id": request_id, "type": "AUTH_REQUIRED", "token": freeze_cards_auth_token,
                    }))
                    audit.log_banking_turn(
                        customer_identity,
                        turn_classification,
                        latency_ms=(time.monotonic() - turn_started_at) * 1000,
                        request_id=request_id,
                    )
                except AdapterUnavailableError:
                    freeze_cards_unavailable_token = await say_text(_say("unavailable", service="their card list"))
                    yield _sse("token", {"token": freeze_cards_unavailable_token})
                    yield _result_event("SERVICE_UNAVAILABLE", category, service, subservice)
                    turn_classification = {
                        "type": "SERVICE_UNAVAILABLE",
                        "category": category,
                        "service": service,
                        "subservice": subservice,
                    }
                    logger.info(json.dumps({
                        "request_id": request_id, "type": "SERVICE_UNAVAILABLE", "token": freeze_cards_unavailable_token,
                    }))
                    audit.log_banking_turn(
                        customer_identity,
                        turn_classification,
                        latency_ms=(time.monotonic() - turn_started_at) * 1000,
                        request_id=request_id,
                    )
                else:
                    cards = cards_result.data.get("cards") if isinstance(cards_result.data, dict) else None
                    cards = cards if isinstance(cards, list) else []
                    if len(cards) == 0:
                        no_cards_token = await say_text(_say("answer", cards_on_file="none"))
                        yield _sse("token", {"token": no_cards_token})
                        yield _result_event("BANKING_SERVICE", category, service, subservice, payload={"cards": []})
                        turn_classification = {
                            "type": "BANKING_SERVICE",
                            "category": category,
                            "service": service,
                            "subservice": subservice,
                        }
                        logger.info(json.dumps({
                            "request_id": request_id, "type": "BANKING_SERVICE", "token": no_cards_token,
                        }))
                        audit.log_banking_turn(
                            customer_identity,
                            turn_classification,
                            latency_ms=(time.monotonic() - turn_started_at) * 1000,
                            request_id=request_id,
                        )
                    elif len(cards) == 1:
                        chosen_card = cards[0] if isinstance(cards[0], dict) else {}
                        payload["cardId"] = chosen_card.get("id")
                        card_number = str(chosen_card.get("cardNumber") or "")
                        if len(card_number) >= 4:
                            payload["cardLast4"] = card_number[-4:]
                    else:
                        card_selection_token = await say_text(_choose_say("which of their cards they mean", cards))
                        yield _sse("token", {"token": card_selection_token})
                        yield _result_event(
                            "ACCOUNT_SELECTION_REQUIRED", category, service, subservice, payload={"accounts": cards}
                        )
                        turn_classification = {
                            "type": "ACCOUNT_SELECTION_REQUIRED",
                            "category": category,
                            "service": service,
                            "subservice": subservice,
                            "question": card_selection_token,
                            "candidates": cards,
                            "payload": _strip_secrets(dict(payload or {})),
                        }
                        logger.info(json.dumps({
                            "request_id": request_id, "type": "ACCOUNT_SELECTION_REQUIRED", "token": card_selection_token,
                        }))
                        audit.log_banking_turn(
                            customer_identity,
                            turn_classification,
                            latency_ms=(time.monotonic() - turn_started_at) * 1000,
                            request_id=request_id,
                        )

            if (
                turn_classification is None
                and (category, service) == _BENEFICIARY_ADD_KEY
                and (payload or {}).get("accountNumber")
                and not (payload or {}).get("serviceType")
            ):
                # Polygon Bank account -> OWN_BANK with the real holder name for the
                # confirmation; otherwise OTHER_BANK, which also needs bank details.
                payload = dict(payload or {})
                try:
                    recipient = await lookup_recipient(token, payload["accountNumber"])
                except AdapterAuthError:
                    recipient_outcome = _TurnOutcome("AUTH_REQUIRED", "Please log in to continue with this request.",
                                                     category, service, subservice)
                except AdapterUnavailableError:
                    recipient_outcome = _service_unavailable(category, service, subservice)
                else:
                    recipient_outcome = None
                    if recipient:
                        payload.update(serviceType="OWN_BANK", identifierType="ACCOUNT",
                                       accountNumber=recipient["accountNumber"],
                                       accountHolderName=recipient.get("accountName"))
                    else:
                        payload["serviceType"] = "OTHER_BANK"
                if recipient_outcome is not None:
                    async for chunk in _emit_outcome(recipient_outcome, request_id, customer_identity, turn_started_at, message=composer_message, history=history):
                        yield chunk
                    turn_classification = recipient_outcome.classification()

            if turn_classification is None and customer_identity is not None:
                payload, prefill_outcome = await _prefill_from_bank(
                    customer_identity, token, category, service, subservice, payload, reply_context
                )
                if prefill_outcome is not None:
                    async for chunk in _emit_outcome(prefill_outcome, request_id, customer_identity, turn_started_at, message=composer_message, history=history):
                        yield chunk
                    turn_classification = prefill_outcome.classification()

            if turn_classification is None:
                missing_fields = _missing_payload_fields(category, service, payload)
                if missing_fields:
                    clarification_question = await say_text(
                        _ask_say(category, service, subservice, payload, missing_fields))
                    yield _sse("token", {"token": clarification_question})
                    yield _result_event("CLARIFICATION_REQUIRED", None, None, None)
                    turn_classification = {
                        "type": "CLARIFICATION_REQUIRED",
                        "category": category,
                        "service": service,
                        "subservice": subservice,
                        "payload": payload,
                        "question": clarification_question,
                        "missingFields": missing_fields,
                    }
                    logger.info(json.dumps({
                        "request_id": request_id,
                        "type": "CLARIFICATION_REQUIRED",
                        "token": clarification_question,
                    }))
                    audit.log_banking_turn(
                        customer_identity,
                        turn_classification,
                        latency_ms=(time.monotonic() - turn_started_at) * 1000,
                        request_id=request_id,
                    )
                elif category == "transfer" and service in ("bank_transfer", "wallet_transfer"):
                    # T-56: never execute a transfer (ADR-0008 / the standing GET-only
                    # policy) -- no adapter call here at all, just a deterministic
                    # confirmation summary once every required field is known. The
                    # customer completes the actual transfer in the app via
                    # routing.action, same pattern as BENEFICIARY_MATCH's redirect.
                    collected_payload = dict(payload or {})
                    collected_payload["formattedAmount"] = _format_bdt(collected_payload.get("amount"))
                    collected_payload["executed"] = False
                    transfer_summary_token = await say_text(_transfer_summary_say(service, subservice, payload or {}))
                    yield _sse("token", {"token": transfer_summary_token})
                    routing_action = f"{subservice}_transfer"
                    yield _result_event(
                        "BANKING_SERVICE",
                        category,
                        service,
                        subservice,
                        payload=_strip_secrets(collected_payload),
                        routing={
                            "category": category,
                            "service": service,
                            "subservice": subservice,
                            "action": routing_action,
                        },
                    )
                    turn_classification = {
                        "type": "BANKING_SERVICE",
                        "category": category,
                        "service": service,
                        "subservice": subservice,
                    }
                    logger.info(json.dumps({
                        "request_id": request_id,
                        "type": "BANKING_SERVICE",
                        "token": transfer_summary_token,
                        "payload": _redact_secrets(collected_payload),
                    }, default=str))
                    audit.log_banking_turn(
                        customer_identity,
                        turn_classification,
                        latency_ms=(time.monotonic() - turn_started_at) * 1000,
                        request_id=request_id,
                    )
                elif category == "service_requests" and service == "raise_dispute":
                    # T-61: same no-adapter-call pattern as T-56's transfer branch above --
                    # raise a dispute is never submitted here (POST service-request/v1/disputes
                    # is never called), just a deterministic confirmation summary once every
                    # gathered field is known. Covers ATM_SUPPORT 2.2, CARD_ISSUE 3.3, and
                    # FAILED_TRANSFER 8.2 -- identical contract, one implementation.
                    collected_payload = dict(payload or {})
                    collected_payload["executed"] = False
                    dispute_summary_token = await say_text(_dispute_summary_say(payload or {}))
                    yield _sse("token", {"token": dispute_summary_token})
                    yield _result_event(
                        "BANKING_SERVICE",
                        category,
                        service,
                        subservice,
                        payload=_strip_secrets(collected_payload),
                        routing={
                            "category": category,
                            "service": service,
                            "subservice": subservice,
                            "action": "raise_dispute",
                        },
                    )
                    turn_classification = {
                        "type": "BANKING_SERVICE",
                        "category": category,
                        "service": service,
                        "subservice": subservice,
                    }
                    logger.info(json.dumps({
                        "request_id": request_id,
                        "type": "BANKING_SERVICE",
                        "token": dispute_summary_token,
                        "payload": _redact_secrets(collected_payload),
                    }, default=str))
                    audit.log_banking_turn(
                        customer_identity,
                        turn_classification,
                        latency_ms=(time.monotonic() - turn_started_at) * 1000,
                        request_id=request_id,
                    )
                elif category == ui_actions.CATEGORY and ui_actions.get(service) is not None:
                    app_outcome = _ui_action_outcome(ui_actions.get(service), payload, req.message)
                    async for chunk in _emit_outcome(app_outcome, request_id, customer_identity, turn_started_at, message=composer_message, history=history):
                        yield chunk
                    turn_classification = app_outcome.classification()
                elif (category, service) in (_REPORT_LOST_KEY, _PHOTO_KEY) or (category, service) in _CONTACT_KEYS:
                    # T-75: report lost card / profile photo = redirect only (no bank
                    # call); email/mobile = OTP first. Fixed wording (caution / security).
                    if (category, service) == _REPORT_LOST_KEY:
                        change_outcome = _report_lost_card_outcome(category, service, subservice, payload)
                    elif (category, service) == _PHOTO_KEY:
                        change_outcome = _profile_photo_outcome(category, service, subservice)
                    else:
                        change_outcome = await _send_contact_otp(customer_identity, category, service, payload)
                    async for chunk in _emit_outcome(change_outcome, request_id, customer_identity, turn_started_at, message=composer_message, history=history):
                        yield chunk
                    turn_classification = change_outcome.classification()
                elif (category, service) in _CONFIRM_CHANGE_KEYS or (category, service) == _FREEZE_KEY:
                    # T-57/T-60: this chatbot's first-ever mutating platform calls --
                    # never executed here. Only an explicit, deterministic "yes" on the
                    # customer's NEXT turn (see the pending_confirmation branch near the
                    # top of this function) triggers the actual fulfill_banking_service
                    # call; nothing below this point calls the real adapter.
                    # Composed; the exact values that will be saved are validated in it.
                    confirmation_question = await say_text(_confirm_say((category, service), payload))
                    yield _sse("token", {"token": confirmation_question})
                    yield _result_event(
                        "CONFIRMATION_REQUIRED", category, service, subservice, payload=_strip_secrets(payload)
                    )
                    turn_classification = {
                        "type": "CONFIRMATION_REQUIRED",
                        "category": category,
                        "service": service,
                        "subservice": subservice,
                        "payload": payload,
                        "question": confirmation_question,
                    }
                    logger.info(json.dumps({
                        "request_id": request_id,
                        "type": "CONFIRMATION_REQUIRED",
                        "token": confirmation_question,
                    }))
                    audit.log_banking_turn(
                        customer_identity,
                        turn_classification,
                        latency_ms=(time.monotonic() - turn_started_at) * 1000,
                        request_id=request_id,
                    )
                else:
                    try:
                        adapter_result = await fulfill_banking_service(
                            customer_identity, token, category, service, subservice, payload
                        )
                    except AdapterAuthError:
                        adapter_auth_error_token = await say_text(_say("login_needed", request=_service_name(category, service)))
                        yield _sse("token", {"token": adapter_auth_error_token})
                        yield _result_event("AUTH_REQUIRED", category, service, subservice)
                        turn_classification = {
                            "type": "AUTH_REQUIRED",
                            "category": category,
                            "service": service,
                            "subservice": subservice,
                        }
                        logger.info(json.dumps({"request_id": request_id, "type": "AUTH_REQUIRED", "token": adapter_auth_error_token}))
                        audit.log_banking_turn(
                            customer_identity,
                            turn_classification,
                            latency_ms=(time.monotonic() - turn_started_at) * 1000,
                            request_id=request_id,
                        )
                    except AdapterAccountSelectionRequiredError as exc:
                        account_selection_token = await say_text(_choose_say("which of their accounts they mean", exc.accounts))
                        yield _sse("token", {"token": account_selection_token})
                        yield _result_event(
                            "ACCOUNT_SELECTION_REQUIRED", category, service, subservice, payload={"accounts": exc.accounts}
                        )
                        turn_classification = {
                            "type": "ACCOUNT_SELECTION_REQUIRED",
                            "category": category,
                            "service": service,
                            "subservice": subservice,
                            "question": account_selection_token,
                            "candidates": exc.accounts,
                            "payload": _strip_secrets(dict(payload or {})),
                        }
                        logger.info(json.dumps({
                            "request_id": request_id,
                            "type": "ACCOUNT_SELECTION_REQUIRED",
                            "token": account_selection_token,
                        }))
                        audit.log_banking_turn(
                            customer_identity,
                            turn_classification,
                            latency_ms=(time.monotonic() - turn_started_at) * 1000,
                            request_id=request_id,
                        )
                    except AdapterUnavailableError:
                        service_unavailable_token = await say_text(_say("unavailable", service=_service_name(category, service)))
                        yield _sse("token", {"token": service_unavailable_token})
                        yield _result_event("SERVICE_UNAVAILABLE", category, service, subservice)
                        turn_classification = {
                            "type": "SERVICE_UNAVAILABLE",
                            "category": category,
                            "service": service,
                            "subservice": subservice,
                        }
                        logger.info(json.dumps({
                            "request_id": request_id,
                            "type": "SERVICE_UNAVAILABLE",
                            "token": service_unavailable_token,
                        }))
                        audit.log_banking_turn(
                            customer_identity,
                            turn_classification,
                            latency_ms=(time.monotonic() - turn_started_at) * 1000,
                            request_id=request_id,
                        )
                    else:
                        data = adapter_result.data
                        if (
                            service == "beneficiary"
                            and isinstance(payload, dict)
                            and (payload.get("nameQuery") or payload.get("beneficiaryId"))
                        ):
                            beneficiaries_raw = data.get("beneficiaries") if isinstance(data, dict) else None
                            beneficiaries = beneficiaries_raw if isinstance(beneficiaries_raw, list) else []

                            beneficiary_id = payload.get("beneficiaryId")
                            if beneficiary_id is not None:
                                matches = [
                                    b for b in beneficiaries
                                    if isinstance(b, dict) and b.get("id") == beneficiary_id
                                ]
                            else:
                                matches = _match_beneficiaries(payload.get("nameQuery", ""), beneficiaries)

                            if len(matches) == 0:
                                beneficiary_reply_token = await say_text(_say(
                                    "ask", {"name searched": payload.get("nameQuery")},
                                    problem="no saved beneficiary has that name",
                                    options=["check the name", "send to a new account or wallet instead"]))
                                yield _sse("token", {"token": beneficiary_reply_token})
                                yield _result_event("CLARIFICATION_REQUIRED", None, None, None)
                                turn_classification = {
                                    "type": "CLARIFICATION_REQUIRED",
                                    "category": None,
                                    "service": None,
                                    "subservice": None,
                                    "question": beneficiary_reply_token,
                                }
                            elif len(matches) == 1:
                                matched = matches[0]
                                destination = _resolve_beneficiary_destination(matched)
                                beneficiary_reply_token = await say_text(_say(
                                    "redirect", {"beneficiary": _beneficiary_name(matched)},
                                    screen=("the matching transfer screen in the app, pre-filled" if destination
                                            else "the beneficiary list in the app (this type can't be opened automatically)"),
                                    done_in_chat="no; they confirm the amount and send it in the app"))
                                yield _sse("token", {"token": beneficiary_reply_token})
                                routing_action = destination["action"] if destination else "manual"
                                yield _result_event(
                                    "BENEFICIARY_MATCH",
                                    category,
                                    service,
                                    subservice,
                                    payload={"beneficiary": matched, "destination": destination},
                                    routing={
                                        "category": category,
                                        "service": service,
                                        "subservice": subservice,
                                        "action": routing_action,
                                    },
                                )
                                turn_classification = {
                                    "type": "BENEFICIARY_MATCH",
                                    "category": category,
                                    "service": service,
                                    "subservice": subservice,
                                }
                            else:
                                beneficiary_reply_token = await say_text(_say(
                                    "choose", question_about="which saved beneficiary they mean",
                                    options=[_beneficiary_name(b) for b in matches]))
                                yield _sse("token", {"token": beneficiary_reply_token})
                                yield _result_event(
                                    "BENEFICIARY_SELECTION_REQUIRED",
                                    category,
                                    service,
                                    subservice,
                                    payload={"beneficiaries": [_trim_beneficiary(b) for b in matches]},
                                )
                                turn_classification = {
                                    "type": "BENEFICIARY_SELECTION_REQUIRED",
                                    "category": category,
                                    "service": service,
                                    "subservice": subservice,
                                }

                            logger.info(json.dumps({
                                "request_id": request_id,
                                "type": turn_classification["type"],
                                "token": beneficiary_reply_token,
                            }))
                            audit.log_banking_turn(
                                customer_identity,
                                turn_classification,
                                latency_ms=(time.monotonic() - turn_started_at) * 1000,
                                request_id=request_id,
                            )
                        else:
                            if data.get("mock") is True:
                                banking_service_token = await say_text(_say(
                                    "unavailable", service=_service_name(category, service),
                                    status="not connected to the chat yet"))
                            else:
                                data = _enrich_payload(service, subservice, data)
                                banking_service_token = ""
                                async for piece in _stream_reply(reply_context, service, subservice, data):
                                    banking_service_token += piece
                                    yield _sse("token", {"token": piece})
                            if data.get("mock") is True:
                                yield _sse("token", {"token": banking_service_token})
                            yield _result_event(
                                "BANKING_SERVICE",
                                category,
                                service,
                                subservice,
                                payload=data,
                                routing=_service_routing(category, service, subservice, payload),
                            )
                            turn_classification = {
                                "type": "BANKING_SERVICE",
                                "category": category,
                                "service": service,
                                "subservice": subservice,
                            }
                            logger.info(json.dumps({
                                "request_id": request_id,
                                "type": "BANKING_SERVICE",
                                "token": banking_service_token,
                                "payload": _redact_secrets(data),
                            }, default=str))
                            audit.log_banking_turn(
                                customer_identity,
                                turn_classification,
                                latency_ms=(time.monotonic() - turn_started_at) * 1000,
                                request_id=request_id,
                            )

    yield _sse("done", {})

    if customer_identity is not None:
        if (isinstance(turn_classification, dict)
                and turn_classification.get("type") == "BANKING_SERVICE"
                and isinstance(result, BankingService)
                and (result.category, result.service) not in _NO_FOLLOW_UP_KEYS):
            # What the customer asked for (never bank data), so a follow-up can reuse it.
            turn_classification = {**turn_classification, "request": _strip_secrets(dict(result.payload or {}))}
        record_turn(
            customer_identity.customer_id,
            ChatTurn(
                timestamp=datetime.now(timezone.utc),
                message=stored_message,
                classification=_session_safe_classification(turn_classification),
            ),
        )


@router.post("")
async def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
    return StreamingResponse(_chat_stream(req, authorization), media_type="text/event-stream")
