import copy
import difflib
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

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
    AdapterUnavailableError,
    AdapterValidationError,
)
from app.banking.identity import extract_jwt, verify_jwt
from app.banking.routing import (
    BankingService,
    Clarification,
    KbQuestion,
    UnknownService,
    classify,
    fee_transaction_types,
    _CLARIFICATION_FALLBACK,
)
from app.banking.session import ChatTurn, get_classification_context, get_session, record_turn
from app.banking.taxonomy import is_valid_path
from app.config import settings
from app.embeddings import embed_text
from app.llm import build_prompt, stream_generate
from app.vectorstore import search

try:
    # T-57: real OTP send/verify, owned by the parallel banking-service-integration
    # dispatch (see app/banking/adapters/real.py's own send_otp()/verify_otp()
    # docstrings for the full status-code contract). Imported here, rather than
    # called via fulfill_banking_service/adapter_map, because these two calls are
    # deliberately unauthenticated/un-routed platform endpoints, not a taxonomy
    # (category, service, subservice) triple -- there is no adapter_map entry for
    # them and there never should be one.
    from app.banking.adapters.real import send_otp, verify_otp
except ImportError:  # pragma: no cover - only during the brief window before that
    # dispatch lands; keeps this module importable (so every *other* chat.py test
    # keeps passing) instead of crashing the whole router. Once hit, any real
    # freeze-OTP attempt below surfaces as a clean SERVICE_UNAVAILABLE rather than
    # a 500 -- never a silent fake success.
    async def send_otp(phone: str) -> None:
        raise AdapterUnavailableError("OTP send is not available yet")

    async def verify_otp(phone: str, otp: str) -> str:
        raise AdapterUnavailableError("OTP verification is not available yet")

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
}


def _missing_payload_fields(category: str, service: str, payload: dict | None) -> list[str]:
    """Returns the required fields (per _REQUIRED_PAYLOAD_FIELDS) missing or falsy from
    `payload` for this (category, service) pair. Empty list if this pair has no required
    fields, or if all required fields are present. `payload=None` is treated as `{}`."""
    required = _REQUIRED_PAYLOAD_FIELDS.get((category, service))
    if not required:
        return []
    payload = payload or {}
    return [field for field in required if not payload.get(field)]


def _fee_quote_clarification_question(payload: dict | None, subservice: str | None = None) -> str:
    """Customer-friendly clarifying question for an incomplete fees/fee_quote payload,
    mirroring the tone/wording of the fee_quote few-shot examples in
    app/banking/routing.py's build_system_prompt() so this code-level guard's question is
    indistinguishable in style from one the classifier itself would ask."""
    payload = payload or {}
    transaction_type = payload.get("transactionType")
    amount = payload.get("amount")

    if transaction_type and not amount:
        friendly_type = str(transaction_type).replace("_", " ")
        return (
            f"Sure — how much would you like to send via {friendly_type}? I can give you "
            "the exact fee once I know the amount."
        )
    if amount and not transaction_type:
        amount_formatted = _format_bdt(amount) or str(amount)
        return (
            f"Sure — you'd like a fee quote for {amount_formatted}. Which transaction type "
            "would you like that for? For example, a bank transfer, bKash, or another wallet?"
        )
    return (
        "Sure — which transaction type would you like a fee quote for, and for what "
        "amount? For example, a bank transfer, bKash, or another wallet?"
    )


# T-56: transfer/bank_transfer and transfer/wallet_transfer subservice ->
# customer-facing display name maps, shared by both the clarification-question
# builders below and the no-adapter confirmation summary built once the
# payload is complete (see _transfer_summary_reply in _chat_stream).
_BANK_TRANSFER_SUBSERVICE_NAMES: dict[str, str] = {
    "own_account": "Own Account Transfer",
    "city_account": "City Account Transfer",
    "other_bank": "Other Bank Transfer",
}

_WALLET_PROVIDER_NAMES: dict[str, str] = {
    "bkash": "bKash",
    "nagad": "Nagad",
    "rocket": "Rocket",
    "upay": "Upay",
}


def _bank_transfer_display_name(subservice: str | None) -> str:
    return _BANK_TRANSFER_SUBSERVICE_NAMES.get(subservice or "", "Bank Transfer")


def _wallet_provider_display_name(subservice: str | None) -> str:
    return _WALLET_PROVIDER_NAMES.get(subservice or "", (subservice or "wallet").replace("_", " ").title())


def _bank_transfer_clarification_question(payload: dict | None, subservice: str | None = None) -> str:
    """Clarifying question for an incomplete transfer/bank_transfer payload
    (own_account/city_account/other_bank), mirroring _fee_quote_clarification_question's
    style: names back whichever of accountNumber/amount is already known, or the
    subservice itself if both are still missing."""
    payload = payload or {}
    account_number = payload.get("accountNumber")
    amount = payload.get("amount")

    if account_number and not amount:
        return f"Sure — how much would you like to send to account {account_number}?"
    if amount and not account_number:
        amount_formatted = _format_bdt(amount) or str(amount)
        return f"Sure — which account number would you like to send {amount_formatted} to?"
    transfer_name = _bank_transfer_display_name(subservice)
    return (
        f"Sure — which account number would you like to send money to via {transfer_name}, "
        "and how much?"
    )


def _wallet_transfer_clarification_question(payload: dict | None, subservice: str | None = None) -> str:
    """Clarifying question for an incomplete transfer/wallet_transfer payload
    (bkash/nagad/rocket/upay), mirroring _bank_transfer_clarification_question."""
    payload = payload or {}
    wallet_number = payload.get("walletNumber")
    amount = payload.get("amount")
    provider_name = _wallet_provider_display_name(subservice)

    if wallet_number and not amount:
        return f"Sure — how much would you like to send to your {provider_name} number {wallet_number}?"
    if amount and not wallet_number:
        amount_formatted = _format_bdt(amount) or str(amount)
        return f"Sure — which {provider_name} number would you like to send {amount_formatted} to?"
    return f"Sure — to which {provider_name} number would you like to send money, and how much?"


def _freeze_card_reason_clarification_question(payload: dict | None, subservice: str | None = None) -> str:
    """Clarifying question for a card-freeze request that's missing a reason.
    Free-text, deliberately not a fixed enum -- the real FreezeCardRequest's
    own `reasonCode` enum only has one value ("OTHER") today, so there's
    nothing meaningful to offer as choices; the adapter sends "OTHER"
    regardless (see FreezeCardAdapter's docstring) and this free-text reason
    is for the customer-facing confirmation/audit trail only."""
    payload = payload or {}
    card_last4 = payload.get("cardLast4")
    card_ref = f"card ending {card_last4}" if card_last4 else "card"
    return f"Sure — what's the reason for freezing this {card_ref}?"


def _beneficiary_add_clarification_question(payload: dict | None, subservice: str | None = None) -> str:
    """Clarifying question for an incomplete beneficiary-add payload, mirroring
    _bank_transfer_clarification_question's style: names back whichever of
    nickname/accountNumber is already known."""
    payload = payload or {}
    nickname = payload.get("nickname")
    account_number = payload.get("accountNumber")

    if nickname and not account_number:
        return f"Sure — what's the account number for {nickname}?"
    if account_number and not nickname:
        return "Sure — what name would you like to save this beneficiary under?"
    return (
        "Sure — what name would you like to save this beneficiary under, and what's their "
        "account number?"
    )


