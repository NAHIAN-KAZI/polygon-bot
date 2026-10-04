"""Generated (LLM-worded) missing-field clarifying questions in app/routes/chat.py.

tests/conftest.py disables generation for every test by default (template fallback,
deterministic). These tests re-enable the REAL generator (captured at import time,
before that autouse patch runs) and mock only the Ollama HTTP call.
"""
import asyncio
import json

import httpx
import pytest

import app.banking.session as session_module
import app.routes.chat as chat_module
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService
from app.config import settings

from tests.conftest import AUTH_HEADERS

REAL_GENERATE = chat_module._generate_clarification_question
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}
CUSTOMER_ID = "01712345678"


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _install_fake_ollama(monkeypatch, response_text=None, exc=None):
    calls = []

    async def fake_post(self, url, json=None, **kwargs):
        calls.append({"url": url, "json": json})
        if exc is not None:
            raise exc
        return _FakeResponse({"response": response_text})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return calls


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def real_generator(monkeypatch):
    monkeypatch.setattr(chat_module, "_generate_clarification_question", REAL_GENERATE)


def _parse_sse(body):
    events = []
    for block in body.strip("\n").split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        events.append((name, data))
    return events


# --- the helper itself --------------------------------------------------------


def test_prompt_contents_and_request_shape(monkeypatch):
    calls = _install_fake_ollama(monkeypatch, "How much would you like to send to the account ending 7890?")
    question = _run(REAL_GENERATE(
        "send money to account 1234567890",
        "transfer", "bank_transfer", "other_bank",
        {"accountNumber": "1234567890", "pin": "864209", "otp": "731942"},
        ["amount"],
    ))
    assert question == "How much would you like to send to the account ending 7890?"

    assert len(calls) == 1
    body = calls[0]["json"]
    assert calls[0]["url"] == f"{settings.OLLAMA_BASE_URL}/api/generate"
    assert body["model"] == settings.OLLAMA_MODEL
    assert body["stream"] is False
    assert body["options"] == {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0.3}
    prompt = body["prompt"]
    assert "Other Bank Transfer" in prompt
    assert "account number ending 7890" in prompt
    assert "how much money (in taka)" in prompt
    # Full numbers and secrets never reach the model.
    assert "1234567890" not in prompt
    assert "864209" not in prompt and "731942" not in prompt
    assert "never ask for a PIN, password, OTP" in prompt


def test_wallet_number_missing_is_described_with_provider(monkeypatch):
    calls = _install_fake_ollama(monkeypatch, "Which bKash number should I send Tk 500 to?")
    _run(REAL_GENERATE("send 500 to bkash", "transfer", "wallet_transfer", "bkash", {"amount": 500}, ["walletNumber"]))
    prompt = calls[0]["json"]["prompt"]
    assert "the bKash number to send to" in prompt
    assert "Tk 500" in prompt


@pytest.mark.parametrize(
    "kwargs",
    [
        {"exc": httpx.ConnectTimeout("timeout")},
        {"response_text": ""},
        {"response_text": "   "},
        {"response_text": "Please share your PIN so I can continue."},
        {"response_text": "What's the OTP you received?"},
        {"response_text": "x" * 500},
        {"response_text": "How much do you want to send via bKash? Is it XXXX taka?"},
        {"response_text": "How much is [amount]?"},
    ],
)
def test_returns_none_on_failure_or_unsafe_output(monkeypatch, kwargs):
    _install_fake_ollama(monkeypatch, **kwargs)
    assert _run(REAL_GENERATE("fee for bkash", "fees", "fee_quote", None, {"transactionType": "BKASH"}, ["amount"])) is None


def test_output_is_cleaned_and_long_digit_runs_masked(monkeypatch):
    _install_fake_ollama(monkeypatch, '"**How much** should I send to 1234567890?"')
    question = _run(REAL_GENERATE("x", "transfer", "bank_transfer", None, {"accountNumber": "1234567890"}, ["amount"]))
    assert question == "How much should I send to ••••••7890?"


# --- wired into /chat ---------------------------------------------------------


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(session_module, "_sessions", {})

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)


def test_chat_uses_generated_question_and_stores_exactly_what_was_sent(client, monkeypatch, real_generator, session):
    generated = "Happy to check that — how much are you planning to send through bKash?"
    _install_fake_ollama(monkeypatch, generated)

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="fees", service="fee_quote", subservice=None, payload={"transactionType": "BKASH"})

    monkeypatch.setattr(chat_module, "classify", fake_classify)

    resp = client.post("/chat", json={"message": "what's the fee to send money via bkash"}, headers=JWT_HEADERS)
    events = _parse_sse(resp.text)
    token = next(d for n, d in events if n == "token")["token"]
    assert token == generated
    assert next(d for n, d in events if n == "result")["type"] == "CLARIFICATION_REQUIRED"

    stored = session_module.get_session(CUSTOMER_ID)[-1].classification
    assert stored["question"] == generated
    assert stored["missingFields"] == ["amount"]
    assert stored["category"] == "fees" and stored["service"] == "fee_quote"


def test_chat_falls_back_to_template_when_generation_fails(client, monkeypatch, real_generator, session):
    _install_fake_ollama(monkeypatch, exc=httpx.ReadTimeout("slow"))

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="fees", service="fee_quote", subservice=None, payload={"transactionType": "other_bank"})

    monkeypatch.setattr(chat_module, "classify", fake_classify)

    resp = client.post("/chat", json={"message": "fee for other bank transfer"}, headers=JWT_HEADERS)
    token = next(d for n, d in _parse_sse(resp.text) if n == "token")["token"]
    expected = chat_module._fee_quote_clarification_question({"transactionType": "other_bank"})
    assert token == expected
    assert session_module.get_session(CUSTOMER_ID)[-1].classification["question"] == expected


def test_t55_bare_amount_completion_still_works_after_generated_question(client, monkeypatch, real_generator, session):
    _install_fake_ollama(monkeypatch, "Sure thing — how much do you want to send via bKash?")
    classify_calls = []

    async def fake_classify(message, recent_turns=None):
        classify_calls.append(message)
        return BankingService(category="fees", service="fee_quote", subservice=None, payload={"transactionType": "BKASH"})

    fulfill_calls = []

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        fulfill_calls.append((category, service, payload))
        return AdapterResult(data={"mock": True})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)

    client.post("/chat", json={"message": "fee to send via bkash"}, headers=JWT_HEADERS)
    resp = client.post("/chat", json={"message": "2000 taka"}, headers=JWT_HEADERS)

    assert classify_calls == ["fee to send via bkash"]
    assert fulfill_calls == [("fees", "fee_quote", {"transactionType": "BKASH", "amount": 2000})]
    assert next(d for n, d in _parse_sse(resp.text) if n == "result")["type"] == "BANKING_SERVICE"


def test_beneficiary_add_confirmation_stays_fixed_text(client, monkeypatch, real_generator, session):
    """Security confirmations are never generated -- no Ollama call at all."""
    calls = _install_fake_ollama(monkeypatch, "SHOULD NOT BE USED")

    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="beneficiary_management", service="beneficiary_add", subservice=None,
            payload={"nickname": "Rahim", "accountNumber": "1234567890"},
        )

    async def fake_lookup(jwt, identifier):
        return {"accountNumber": "1234567890", "accountName": "Rahim Uddin"}

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "lookup_recipient", fake_lookup)
    resp = client.post("/chat", json={"message": "add Rahim"}, headers=JWT_HEADERS)
    token = next(d for n, d in _parse_sse(resp.text) if n == "token")["token"]
    assert token.endswith("Shall I proceed? (yes/no)")
    assert calls == []
