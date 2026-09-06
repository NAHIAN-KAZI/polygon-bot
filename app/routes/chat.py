import json
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.auth import require_api_key
from app.banking import audit
from app.banking.adapters import fulfill_banking_service
from app.banking.adapters.base import AdapterAccountSelectionRequiredError, AdapterAuthError, AdapterUnavailableError
from app.banking.identity import extract_jwt, verify_jwt
from app.banking.routing import BankingService, Clarification, KbQuestion, UnknownService, classify
from app.banking.session import ChatTurn, get_classification_context, record_turn
from app.banking.taxonomy import is_valid_path
from app.config import settings
from app.embeddings import embed_text
from app.llm import build_prompt, stream_generate
from app.vectorstore import search

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


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
                    summary += f" Your most recent was a ৳{amount} {description} {verb}."
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


def _account_selection_reply(accounts: list[dict]) -> str:
    options = ", ".join(
        f"{a.get('accountType', 'account').title()} account ending {str(a.get('accountNumber', ''))[-4:]}"
        for a in accounts
    )
    return f"You have multiple accounts — which one did you mean? {options}."


async def _kb_stream(req: ChatRequest):
    top_k = req.top_k or settings.DEFAULT_TOP_K
    try:
        query_vector = await embed_text(req.message)
        hits = search(query_vector, top_k)
    except httpx.HTTPStatusError as e:
        yield _sse("error", {"detail": f"Embedding model rejected the request: {e.response.text.strip()}"})
        return
    except httpx.HTTPError:
        yield _sse("error", {"detail": "Embedding model (Ollama) is unreachable"})
        return
    except Exception:
        yield _sse("error", {"detail": "Vector store (Qdrant) is unreachable"})
        return

    prompt = build_prompt(req.message, hits)
    try:
        async for token in stream_generate(prompt):
            yield _sse("token", {"token": token})
    except httpx.HTTPError:
        yield _sse("error", {"detail": "Generation model (Ollama) failed or became unreachable mid-stream"})
        return

    yield _sse("done", {})


async def _chat_stream(req: ChatRequest, authorization: str | None):
    turn_started_at = time.monotonic()
    token = extract_jwt(authorization)
    customer_identity = await verify_jwt(token) if token else None

    recent_turns = get_classification_context(customer_identity.customer_id) if customer_identity else []

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
        result = await classify(req.message, recent_turns=recent_turns)
        if isinstance(result, BankingService) and req.payload is not None:
            result = BankingService(
                category=result.category,
                service=result.service,
                subservice=result.subservice,
                payload=req.payload,
            )

    turn_classification: dict | None = None

    if isinstance(result, KbQuestion):
        async for chunk in _kb_stream(req):
            yield chunk
        if customer_identity is not None:
            record_turn(
                customer_identity.customer_id,
                ChatTurn(timestamp=datetime.now(timezone.utc), message=req.message, classification=None),
            )
        return

    if isinstance(result, Clarification):
        yield _sse("token", {"token": result.question})
        yield _result_event("CLARIFICATION_REQUIRED", None, None, None)
        turn_classification = {"type": "CLARIFICATION_REQUIRED", "category": None, "service": None, "subservice": None}
        audit.log_banking_turn(customer_identity, turn_classification, latency_ms=(time.monotonic() - turn_started_at) * 1000)

    elif isinstance(result, UnknownService):
        yield _sse("token", {"token": "I'm not able to help with that specific request right now."})
        yield _result_event("UNKNOWN_SERVICE", result.category, result.service, result.subservice)
        turn_classification = {
            "type": "UNKNOWN_SERVICE",
            "category": result.category,
            "service": result.service,
            "subservice": result.subservice,
        }
        audit.log_banking_turn(customer_identity, turn_classification, latency_ms=(time.monotonic() - turn_started_at) * 1000)

    elif isinstance(result, BankingService):
        category, service, subservice, payload = (
            result.category,
            result.service,
            result.subservice,
            result.payload,
        )

        if customer_identity is None:
            yield _sse("token", {"token": "Please log in to continue with this request."})
            yield _result_event("AUTH_REQUIRED", category, service, subservice)
            turn_classification = {
                "type": "AUTH_REQUIRED",
                "category": category,
                "service": service,
                "subservice": subservice,
            }
            audit.log_banking_turn(customer_identity, turn_classification, latency_ms=(time.monotonic() - turn_started_at) * 1000)
        else:
            try:
                adapter_result = await fulfill_banking_service(
                    customer_identity, token, category, service, subservice, payload
                )
            except AdapterAuthError:
                yield _sse("token", {"token": "Please log in to continue with this request."})
                yield _result_event("AUTH_REQUIRED", category, service, subservice)
                turn_classification = {
                    "type": "AUTH_REQUIRED",
                    "category": category,
                    "service": service,
                    "subservice": subservice,
                }
                audit.log_banking_turn(customer_identity, turn_classification, latency_ms=(time.monotonic() - turn_started_at) * 1000)
            except AdapterAccountSelectionRequiredError as exc:
                yield _sse("token", {"token": _account_selection_reply(exc.accounts)})
                yield _result_event(
                    "ACCOUNT_SELECTION_REQUIRED", category, service, subservice, payload={"accounts": exc.accounts}
                )
                turn_classification = {
                    "type": "ACCOUNT_SELECTION_REQUIRED",
                    "category": category,
                    "service": service,
                    "subservice": subservice,
                }
                audit.log_banking_turn(customer_identity, turn_classification, latency_ms=(time.monotonic() - turn_started_at) * 1000)
            except AdapterUnavailableError:
                yield _sse("token", {"token": "That service isn't available right now. Please try again shortly."})
                yield _result_event("SERVICE_UNAVAILABLE", category, service, subservice)
                turn_classification = {
                    "type": "SERVICE_UNAVAILABLE",
                    "category": category,
                    "service": service,
                    "subservice": subservice,
                }
                audit.log_banking_turn(customer_identity, turn_classification, latency_ms=(time.monotonic() - turn_started_at) * 1000)
            else:
                data = adapter_result.data
                if data.get("mock") is True:
                    yield _sse("token", {"token": f"Sure — here's information about {service.replace('_', ' ')}."})
                else:
                    yield _sse("token", {"token": _subservice_reply(service, subservice, data)})
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
                audit.log_banking_turn(customer_identity, turn_classification, latency_ms=(time.monotonic() - turn_started_at) * 1000)

    yield _sse("done", {})

    if customer_identity is not None:
        record_turn(
            customer_identity.customer_id,
            ChatTurn(
                timestamp=datetime.now(timezone.utc),
                message=req.message,
                classification=turn_classification,
            ),
        )


@router.post("")
async def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
    return StreamingResponse(_chat_stream(req, authorization), media_type="text/event-stream")