def _dispute_clarification_question(payload: dict | None, subservice: str | None = None) -> str:
    """Clarifying question for an incomplete service_requests/raise_dispute payload.
    Mirrors the naming-back style of the other builders above, extended to this flow's
    three gatherable fields (accountNumber, transactionReferenceNo, remarks) -- names back
    whichever are already known, and asks only for whatever's still missing."""
    payload = payload or {}
    account_number = payload.get("accountNumber")
    transaction_ref = payload.get("transactionReferenceNo")
    remarks = payload.get("remarks")

    known_parts = []
    if account_number:
        known_parts.append(f"account {account_number}")
    if transaction_ref:
        known_parts.append(f"transaction {transaction_ref}")
    if remarks:
        known_parts.append(f"reason: {remarks}")

    missing_parts = []
    if not account_number:
        missing_parts.append("the account number")
    if not transaction_ref:
        missing_parts.append("the transaction reference number")
    if not remarks:
        missing_parts.append(
            "the reason for the dispute (for example, you were charged but didn't get the "
            "cash or service, or the amount looks wrong)"
        )

    if not missing_parts:
        return "Could you share a few more details so I can help with that?"

    if len(missing_parts) == 1:
        missing_sentence = missing_parts[0]
    elif len(missing_parts) == 2:
        missing_sentence = " and ".join(missing_parts)
    else:
        missing_sentence = ", ".join(missing_parts[:-1]) + f", and {missing_parts[-1]}"

    if known_parts:
        return f"Sure — I have {', '.join(known_parts)}. Could you also share {missing_sentence}?"
    return f"Sure — to raise a dispute, could you share {missing_sentence}?"


_PAYLOAD_CLARIFICATION_BUILDERS: dict[tuple[str, str], Callable[[dict | None, str | None], str]] = {
    ("fees", "fee_quote"): _fee_quote_clarification_question,
    ("transfer", "bank_transfer"): _bank_transfer_clarification_question,
    ("transfer", "wallet_transfer"): _wallet_transfer_clarification_question,
    ("card_services", "frezz_unfrezz"): _freeze_card_reason_clarification_question,
    ("beneficiary_management", "beneficiary_add"): _beneficiary_add_clarification_question,
    ("service_requests", "raise_dispute"): _dispute_clarification_question,
}


def _payload_clarification_question(
    category: str, service: str, payload: dict | None, subservice: str | None = None
) -> str:
    """Deterministic template wording -- FALLBACK ONLY since the generated-wording
    change (see _generate_clarification_question below). Still the sole source of
    truth for nothing but phrasing: *which* fields are missing is always decided by
    _missing_payload_fields, never by either of these."""
    builder = _PAYLOAD_CLARIFICATION_BUILDERS.get((category, service))
    if builder:
        return builder(payload, subservice)
    return "Could you share a few more details so I can help with that?"


# Generated (LLM-worded) missing-field clarifications. User requirement: clarifying
# questions must not be identical fixed boilerplate every time. Only the *wording* is
# generated -- _missing_payload_fields still decides deterministically which fields are
# missing, and that list is handed to the model as a fixed instruction. Security
# confirmations (freeze OTP prompt, beneficiary-add yes/no) are deliberately NOT
# generated -- they stay fixed text.
def _clarification_service_description(category: str, service: str, subservice: str | None) -> str:
    key = (category, service)
    if key == ("fees", "fee_quote"):
        return "getting a quote for the fee charged on a money transfer"
    if key == ("transfer", "bank_transfer"):
        return f"sending money to a bank account ({_bank_transfer_display_name(subservice)})"
    if key == ("transfer", "wallet_transfer"):
        return f"sending money to a {_wallet_provider_display_name(subservice)} mobile wallet"
    if key == ("card_services", "frezz_unfrezz"):
        return "freezing (temporarily blocking) one of their bank cards"
    if key == ("beneficiary_management", "beneficiary_add"):
        return "saving another bank account as a beneficiary for future transfers"
    if key == ("service_requests", "raise_dispute"):
        return "raising a dispute about a problem with a transaction"
    return f"the {service.replace('_', ' ')} banking service"


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
        ("transactionReferenceNo", "transaction reference"),
        ("reason", "reason"),
        ("remarks", "dispute reason"),
    ):
        value = payload.get(field)
        if value:
            phrases.append(f"{label}: {_DIGIT_RUN_RE.sub(_mask_digit_run, str(value))[:200]}")
    return phrases


_FORBIDDEN_CLARIFICATION_RE = re.compile(
    r"\b(pin|password|passcode|otp|one[- ]time)\b", re.IGNORECASE
)
# Template/placeholder artifacts ("XXXX", "[amount]", "<number>", "{x}") -- seen live.
_PLACEHOLDER_RE = re.compile(r"[xX]{3,}|[\[\]<>{}]")


def _clean_generated_question(text: str) -> str | None:
    """Post-checks a generated question. Returns None (-> caller falls back to the
    template) if it's empty, implausibly long, or mentions PIN/password/OTP; also
    strips wrapping quotes/markdown and masks any 6+ digit run it may have echoed."""
    text = (text or "").strip().strip('"').strip("'").strip()
    text = re.sub(r"[*_`#]+", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    if not text or len(text) > 400:
        return None
    if _FORBIDDEN_CLARIFICATION_RE.search(text) or _PLACEHOLDER_RE.search(text):
        return None
    return _DIGIT_RUN_RE.sub(_mask_digit_run, text)


async def _generate_clarification_question(
    message: str,
    category: str,
    service: str,
    subservice: str | None,
    payload: dict | None,
    missing_fields: list[str],
) -> str | None:
    """One short Ollama /api/generate call wording a missing-field clarification
    naturally. Returns None on ANY failure (timeout, HTTP error, empty/unsafe output)
    so the caller falls back to the deterministic template. Never raises."""
    try:
        missing = [
            _CLARIFICATION_FIELD_DESCRIPTIONS.get(f, f.replace("_", " ")) for f in missing_fields
        ]
        if service == "wallet_transfer" and "walletNumber" in missing_fields:
            provider = _wallet_provider_display_name(subservice)
            missing = [
                f"the {provider} number to send to" if f == "walletNumber" else desc
                for f, desc in zip(missing_fields, missing)
            ]
        known = _known_field_phrases(payload)
        safe_message = _DIGIT_RUN_RE.sub(_mask_digit_run, message)[:500]
        prompt = (
            "You are a friendly banking assistant chatting with a customer.\n"
            f"The customer said: \"{safe_message}\"\n"
            f"They want help with: {_clarification_service_description(category, service, subservice)}.\n"
            f"Details already known: {'; '.join(known) if known else 'none yet'}.\n"
            f"Details still needed: {'; '.join(missing)}.\n\n"
            "Write the next message to the customer, in English: one or two short, natural, "
            "conversational sentences that ask ONLY for the details still needed. You may "
            "briefly name back known details exactly as written above (an account or wallet "
            "number only in the \"ending\" form shown). Do not guess or suggest values, never "
            "use placeholders, do not ask for anything else or for details already known, "
            "never ask for a PIN, password, OTP or any code, do not invent fees or facts, no "
            "greeting, no markdown, no quotes. Output only the message."
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.3},
                },
            )
            resp.raise_for_status()
            result = resp.json()
        return _clean_generated_question(result.get("response") or "")
    except Exception:
        return None


