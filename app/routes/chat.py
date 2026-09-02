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
from app.banking.adapters.base import AdapterAuthError, AdapterUnavailableError
from app.banking.identity import extract_jwt, verify_jwt
from app.banking.routing import BankingService, Clarification, KbQuestion, UnknownService, classify
from app.banking.session import ChatTurn, get_session, record_turn
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


def _subservice_reply(service: str, subservice: str | None, data: dict) -> str:
    key = subservice or service
    if key == "balance":
        return f"Your available balance is {data.get('balance')}."
    if key == "transaction_history":
        return "Here are your recent transactions."
    if key in ("accounts", "device_history", "login_history"):
        return f"Here's your {key.replace('_', ' ')} information."
    return f"Sure — here's information about {service.replace('_', ' ')}."


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
    customer_identity = verify_jwt(token) if token else None

    recent_turns = get_session(customer_identity.customer_id) if customer_identity else []

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