# Numbers, taka amounts and card/account endings a reworded reply must keep verbatim.
_PHRASE_FACT_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _number_keeps_its_label(number: str, facts: str, text: str) -> bool:
    """Every place `number` follows a word in the facts ("ending 0293", "Tk 500.00"),
    the rewording must keep that word right before it at least once."""
    labels = set(re.findall(r"(\w+)\W{1,2}" + re.escape(number), facts))
    return all(re.search(re.escape(label) + r"\W{1,2}" + re.escape(number), text, re.IGNORECASE) for label in labels)


async def _phrase(facts: str, customer_message: str) -> str:
    """Code decides WHAT to tell the customer (`facts`); the model decides HOW to
    say it for this customer's message, tone and language. Every number, amount and
    card/account ending in `facts` must appear verbatim in the reworded reply, and no
    foreign currency may appear -- otherwise `facts` is sent as-is. Tests patch this
    to identity (tests/conftest.py)."""
    if not facts:
        return facts
    facts = facts.replace("৳", "Tk ")
    required = [f for f in _PHRASE_FACT_RE.findall(facts) if len(re.sub(r"\D", "", f)) >= 3]
    prompt = (
        "You are Polygon Bank's chat assistant. A customer wrote:\n"
        f"\"{_DIGIT_RUN_RE.sub(_mask_digit_run, customer_message)}\"\n\n"
        "Tell them exactly the following, in your own natural words:\n"
        f"{facts}\n\n"
        "Rules: keep every number, amount, name and card/account ending exactly as written "
        "above, each attached to the same thing it describes (never move a card ending onto "
        "a phone number, or the like). Keep every warning and every option the customer is "
        "given (such as how to cancel). Add no facts, steps, promises or offers that aren't "
        "in it. Reply in English (simple English if the customer wrote Banglish). One to "
        "four short sentences, plain text, no markdown, no greeting."
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.4},
                },
            )
            resp.raise_for_status()
            text = (resp.json().get("response") or "").strip().strip('"')
    except Exception:
        return facts
    if (
        not text
        or len(text) > 600
        # Much longer than the facts means it added something (seen live: invented
        # "contact the number on your statement", "refer to your welcome email").
        or len(text) > len(facts) * 1.5 + 40
        or "$" in text
        or any(fact not in text for fact in required)
        # A number repeated beyond the facts, or moved away from the word it follows
        # in the facts, got attached to something else (seen live: "your registered
        # phone number 0293" for a card ending 0293).
        or any(text.count(fact) > facts.count(fact) for fact in required)
        or any(not _number_keeps_its_label(fact, facts, text) for fact in required)
    ):
        return facts
    return text


async def _clarification_question_for(
    message: str,
    category: str,
    service: str,
    subservice: str | None,
    payload: dict | None,
    missing_fields: list[str],
) -> str:
    generated = await _generate_clarification_question(
        message, category, service, subservice, payload, missing_fields
    )
    if generated:
        return generated
    return _payload_clarification_question(category, service, payload, subservice)


# T-57/T-60: deterministic, code-level re-confirmation gate for this chatbot's first
# two ever mutating platform calls (freeze a card / add a beneficiary). Same philosophy
# as T-49/T-55's deterministic payload-completion guard above: an LLM judgment call on
# "did the customer actually confirm?" is not an acceptable risk for a mutating action --
# T-55's own module notes document a severity-1 regression from LLM-based pending-state
# interpretation elsewhere in this file. A small, literal, enumerated phrase set (never
# fuzzy/substring matching) decides yes/no/unclear; "unclear" always re-asks rather than
# ever guessing in either direction.
_AFFIRMATIVE_CONFIRMATION_REPLIES = {"yes", "confirm", "confirmed", "do it", "go ahead", "yes please"}
_NEGATIVE_CONFIRMATION_REPLIES = {"no", "cancel", "nevermind", "never mind", "stop"}


def _classify_confirmation_reply(message: str) -> str:
    """Returns "affirmative", "negative", or "unclear" for a reply to a pending
    CONFIRMATION_REQUIRED turn. Only exact (case-insensitive, trailing-punctuation-
    insensitive) matches against the two phrase sets above resolve either way --
    anything else, including a plausible-sounding variant not in either set, is
    "unclear" so the caller re-asks instead of guessing."""
    normalized = re.sub(r"[.!?]+$", "", message.strip().lower()).strip()
    if normalized in _AFFIRMATIVE_CONFIRMATION_REPLIES:
        return "affirmative"
    if normalized in _NEGATIVE_CONFIRMATION_REPLIES:
        return "negative"
    return "unclear"


def _beneficiary_add_confirmation_question(payload: dict | None) -> str:
    payload = payload or {}
    nickname = payload.get("nickname")
    account_number = str(payload.get("accountNumber") or "")
    account_ref = f"ending {account_number[-4:]}" if account_number else "that account"
    return (
        f"You're about to add {nickname} as a beneficiary with account number {account_ref}. "
        "Shall I proceed? (yes/no)"
    )


def _freeze_card_success_message(payload: dict | None) -> str:
    card_last4 = (payload or {}).get("cardLast4")
    if card_last4:
        return f"Done — your card ending {card_last4} has been frozen."
    return "Done — your card has been frozen."


def _beneficiary_add_success_message(payload: dict | None) -> str:
    nickname = (payload or {}).get("nickname") or "that beneficiary"
    return f"Done — {nickname} has been added as a beneficiary."


# Keyed by (category, service) -- the exact pair driving the generic BankingService
# branch below into the confirmation step instead of the normal immediate-adapter-call
# path. Adding a future mutating exception is a one-line addition to each of these 3
# dicts (plus _REQUIRED_PAYLOAD_FIELDS/_PAYLOAD_CLARIFICATION_BUILDERS above for its
# gather step), never new branching logic in _chat_stream itself.
#
# Card freeze is deliberately NOT in _CONFIRMATION_QUESTION_BUILDERS any more: its
# confirmation step is the bank's own OTP + PIN/password step-up (see the T-57 OTP
# section below), not a plain yes/no. Only (category, service) pairs listed here are
# ever treated as a pending yes/no confirmation.
_CONFIRMATION_QUESTION_BUILDERS: dict[tuple[str, str], Callable[[dict | None], str]] = {
    ("beneficiary_management", "beneficiary_add"): _beneficiary_add_confirmation_question,
}

_CONFIRMATION_DECLINE_MESSAGES: dict[tuple[str, str], str] = {
    ("card_services", "frezz_unfrezz"): "Okay, I won't freeze your card.",
    ("beneficiary_management", "beneficiary_add"): "Okay, I won't add that beneficiary.",
}

_CONFIRMATION_SUCCESS_MESSAGES: dict[tuple[str, str], Callable[[dict | None], str]] = {
    ("card_services", "frezz_unfrezz"): _freeze_card_success_message,
    ("beneficiary_management", "beneficiary_add"): _beneficiary_add_success_message,
}


# T-57: OTP + PIN/password step-up for card freeze. Flow, all deterministic (no LLM
# ever sees any of this): card + reason gathered -> send_otp(phone from the
# customer's own verified JWT identity, NEVER from request input) -> OTP_REQUIRED
# pending state -> the customer's next request carries `payload.otp` + exactly one of
# `payload.pin`/`payload.password` (structured fields only -- never parsed from
# message text) -> verify_otp -> FreezeCardAdapter (reasonCode=OTHER). pin/password/
# otp are never logged, never persisted in session state, never echoed in a result.
_FREEZE_KEY = ("card_services", "frezz_unfrezz")
_OTP_PENDING_TYPE = "OTP_REQUIRED"


class _TurnOutcome:
    """One fully-decided turn outcome from the freeze-OTP helpers below; the caller
    emits token + result, logs, audits and records it uniformly."""

    def __init__(
        self,
        result_type: str,
        token: str,
        category: str | None,
        service: str | None,
        subservice: str | None,
        *,
        result_payload: dict | None = None,
        routing: dict | None = None,
        stored: dict | None = None,
    ):
        self.result_type = result_type
        self.token = token
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


def _freeze_card_ref(payload: dict | None) -> str:
    card_last4 = (payload or {}).get("cardLast4")
    return f"card ending {card_last4}" if card_last4 else "card"


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
    question: str,
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
    stored = {"payload": public_payload, "question": question}
    if verification_token:
        stored["verificationToken"] = verification_token
    return _TurnOutcome(
        _OTP_PENDING_TYPE, question, category, service, subservice,
        result_payload=result_payload, stored=stored,
    )


def _freeze_not_executed(
    category: str, service: str, subservice: str | None, token: str, status: str
) -> _TurnOutcome:
    """Terminal, nothing-was-frozen outcome (flow ends; the next message is a fresh
    request)."""
    return _TurnOutcome(
        "BANKING_SERVICE", token, category, service, subservice,
        result_payload={"executed": False, "verificationStatus": status},
    )


def _service_unavailable(category, service, subservice) -> _TurnOutcome:
    return _TurnOutcome(
        "SERVICE_UNAVAILABLE",
        "That service isn't available right now. Please try again shortly.",
        category, service, subservice,
    )


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
                "I couldn't send you a verification code right now because too many codes "
                "were requested recently. Please wait a few minutes, then ask me to freeze "
                "your card again. Your card has not been frozen.",
                "SEND_THROTTLED",
            )
        return _service_unavailable(category, service, subservice)
    except AdapterUnavailableError:
        return _service_unavailable(category, service, subservice)

    reason = (payload or {}).get("reason")
    reason_part = f" (reason: {reason})" if reason else ""
    question = (
        f"{lead + ' ' if lead else ''}I've sent a one-time code to your registered phone "
        f"number. To freeze your {_freeze_card_ref(payload)}{reason_part}, please enter that "
        "code together with either your card PIN or your login password. Freezing will "
        "block all transactions on this card until you unfreeze it. Say \"cancel\" if you "
        "don't want to go ahead."
    )
    return _freeze_otp_pending(
        category, service, subservice, payload, question,
        status="OTP_RESENT" if lead else "OTP_SENT",
    )


async def _handle_freeze_otp_reply(
    customer_identity, jwt: str | None, pending: dict, message: str, submitted: dict | None
) -> _TurnOutcome:
    """Resolves the customer's reply to a pending OTP_REQUIRED freeze step. Reads
    otp/pin/password ONLY from the structured `submitted` payload -- `message` is only
    ever checked against the literal cancel phrase set, never parsed for secrets and
    never sent to an LLM."""
    category = pending.get("category")
    service = pending.get("service")
    subservice = pending.get("subservice")
    stored_payload = dict(pending.get("payload") or {})
    stored_token = pending.get("verificationToken")
    submitted = submitted if isinstance(submitted, dict) else {}
    otp = _clean_secret(submitted.get("otp"))
    pin = _clean_secret(submitted.get("pin"))
    password = _clean_secret(submitted.get("password"))
    card_ref = _freeze_card_ref(stored_payload)

    def reask(question: str, status: str, **kw) -> _TurnOutcome:
        return _freeze_otp_pending(
            category, service, subservice, stored_payload, question, status=status,
            otp_required=kw.pop("otp_required", not stored_token),
            verification_token=kw.pop("verification_token", stored_token),
            **kw,
        )

    if not (otp or pin or password) and _classify_confirmation_reply(message) == "negative":
        return _TurnOutcome(
            "BANKING_SERVICE", _CONFIRMATION_DECLINE_MESSAGES[_FREEZE_KEY],
            category, service, subservice,
            result_payload={"executed": False, "cancelled": True},
        )

    if pin and password:
        return reask(
            f"Please provide either your card PIN or your login password to freeze your "
            f"{card_ref} — just one of them, not both.",
            "CREDENTIALS_INVALID_COMBINATION",
        )
    if not otp and not stored_token:
        return reask(
            f"To freeze your {card_ref}, please enter the one-time code we sent to your "
            "registered phone number, together with either your card PIN or your login "
            "password, in the secure verification form. Say \"cancel\" to stop.",
            "CREDENTIALS_MISSING",
        )
    if not (pin or password):
        return reask(
            f"To freeze your {card_ref}, please also enter either your card PIN or your "
            "login password along with the code.",
            "CREDENTIALS_MISSING",
        )

    verification_token = stored_token
    if otp:
        try:
            verification_token = await verify_otp(customer_identity.customer_id, otp)
        except AdapterValidationError as exc:
            if exc.reason == "OTP_INCORRECT":
                remaining = exc.attempts_remaining
                if remaining is not None:
                    attempts = f"You have {remaining} attempt{'s' if remaining != 1 else ''} left."
                else:
                    attempts = "Please check it and try again."
                return reask(
                    f"That code isn't correct. {attempts} Please re-enter the code we "
                    "already sent (no new code is needed), along with your PIN or password.",
                    "OTP_INCORRECT", otp_required=True, verification_token=None,
                    attempts_remaining=remaining,
                )
            if exc.reason == "OTP_EXPIRED":
                return await _send_freeze_otp(
                    customer_identity, category, service, subservice, stored_payload,
                    lead="That code has expired, so I've sent you a new one.",
                )
            if exc.reason == "OTP_BLOCKED":
                return _freeze_not_executed(
                    category, service, subservice,
                    "Too many incorrect codes were entered, so verification is temporarily "
                    "blocked for your number. Please wait about 5 minutes, then ask me to "
                    "freeze your card again. Your card has not been frozen.",
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
                "That PIN or password wasn't correct. Your code is still valid, so just "
                "re-enter your card PIN or your login password — no new code is needed.",
                "INVALID_CREDENTIALS", otp_required=False,
                verification_token=verification_token,
            )
        if exc.reason == "INVALID_VERIFICATION_TOKEN":
            return await _send_freeze_otp(
                customer_identity, category, service, subservice, stored_payload,
                lead="Your verification has expired, so I've sent you a new code.",
            )
        if exc.reason == "PIN_OR_PASSWORD_REQUIRED":
            return reask(
                "Please provide either your card PIN or your login password — exactly one.",
                "CREDENTIALS_INVALID_COMBINATION",
                verification_token=verification_token,
            )
        return _service_unavailable(category, service, subservice)
    except AdapterAuthError:
        return _TurnOutcome(
            "AUTH_REQUIRED", "Please log in to continue with this request.",
            category, service, subservice,
        )
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
        "BANKING_SERVICE", _freeze_card_success_message(stored_payload),
        category, service, subservice,
        result_payload=executed_data,
        routing={"category": category, "service": service, "subservice": subservice, "action": "redirect"},
    )


# T-55: deterministic completion of a still-pending T-49 payload-completeness guard,
# without re-deriving category/service/payload from scratch via classify(). Live-tested
# (llama3.1:8b) that asking the LLM to resolve a bare-amount reply like "2000 taka" to a
# clarification it JUST asked is 0/3 reliable for this structural pattern -- unlike a
# genuine ask_clarification() (real ambiguity), the T-49 guard fires when category/service
# are already known for certain and only a payload field is missing, so that certainty
# should never be thrown away and re-guessed from raw text. Only "amount" has an actual
# extractor right now; any other missing field name simply has no entry below, so
# _try_deterministic_payload_completion falls through to classify() unchanged for it --
# this is intentionally generic (keyed off the missing field's name) so a future
# required-payload service can plug in its own extractor here without new branching in
# _chat_stream.
_AMOUNT_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def _extract_single_amount(message: str) -> float | int | None:
    """Best-effort deterministic amount extraction for a bare-amount clarification
    reply (e.g. "2000", "2000 taka", "5,000 tk"). Returns the parsed number only if
    exactly one numeric substring is found in `message` -- multiple numbers make the
    reply ambiguous (which one answers the pending question?), so callers should fall
    back to the normal classify() path rather than guess. Never raises."""
    matches = _AMOUNT_RE.findall(message)
    if len(matches) != 1:
        return None
    try:
        value = float(matches[0].replace(",", ""))
    except ValueError:
        return None
    return int(value) if value.is_integer() else value


_DETERMINISTIC_FIELD_EXTRACTORS: dict[str, Callable[[str], object | None]] = {
    "amount": _extract_single_amount,
}


def _try_deterministic_payload_completion(
    recent_turns: list[ChatTurn], message: str
) -> BankingService | None:
    """If the last turn was T-49's deterministic payload-completeness guard -- a
    CLARIFICATION_REQUIRED with a known, non-null category/service/missingFields, as
    opposed to a genuinely ambiguous Clarification (which always stores
    category=None/service=None) -- attempts to resolve the still-missing payload
    field(s) directly from `message`, without calling classify() at all.

    Returns a BankingService (payload merged with whatever could be deterministically
    resolved, possibly still incomplete) to be handled exactly like a fresh classify()
    BankingService result -- the existing _missing_payload_fields guard downstream will
    ask for whatever, if anything, is still missing. Returns None (meaning: fall through
    to the normal classify() path unchanged) whenever nothing could be resolved -- e.g.
    the last turn isn't this specific kind of pending clarification, or `message` doesn't
    unambiguously supply any of the missing fields (a genuine subject change, an
    unrelated full-sentence reply, or an ambiguous message with 0 or 2+ numbers) -- never
    forces a guess.
    """
    if not recent_turns:
        return None
    last_classification = recent_turns[-1].classification or {}
    if last_classification.get("type") != "CLARIFICATION_REQUIRED":
        return None

    category = last_classification.get("category")
    service = last_classification.get("service")
    missing_fields = last_classification.get("missingFields")
    if not category or not service or not missing_fields:
        return None

    payload = dict(last_classification.get("payload") or {})
    resolved_any = False
    for field in missing_fields:
        extractor = _DETERMINISTIC_FIELD_EXTRACTORS.get(field)
        if extractor is None:
            continue
        value = extractor(message)
        if value is not None:
            payload[field] = value
            resolved_any = True

    if not resolved_any:
        return None

    return BankingService(
        category=category,
        service=service,
        subservice=last_classification.get("subservice"),
        payload=payload,
    )


def _candidate_number(candidate: dict) -> str:
    return str(
        candidate.get("accountNumber") or candidate.get("identifier")
        or candidate.get("cardNumber") or ""
    )


_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")


def _foreign_script(reply: str, message: str) -> bool:
    """Bengali script in a reply to a customer who wrote none (replies are English)."""
    return bool(_BENGALI_RE.search(reply or "")) and not _BENGALI_RE.search(message or "")


def _normalize_fee_type(result):
    """fees/fee_quote: transactionType must be one of the bank's live transfer ids
    (routing.fee_transaction_types). Live, the model sent "bkash transfer" and
    "NPSB", both 404s. Map to the id it names; otherwise drop it so the customer is
    asked which transfer type they mean."""
    if not (isinstance(result, BankingService) and (result.category, result.service) == ("fees", "fee_quote")):
        return result
    payload = dict(result.payload or {})
    raw = payload.get("transactionType")
    if not raw:
        return result
    valid = fee_transaction_types()
    if not valid:  # taxonomy not loaded: nothing to check against
        return result
    text = re.sub(r"[\s-]+", "_", str(raw).strip().lower())
    named = [v for v in valid if v == text or re.search(rf"(^|_){re.escape(v)}(_|$)", text)]
    if len(named) == 1:
        payload["transactionType"] = named[0]
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
    said = "\n".join(f'- "{_DIGIT_RUN_RE.sub(_mask_digit_run, m)}"' for m in messages)
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


async def _ground_freeze_request(result, message: str, recent_turns: list[ChatTurn]):
    """Freeze only. The classifier invents a plausible reason ("lost") and routes
    vague card problems ("my card isn't working", "reset my PIN") to freeze. Keep the
    freeze only if the customer asked to block the card or said why; the reason is
    the customer's own words, never the classifier's guess."""
    if not (isinstance(result, BankingService) and (result.category, result.service) == _FREEZE_KEY):
        return result
    messages = [t.message for t in (recent_turns or [])[-2:] if t.message] + [message]
    reason, block_request = await _freeze_request_facts(messages)
    if not reason and not block_request:
        question = await _phrase(
            "Freezing a card is only for a lost, stolen or misused card. What's happening "
            "with your card, and what would you like me to help with?",
            message,
        )
        return Clarification(question=question)
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
        f"The customer replied: \"{_DIGIT_RUN_RE.sub(_mask_digit_run, message)}\"\n\n"
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
    if last.get("type") != "ACCOUNT_SELECTION_REQUIRED" or not last.get("candidates"):
        return None
    candidates = [c for c in last["candidates"] if isinstance(c, dict)]
    chosen = None

    if req_payload:
        picked = {str(req_payload.get(k)) for k in ("accountNumber", "id", "identifier", "cardId")
                  if req_payload.get(k) is not None}
        matches = [c for c in candidates
                   if picked & {str(c.get(k)) for k in ("accountNumber", "id", "identifier")}]
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


def _account_card_summary(cards: object) -> str:
    """Build a ", linked to N ... card(s)" style fragment for an account's cards.

    Returns "" if there are no (countable) cards. Skips non-dict entries and
    cards missing a usable cardType. Skips cards whose status is present and
    clearly not ACTIVE; a missing status is treated as active/countable.
    """
    if not isinstance(cards, list):
        return ""
    counts: dict[str, int] = {}
    for card in cards:
        try:
            if not isinstance(card, dict):
                continue
            status = card.get("status")
            if status is not None and str(status).strip().upper() != "ACTIVE":
                continue
            card_type = card.get("cardType")
            if not card_type:
                continue
            type_name = str(card_type).strip().lower()
            if not type_name:
                continue
            counts[type_name] = counts.get(type_name, 0) + 1
        except Exception:
            continue
    total = sum(counts.values())
    if total == 0:
        return ""
    if len(counts) == 1:
        ((only_type, count),) = counts.items()
        noun = "card" if count == 1 else "cards"
        return f"linked to {count} {only_type} {noun}"
    breakdown = ", ".join(f"{count} {type_name}" for type_name, count in counts.items())
    return f"linked to {total} cards ({breakdown})"


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
    "balanceAfterThisTransaction",
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


_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _unsupported_numbers(reply: str, source: str) -> list[str]:
    """Numbers (3+ digits) in a model-written reply that don't appear in the data it
    was given -- a wrong balance must never reach a customer."""
    haystack = source.replace(",", "")
    return [
        n for n in _NUMBER_RE.findall(reply)
        if len(re.sub(r"\D", "", n)) >= 3 and n.replace(",", "") not in haystack
    ]


def _compact_for_prompt(node):
    """Fewer prompt tokens, same facts: drop link fields (icon URLs) the reply never
    uses. On the M40 every ~250 prompt tokens cost ~1 s. Nulls stay ("not set" is an
    answer), and so do empty lists ("none")."""
    if isinstance(node, dict):
        return {
            key: _compact_for_prompt(value)
            for key, value in node.items()
            if not (isinstance(value, str) and value.startswith(("http://", "https://")))
        }
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


def _reply_prompt(message: str, service: str, subservice: str | None, data: dict) -> tuple[str, str, dict]:
    """(prompt, data_json, redacted) for the data-answering reply -- shared by the
    streamed and non-streamed paths so both send the model the identical prompt."""
    if (subservice or service) == "accounts":
        data = _accounts_for_prompt(data)
    data = _label_running_balances(data)
    redacted = _redact_for_prompt(data, subservice or service)
    data_json = json.dumps(_compact_for_prompt(redacted), default=str, ensure_ascii=False,
                           separators=(",", ":"))
    prompt = (
        "You are Polygon Bank's chat assistant. The customer said:\n"
        f"\"{message}\"\n\n"
        "Here is the real data already fetched to answer them (JSON):\n"
        f"{data_json}\n\n"
        "Write a short, natural, accurate reply in English that directly answers what they "
        "asked, using ONLY this data. Copy every number exactly as it appears in the data — "
        "never change, round, add or invent a digit. Money is already in Bangladeshi taka "
        "(Tk); write it as given, never with $, Rs or any other currency, and never "
        "recalculate it. If a list is empty, say plainly there are none — never describe a "
        "record, request or status that isn't in the data. A null value means not set or "
        "not available. Ignore technical fields (status, pagination, ids, icons, "
        "timestamps' time-of-day) unless the customer asked about them. If the data doesn't "
        "cover something they asked (e.g. a date range), say what you DO have instead. Never "
        "state a full account or card number; use only masked forms present in the data. "
        "You can only SHOW this information: you cannot change, update, submit or cancel "
        "anything. If the customer asked to change something, never say it was done — say "
        "it can't be done in this chat and they can do it in the app, then share what the "
        "data shows if useful. Give no advice, contacts or steps that aren't in the data. "
        "1-3 sentences, plain prose, no markdown."
    )
    return prompt, data_json, redacted


async def _synthesize_reply(message: str, service: str, subservice: str | None, data: dict) -> str:
    """LLM-written reply answering the customer's actual question from the real
    fetched data only. Every 3+-digit number in the reply must exist in that data;
    a reply that fails the check is regenerated once at temperature 0, and only if
    that also fails (or Ollama is down) does the deterministic summary stand in."""
    prompt, data_json, redacted = _reply_prompt(message, service, subservice, data)
    for temperature in (0.2, 0.0):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": settings.OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "think": settings.OLLAMA_THINK,
                        "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": temperature},
                    },
                )
                resp.raise_for_status()
                text = (resp.json().get("response") or "").strip()
        except Exception:
            break
        if text and "$" not in text and not _unsupported_numbers(text, data_json):
            return text
    return _subservice_reply(service, subservice, redacted)


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
    prompt, data_json, redacted = _reply_prompt(message, service, subservice, data)
    full, sent = "", 0
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": True,
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.2},
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    full += chunk.get("response") or ""
                    done = bool(chunk.get("done"))
                    ends = [m.end() for m in _SENTENCE_END_RE.finditer(full)]
                    cut = len(full) if done else (ends[-1] if ends else 0)
                    safe = full[:cut]
                    if "$" in safe or _unsupported_numbers(safe, data_json):
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
            yield gap + _subservice_reply(service, subservice, redacted)
        return
    if sent == 0:
        yield await _synthesize_reply(message, service, subservice, data)


def _subservice_reply(service: str, subservice: str | None, data: dict) -> str:
    key = subservice or service
    fallback = f"Sure — here's information about {service.replace('_', ' ')}."

    if not isinstance(data, dict):
        return fallback

    if key == "balance":
        return f"Your available balance is {data.get('balance')}."

    if key == "accounts":
        try:
            inner = data.get("data")
            accounts = inner.get("accounts") if isinstance(inner, dict) else None
            if not isinstance(accounts, list):
                return fallback
            if not accounts:
                return "You don't have any accounts on record."
            descriptions = []
            for a in accounts:
                if not isinstance(a, dict):
                    continue
                account_type = str(a.get("accountType") or "account").replace("_", " ").title()
                account_number = a.get("accountNumber")
                extras = []
                if account_number:
                    extras.append(f"ending {str(account_number)[-4:]}")
                card_summary = _account_card_summary(a.get("cards"))
                if card_summary:
                    extras.append(card_summary)
                if extras:
                    descriptions.append(f"{account_type} ({', '.join(extras)})")
                else:
                    descriptions.append(account_type)
            if not descriptions:
                return "You don't have any accounts on record."
            plural = "account" if len(descriptions) == 1 else "accounts"
            return f"You have {len(descriptions)} {plural}: {', '.join(descriptions)}."
        except Exception:
            return fallback

    if key == "device_history":
        try:
            devices = data.get("devices")
            if not isinstance(devices, list):
                return fallback
            if not devices:
                return "You don't have any devices on record."
            names = [d.get("deviceName") for d in devices if isinstance(d, dict) and d.get("deviceName")]
            if not names:
                return fallback
            plural = "device" if len(names) == 1 else "devices"
            return f"You have {len(names)} {plural} linked: {', '.join(str(n) for n in names)}."
        except Exception:
            return fallback

    if key == "transaction_history":
        try:
            transactions = data.get("transactions")
            if not isinstance(transactions, list):
                return fallback
            if not transactions:
                return "You don't have any recent transactions."
            pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
            total_count = pagination.get("totalCount")
            shown = len(transactions)
            if isinstance(total_count, int) and total_count > shown:
                summary = f"Here are your {shown} most recent transactions (out of {total_count} total)."
            else:
                plural = "transaction" if shown == 1 else "transactions"
                summary = f"Here are your {shown} most recent {plural}."
            latest = transactions[0]
            if isinstance(latest, dict):
                amount = latest.get("amount")
                description = latest.get("description")
                txn_type = str(latest.get("type") or "").upper()
                verb = {"DEBIT": "debit", "CREDIT": "credit"}.get(txn_type)
                if amount is not None and description and verb:
                    summary += f" Your most recent was a {amount} {description} {verb}."
            return summary
        except Exception:
            return fallback

    if key == "login_history":
        try:
            logins = None
            for candidate_key in ("records", "loginHistory", "logins", "history"):
                candidate = data.get(candidate_key)
                if isinstance(candidate, list):
                    logins = candidate
                    break
            if logins is None and isinstance(data.get("data"), list):
                logins = data.get("data")
            if logins is None:
                return fallback
            if not logins:
                return "There's no login history on record for this device."
            pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
            total_count = pagination.get("totalCount")
            shown = len(logins)
            if isinstance(total_count, int) and total_count > shown:
                summary = f"Here are your {shown} most recent logins (out of {total_count} total)."
            else:
                plural = "login" if shown == 1 else "logins"
                summary = f"Here are your {shown} most recent {plural}."
            latest = logins[0]
            if isinstance(latest, dict):
                status = latest.get("status")
                ip_address = latest.get("ipAddress")
                if status and ip_address:
                    summary += f" The most recent was {str(status).lower()} from {ip_address}."
                elif status:
                    summary += f" The most recent was {str(status).lower()}."
            return summary
        except Exception:
            return fallback

    return fallback


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


def _transfer_summary_reply(service: str, subservice: str | None, payload: dict) -> str:
    """Deterministic (never LLM-synthesized -- see T-56 module notes in _chat_stream)
    confirmation summary for a complete transfer/bank_transfer or transfer/wallet_transfer
    payload. There is no real adapter for either service -- ADR-0008's GET-only policy
    means a transfer is never executed from here -- so this template, built only from
    already-known payload fields, is the entire reply; it must never claim the transfer
    is done."""
    amount_formatted = _format_bdt(payload.get("amount")) or str(payload.get("amount"))
    if service == "wallet_transfer":
        provider_name = _wallet_provider_display_name(subservice)
        wallet_number = payload.get("walletNumber")
        destination = f"to your {provider_name} number {wallet_number}"
    else:
        transfer_name = _bank_transfer_display_name(subservice)
        account_number = payload.get("accountNumber")
        destination = f"to account {account_number} via {transfer_name}"
    return (
        f"Here's your transfer summary: {amount_formatted} {destination}. I can't complete "
        "this for you here — please confirm and finish it in the app."
    )


def _dispute_summary_reply(payload: dict) -> str:
    """Deterministic (never LLM-synthesized -- same reasoning as _transfer_summary_reply)
    confirmation summary for a complete service_requests/raise_dispute payload. There is no
    real submission here -- this flow never calls POST service-request/v1/disputes -- so this
    template, built only from already-known payload fields, is the entire reply; it must
    never claim the dispute has been filed."""
    transaction_ref = payload.get("transactionReferenceNo")
    account_number = payload.get("accountNumber")
    remarks = payload.get("remarks")
    # The customer's own account: last 4 only, like every other reply.
    account_ref = f"ending {str(account_number)[-4:]}" if account_number else "on file"
    return (
        f"Here's your dispute summary: transaction {transaction_ref} on account "
        f"{account_ref}, reason: {remarks}. I can't submit this for you here — please "
        "confirm and complete it in the app."
    )


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


def _account_selection_reply(accounts: list[dict]) -> str:
    options = ", ".join(_describe_selection_account(a) for a in accounts)
    noun = "cards" if accounts and all("cardNumber" in a for a in accounts) else "accounts"
    return f"You have multiple {noun} — which one did you mean? {options}."


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


def _beneficiary_display_name(beneficiary: dict) -> str:
    return beneficiary.get("nickname") or beneficiary.get("accountHolderName") or "that beneficiary"


def _beneficiary_match_reply(beneficiary: dict, destination: dict | None) -> str:
    name = _beneficiary_display_name(beneficiary)
    if destination is None:
        return f"Found {name}, but I can't route this transfer type automatically — please open it manually."
    action = destination["action"]
    if action == "own_bank_transfer":
        return f"Sending to {name} via your Polygon Bank account — redirecting you now."
    if action == "other_bank_transfer":
        return f"Sending to {name} via their other bank account — redirecting you now."
    if action == "wallet_transfer":
        provider = destination.get("provider") or "wallet"
        return f"Sending to {name} via {provider.title()} — redirecting you now."
    return f"Found {name} — redirecting you now."


def _beneficiary_selection_reply(beneficiaries: list[dict]) -> str:
    names = ", ".join(_beneficiary_display_name(b) for b in beneficiaries)
    return f"I found {len(beneficiaries)} beneficiaries matching that name — which one did you mean? {names}."


def _beneficiary_not_found_reply(name_query: str) -> str:
    return f"I couldn't find a beneficiary named {name_query}."


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


def _emit_outcome(
    outcome: _TurnOutcome, request_id: str, customer_identity, turn_started_at: float
) -> list[str]:
    """SSE chunks (token + result) for a decided _TurnOutcome, plus its per-turn log
    line and audit line. Logged payload is always secret-redacted."""
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
    return [
        _sse("token", {"token": outcome.token}),
        _result_event(
            outcome.result_type, outcome.category, outcome.service, outcome.subservice,
            payload=outcome.result_payload, routing=outcome.routing,
        ),
    ]


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
    last_session_classification = (session_turns[-1].classification or {}) if session_turns else {}

    # T-57: a pending freeze OTP step. Applies to a plain follow-up, or to an explicit
    # resubmit of the SAME category+service that carries otp/pin/password (frontends
    # may echo the routing fields back) -- any other explicit category+service is a
    # fresh request, same rule as the yes/no confirmation gate below.
    pending_otp: dict | None = None
    if last_session_classification.get("type") == _OTP_PENDING_TYPE:
        explicit_pair = (req.category, req.service) if (req.category and req.service) else None
        pending_pair = (last_session_classification.get("category"), last_session_classification.get("service"))
        if explicit_pair is None or (explicit_pair == pending_pair and _has_secret_fields(req.payload)):
            pending_otp = last_session_classification
        # A plain chat message with no form submission only stays inside the freeze
        # step when it's a cancel or looks like a code/password typed into the chat
        # box (never logged or sent to an LLM). Anything else means the customer has
        # moved on: the freeze is dropped and the message is handled normally.
        if (
            pending_otp is not None
            and explicit_pair is None
            and not _has_secret_fields(req.payload)
            and _classify_confirmation_reply(req.message) != "negative"
            and not _looks_like_typed_secret(req.message)
        ):
            pending_otp = None

    logger.info(json.dumps({
        "request_id": request_id,
        # While an OTP step is pending, the free-text message is never logged: a
        # customer may type their code/PIN into the chat box instead of the form.
        "message": "[redacted: pending verification]" if pending_otp is not None else req.message,
        "session_id": req.session_id,
        "top_k": req.top_k,
        "category": req.category,
        "service": req.service,
        "subservice": req.subservice,
        "payload": _redact_secrets(req.payload),
        "auth_present": token is not None,
    }))

    if pending_otp is not None:
        outcome = await _handle_freeze_otp_reply(
            customer_identity, token, pending_otp, req.message, req.payload
        )
        # Security step: sent exactly as decided, never reworded. Live, the rewording
        # put the card ending onto the phone number and invented a way to cancel.
        for chunk in _emit_outcome(outcome, request_id, customer_identity, turn_started_at):
            yield chunk
        yield _sse("done", {})
        record_turn(
            customer_identity.customer_id,
            ChatTurn(
                timestamp=datetime.now(timezone.utc),
                message="[redacted: verification submission]",
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
        in _CONFIRMATION_QUESTION_BUILDERS
    ):
        pending_confirmation = last_session_classification

    if pending_confirmation is not None:
        outcome = _classify_confirmation_reply(req.message)
        conf_category = pending_confirmation.get("category")
        conf_service = pending_confirmation.get("service")
        conf_subservice = pending_confirmation.get("subservice")
        conf_payload = pending_confirmation.get("payload")
        conf_question = pending_confirmation.get("question") or "Shall I proceed? (yes/no)"
        confirmation_turn_classification: dict

        if outcome == "negative":
            decline_token = _CONFIRMATION_DECLINE_MESSAGES.get(
                (conf_category, conf_service), "Okay, I won't go ahead with that."
            )
            decline_token = await _phrase(decline_token, req.message)
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
            reask_token = f"Sorry, I didn't quite catch that — {conf_question}"
            reask_token = await _phrase(reask_token, req.message)
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
        else:
            try:
                adapter_result = await fulfill_banking_service(
                    customer_identity, token, conf_category, conf_service, conf_subservice, conf_payload
                )
            except AdapterAuthError:
                confirm_auth_token = "Please log in to continue with this request."
                confirm_auth_token = await _phrase(confirm_auth_token, req.message)
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
            except AdapterUnavailableError:
                confirm_unavailable_token = "That service isn't available right now. Please try again shortly."
                confirm_unavailable_token = await _phrase(confirm_unavailable_token, req.message)
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
                success_builder = _CONFIRMATION_SUCCESS_MESSAGES.get((conf_category, conf_service))
                success_token = success_builder(conf_payload) if success_builder else "Done."
                success_token = await _phrase(success_token, req.message)
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
                message=req.message,
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
        result = await _try_account_selection_completion(recent_turns, req.message, req.payload)
        if result is None:
            result = _try_deterministic_payload_completion(recent_turns, req.message)
        if result is not None:
            # A bare follow-up ("500", "the savings one") answered our question; the reply
            # must still answer what the customer originally asked.
            reply_context = f"{recent_turns[-1].message} (follow-up answer: {req.message})"
        if result is None:
            result = await classify(req.message, recent_turns=recent_turns)
            if isinstance(result, BankingService) and req.payload is not None:
                result = BankingService(
                    category=result.category,
                    service=result.service,
                    subservice=result.subservice,
                    payload=req.payload,
                )
            result = await _ground_freeze_request(result, req.message, recent_turns)
            result = _normalize_fee_type(result)

    turn_classification: dict | None = None

    if isinstance(result, KbQuestion):
        async for chunk in _kb_stream(req, request_id):
            yield chunk
        if customer_identity is not None:
            record_turn(
                customer_identity.customer_id,
                ChatTurn(timestamp=datetime.now(timezone.utc), message=req.message, classification=None),
            )
        return

    if isinstance(result, Clarification) and _foreign_script(result.question, req.message):
        # Live: Banglish typed in Latin letters came back as garbled Bengali script.
        result = Clarification(question=_CLARIFICATION_FALLBACK)
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
        unknown_service_token = "I'm not able to help with that specific request right now."
        unknown_service_token = await _phrase(unknown_service_token, req.message)
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
            auth_required_token = "Please log in to continue with this request."
            auth_required_token = await _phrase(auth_required_token, req.message)
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
            if category == "card_services" and service == "frezz_unfrezz" and not (payload or {}).get("cardId"):
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
                    freeze_cards_auth_token = "Please log in to continue with this request."
                    freeze_cards_auth_token = await _phrase(freeze_cards_auth_token, req.message)
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
                    freeze_cards_unavailable_token = "That service isn't available right now. Please try again shortly."
                    freeze_cards_unavailable_token = await _phrase(freeze_cards_unavailable_token, req.message)
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
                        no_cards_token = "You don't have any cards on file, so there's nothing to freeze."
                        no_cards_token = await _phrase(no_cards_token, req.message)
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
                        card_selection_token = _account_selection_reply(cards)
                        card_selection_token = await _phrase(card_selection_token, req.message)
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

            if turn_classification is None:
                missing_fields = _missing_payload_fields(category, service, payload)
                if missing_fields:
                    clarification_question = await _clarification_question_for(
                        req.message, category, service, subservice, payload, missing_fields
                    )
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
                    transfer_summary_token = _transfer_summary_reply(service, subservice, payload or {})
                    transfer_summary_token = await _phrase(transfer_summary_token, req.message)
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
                    dispute_summary_token = _dispute_summary_reply(payload or {})
                    dispute_summary_token = await _phrase(dispute_summary_token, req.message)
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
                elif (category, service) == _FREEZE_KEY:
                    # T-57: card + reason known -> send the OTP to the customer's own
                    # phone and ask for OTP + PIN/password (replaces the old yes/no).
                    # The freeze itself only ever runs from the pending OTP_REQUIRED
                    # branch at the top of this function.
                    freeze_outcome = await _send_freeze_otp(
                        customer_identity, category, service, subservice, payload
                    )
                    # Security step: exact wording, never reworded (see the OTP branch above).
                    for chunk in _emit_outcome(freeze_outcome, request_id, customer_identity, turn_started_at):
                        yield chunk
                    turn_classification = freeze_outcome.classification()
                elif (category, service) in _CONFIRMATION_QUESTION_BUILDERS:
                    # T-57/T-60: this chatbot's first-ever mutating platform calls --
                    # never executed here. Only an explicit, deterministic "yes" on the
                    # customer's NEXT turn (see the pending_confirmation branch near the
                    # top of this function) triggers the actual fulfill_banking_service
                    # call; nothing below this point calls the real adapter.
                    if category == "beneficiary_management" and service == "beneficiary_add":
                        # T-60: this conversational flow currently only supports adding
                        # an other-bank beneficiary by account number -- the real
                        # CreateBeneficiaryRequest's other serviceTypes (MFS wallets,
                        # billers, ...) need fields this flow doesn't gather yet. These
                        # two are fixed defaults, not asked of the customer, mirroring
                        # FreezeCardAdapter's own fixed `reasonCode: "OTHER"` default.
                        payload = dict(payload or {})
                        payload.setdefault("serviceType", "OTHER_BANK")
                        payload.setdefault("identifierType", "ACCOUNT_NUMBER")
                    confirmation_question = _CONFIRMATION_QUESTION_BUILDERS[(category, service)](payload)
                    confirmation_question = await _phrase(confirmation_question, req.message)
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
                        adapter_auth_error_token = "Please log in to continue with this request."
                        adapter_auth_error_token = await _phrase(adapter_auth_error_token, req.message)
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
                        account_selection_token = _account_selection_reply(exc.accounts)
                        account_selection_token = await _phrase(account_selection_token, req.message)
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
                        service_unavailable_token = "That service isn't available right now. Please try again shortly."
                        service_unavailable_token = await _phrase(service_unavailable_token, req.message)
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
                                beneficiary_reply_token = _beneficiary_not_found_reply(
                                    payload.get("nameQuery") or "that beneficiary"
                                )
                                beneficiary_reply_token = await _phrase(beneficiary_reply_token, req.message)
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
                                beneficiary_reply_token = _beneficiary_match_reply(matched, destination)
                                beneficiary_reply_token = await _phrase(beneficiary_reply_token, req.message)
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
                                beneficiary_reply_token = _beneficiary_selection_reply(matches)
                                beneficiary_reply_token = await _phrase(beneficiary_reply_token, req.message)
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
                                banking_service_token = await _phrase(f"This is placeholder information about {service.replace('_', ' ')}; the real service isn't connected to chat yet.", req.message)
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
                                routing={"category": category, "service": service, "subservice": subservice, "action": "redirect"},
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
        record_turn(
            customer_identity.customer_id,
            ChatTurn(
                timestamp=datetime.now(timezone.utc),
                message=req.message,
                classification=_session_safe_classification(turn_classification),
            ),
        )


@router.post("")
async def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
    return StreamingResponse(_chat_stream(req, authorization), media_type="text/event-stream")
