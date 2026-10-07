"""T-77 (chat side): every customer message is composed from facts, so safety lives in
what the code decides and what it lets a model see.

Covers _read_pending_reply (buttons decided without the model, secrets never shown to
a model, a "confirm" only when grounded in the customer's own words), _amount_supported
/ _check_amount (an amount must be a number the customer wrote times a power of ten),
_say / _safe_for_model / _history, the persona-based data-reply prompt, and the
/chat wiring of all of these. Ollama is never reached.
"""
import asyncio
import json

import httpx
import pytest

import app.routes.chat as chat_module
from app.banking.identity import CustomerIdentity
from app.banking.adapters.base import AdapterResult
from app.banking.routing import BankingService, Clarification
from app.banking.session import ChatTurn
from app.conversation.persona import GLOBAL_PERSONA, KIND_EXAMPLE, KIND_PURPOSE

from tests.conftest import AUTH_HEADERS

# Captured at import, before conftest's autouse fixture swaps in a stand-in.
_real_read = chat_module._read_pending_reply

CUSTOMER_ID = "cust-77"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}


class _Resp:
    def __init__(self, obj):
        self._obj = obj

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": json.dumps(self._obj)}


def _model(monkeypatch, obj=None, error=None):
    """Patch the model call; returns the prompts it was sent."""
    prompts = []

    async def fake_post(self, url, *args, **kwargs):
        prompts.append(kwargs.get("json", {}).get("prompt", ""))
        if error is not None:
            raise error
        return _Resp(obj)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return prompts


def _read(question, message, payload=None):
    return asyncio.run(_real_read(question, message, payload))


# --- _read_pending_reply ---------------------------------------------------------


@pytest.mark.parametrize("confirm,expected", [(True, "confirm"), (False, "decline")])
def test_app_button_is_decided_without_the_model(monkeypatch, confirm, expected):
    prompts = _model(monkeypatch, error=AssertionError("the model must not be asked"))
    assert _read("Save Rahim?", "anything at all", {"confirm": confirm}) == expected
    assert prompts == []


def test_non_boolean_confirm_is_not_a_button_press(monkeypatch):
    prompts = _model(monkeypatch, {"answer": "unsure", "quote": "ok"})
    assert _read("Save Rahim?", "ok", {"confirm": "yes"}) == "unsure"
    assert len(prompts) == 1


@pytest.mark.parametrize("message,payload", [
    ("482916", None),
    ("my code is 4829 and pin 1234", None),
    ("Secret@123", None),
    ("submit", {"otp": "482916"}),
    ("submit", {"pin": "1234"}),
    ("submit", {"password": "hunter2"}),
])
def test_secret_shaped_text_never_reaches_a_model(monkeypatch, message, payload):
    prompts = _model(monkeypatch, error=AssertionError("a secret must never be sent to a model"))
    assert _read("Enter the code in the app", message, payload) == "secret"
    assert prompts == []


def test_confirm_counts_only_with_the_customers_own_words(monkeypatch):
    _model(monkeypatch, {"answer": "confirm", "quote": "yes go ahead"})
    assert _read("Save Rahim?", "yes go ahead") == "confirm"
    assert _read("Save Rahim?", "hmm what does that mean") == "unsure"


@pytest.mark.parametrize("quote", [None, "", "null", "n/a"])
def test_confirm_without_a_quote_is_unsure(monkeypatch, quote):
    _model(monkeypatch, {"answer": "confirm", "quote": quote})
    assert _read("Save Rahim?", "yes") == "unsure"


def test_decline_and_other_are_passed_through(monkeypatch):
    _model(monkeypatch, {"answer": "decline", "quote": "no"})
    assert _read("Save Rahim?", "no thanks") == "decline"
    _model(monkeypatch, {"answer": "other", "quote": "balance"})
    assert _read("Save Rahim?", "what is my balance") == "other"


@pytest.mark.parametrize("parsed", [{"answer": "maybe?"}, {}, ["confirm"], "confirm"])
def test_unknown_or_malformed_answers_are_unsure(monkeypatch, parsed):
    _model(monkeypatch, parsed)
    assert _read("Save Rahim?", "go") == "unsure"


@pytest.mark.parametrize("error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")])
def test_model_failure_is_unsure(monkeypatch, error):
    _model(monkeypatch, error=error)
    assert _read("Save Rahim?", "yes") == "unsure"


def test_the_prompt_carries_the_pending_question_and_the_reply(monkeypatch):
    prompts = _model(monkeypatch, {"answer": "unsure", "quote": ""})
    _read("Shall I save Rahim as a beneficiary?", "not now")
    assert 'asked the customer: "Shall I save Rahim as a beneficiary?"' in prompts[0]
    assert 'The customer replied: "not now"' in prompts[0]


# --- _amount_supported / _check_amount -------------------------------------------


@pytest.mark.parametrize("amount,text", [
    (50000, "send 50k to bkash"),
    (150000, "1.5 lakh pathabo"),
    (75000, "75,000 taka"),
    (20000000, "2 crore"),
    ("5000", "5000 tk"),
    (2000.5, "2000.50"),
])
def test_amount_is_a_written_number_times_a_power_of_ten(amount, text):
    assert chat_module._amount_supported(amount, text) is True


@pytest.mark.parametrize("amount,text", [
    (5, "send 50k"),           # an amount smaller than anything written
    (3000, "send 5000"),       # a different number
    (50001, "50k"),
    (0, "0"),
    (-500, "500"),
    (None, "500"),
    ("abc", "abc 500"),
    (500, ""),
])
def test_amount_not_written_by_the_customer_is_rejected(amount, text):
    assert chat_module._amount_supported(amount, text) is False


def test_check_amount_drops_an_unsupported_amount_and_keeps_the_rest():
    result = BankingService("transfer", "wallet_transfer", "bkash", {"walletNumber": "01812345678", "amount": 3000})
    out = chat_module._check_amount(result, "send 5000 to 01812345678")
    assert out == BankingService("transfer", "wallet_transfer", "bkash", {"walletNumber": "01812345678"})


def test_check_amount_keeps_a_supported_amount_unchanged():
    result = BankingService("fees", "fee_quote", None, {"transactionType": "bkash", "amount": 50000})
    assert chat_module._check_amount(result, "fee for 50k bkash") is result


def test_check_amount_payload_with_only_a_bad_amount_becomes_none():
    out = chat_module._check_amount(BankingService("fees", "fee_quote", None, {"amount": 7}), "fee koto")
    assert out.payload is None


@pytest.mark.parametrize("result", [
    Clarification(question="?"),
    BankingService("account_info", "balance", None, None),
    BankingService("transfer", "bank_transfer", "other_bank", {"accountNumber": "1234567890"}),
])
def test_check_amount_leaves_results_without_an_amount_alone(result):
    assert chat_module._check_amount(result, "anything") is result


# --- _say / _safe_for_model / _history -------------------------------------------


def test_say_turns_keywords_into_labelled_facts_and_drops_empties():
    kind, facts, must = chat_module._say("confirm", {"card ending": "0251"},
                                         to_confirm="say yes", reason=None, note="")
    assert kind == "confirm"
    assert facts == {"to confirm": "say yes"}
    assert must == {"card ending": "0251"}
    assert chat_module._say("declined")[2] == {}


@pytest.mark.parametrize("message,payload", [("482916", None), ("submit", {"otp": "1"}), ("x", {"pin": "1234"})])
def test_composer_never_sees_a_typed_or_submitted_secret(message, payload):
    safe = chat_module._safe_for_model(message, payload)
    assert safe == "(the customer submitted the secure verification form)"


def test_composer_sees_ordinary_text_as_is():
    assert chat_module._safe_for_model("what is my balance", None) == "what is my balance"


def _turn(message, **classification):
    return ChatTurn(timestamp=None, message=message, classification=classification or None)


def test_history_is_empty_for_nothing_or_no_turns():
    assert chat_module._history(None) == []
    assert chat_module._history([]) == []


@pytest.mark.parametrize("answered", [
    {"type": "BANKING_SERVICE", "question": "an old question"},
    {"type": "AUTH_REQUIRED"}, {"type": "SERVICE_UNAVAILABLE"}, {"type": "UNKNOWN_SERVICE"},
    {"type": "BENEFICIARY_MATCH"}, {},
])
def test_history_is_empty_once_the_topic_is_finished(answered):
    turns = [_turn("freeze my card", type="CONFIRMATION_REQUIRED", question="Shall I?"),
             _turn("what is my balance", **answered)]
    assert chat_module._history(turns) == []


def test_history_is_empty_when_the_last_turn_has_no_classification():
    assert chat_module._history([_turn("open q", type="CLARIFICATION_REQUIRED", question="?"),
                                 ChatTurn(timestamp=None, message="what is a DPS", classification=None)]) == []


@pytest.mark.parametrize("open_type", [
    "CLARIFICATION_REQUIRED", "CONFIRMATION_REQUIRED", "OTP_REQUIRED", "ACCOUNT_SELECTION_REQUIRED",
    "TRANSACTION_SELECTION_REQUIRED", "BENEFICIARY_SELECTION_REQUIRED",
])
def test_history_while_a_question_is_open_is_the_last_two_turns_with_the_question(open_type):
    turns = [_turn("older topic", type="BANKING_SERVICE", question="old q"),
             _turn("send money", type="CLARIFICATION_REQUIRED", question="To whom?"),
             _turn("to Rahim", type=open_type, question="Which Rahim?")]
    assert chat_module._history(turns) == [
        ("Customer", "send money"), ("Assistant", "To whom?"),
        ("Customer", "to Rahim"), ("Assistant", "Which Rahim?")]


def test_history_skips_verification_submissions_even_while_open():
    turns = [_turn("freeze my card", type="CONFIRMATION_REQUIRED", question="Shall I?"),
             _turn("[redacted: verification submission]", type="OTP_REQUIRED", question="Enter the code")]
    assert chat_module._history(turns) == [
        ("Customer", "freeze my card"), ("Assistant", "Shall I?"), ("Assistant", "Enter the code")]


def test_history_with_a_single_open_turn():
    assert chat_module._history([_turn("hmm", type="CLARIFICATION_REQUIRED", question="What?")]) == [
        ("Customer", "hmm"), ("Assistant", "What?")]


# --- _synthesize_reply: the retry knows what was wrong ------------------------------------------


def _chat_model(monkeypatch, *texts):
    sent = []
    queue = list(texts)

    class _R:
        def __init__(self, text):
            self._text = text

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": self._text}}

    async def fake_post(self, url, *args, **kwargs):
        sent.append(kwargs["json"])
        return _R(queue.pop(0))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return sent


def test_second_attempt_is_told_why_the_first_was_rejected(monkeypatch):
    sent = _chat_model(monkeypatch, "Your balance is Tk 31,000.00.", "Your balance is Tk 90,000.00.")
    out = asyncio.run(chat_module._synthesize_reply("balance?", "balance", None, {"balance": 9000000}))
    assert out == "Your balance is Tk 90,000.00."
    assert len(sent) == 2
    first, second = (body["messages"][1]["content"] for body in sent)
    assert "rejected because" not in first
    assert "Your previous reply was rejected because it contained numbers that are not in the facts" in second
    assert "31,000" in second  # names the offending number
    assert sent[1]["options"]["temperature"] == 0.0
    assert sent[0]["messages"][0] == sent[1]["messages"][0]  # same persona both times


def test_two_rejected_replies_fall_back_to_the_data_facts(monkeypatch):
    sent = _chat_model(monkeypatch, "- Your balance is $5", "Your balance is Tk 31,000.00.")
    out = asyncio.run(chat_module._synthesize_reply("balance?", "balance", None, {"balance": 9000000}))
    assert len(sent) == 2
    assert out == "balance: Tk 90,000.00"
    assert "rejected because it used a currency" in sent[1]["messages"][1]["content"] or \
        "rejected because it used markdown" in sent[1]["messages"][1]["content"]


def test_reply_prompt_forwards_a_retry_reason_to_the_user_message():
    plain, _, _ = chat_module._reply_prompt("balance?", "balance", None, {"balance": 9000000})
    retry, _, _ = chat_module._reply_prompt("balance?", "balance", None, {"balance": 9000000},
                                            "it used markdown formatting; write plain text")
    assert "rejected because" not in plain[1]["content"]
    assert "Your previous reply was rejected because it used markdown formatting; write plain text. Fix that." \
        in retry[1]["content"]
    assert plain[0] == retry[0]


# --- data-answer prompt --------------------------------------------------------------


def test_reply_prompt_uses_the_global_persona_and_the_answer_purpose():
    messages, data_json, _ = chat_module._reply_prompt("what is my balance", "balance", None, {"balance": 9000000})
    assert messages[0] == {"role": "system", "content": GLOBAL_PERSONA}
    user = messages[1]["content"]
    assert KIND_PURPOSE["answer"] in user
    assert KIND_EXAMPLE["answer"] in user
    assert "Customer: what is my balance" in user
    assert json.loads(data_json) == {"balance": "Tk 90,000.00"}
    assert '"what you know about their account": {"balance": "Tk 90,000.00"}' in user
    assert user.endswith("Reply:")
    # persona rule 2 (copy numbers exactly) travels in the system message
    assert "Copy numbers" in messages[0]["content"]


# --- /chat wiring ------------------------------------------------------------------


def _parse_sse(body):
    events = []
    for block in body.strip("\n").split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((name, data))
    return events


def _result(events):
    return next(d for n, d in events if n == "result")


def _token(events):
    return "".join(d["token"] for n, d in events if n == "token")


@pytest.fixture
def chat_env(monkeypatch):
    """Logged-in customer with a pending nickname confirmation; records bank calls and
    every composer call (kind, facts, message, history)."""
    env = {"fulfills": [], "composed": [], "classified": []}

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        env["fulfills"].append((category, service, payload))
        return AdapterResult(data={"success": True})

    async def fake_classify(message, recent_turns=None):
        env["classified"].append(message)
        return env.get("route") or Clarification(question="What would you like to do?")

    async def recording_compose(kind, facts, *, message="", history=None, must_include=None):
        env["composed"].append({"kind": kind, "facts": facts, "message": message, "history": history,
                                "must": must_include})
        return f"{kind}: " + "; ".join(f"{k}: {v}" for k, v in {**facts, **(must_include or {})}.items())

    async def recording_stream(kind, facts, *, message="", history=None, must_include=None):
        yield await recording_compose(kind, facts, message=message, history=history, must_include=must_include)

    pending = ChatTurn(timestamp=None, message="change my nickname to Rafi", classification={
        "type": "CONFIRMATION_REQUIRED", "category": "profile_update", "service": "update_nickname",
        "subservice": None, "payload": {"nickName": "Rafi"}, "question": "confirm: nickname: Rafi"})
    env["session"] = [pending]

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "compose", recording_compose)
    monkeypatch.setattr(chat_module, "compose_stream", recording_stream)
    monkeypatch.setattr(chat_module, "get_session", lambda customer_id: env["session"])
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [])
    monkeypatch.setattr(chat_module, "record_turn", lambda *a, **k: None)
    return env


def _post(client, message, payload=None):
    body = {"message": message}
    if payload is not None:
        body["payload"] = payload
    resp = client.post("/chat", json=body, headers=JWT_HEADERS)
    assert resp.status_code == 200
    return _parse_sse(resp.text)


def test_confirm_button_executes_the_pending_change(client, chat_env):
    events = _post(client, "Confirm", {"confirm": True})
    assert chat_env["fulfills"] == [("profile_update", "update_nickname", {"nickName": "Rafi"})]
    assert _result(events)["payload"]["executed"] is True
    assert chat_env["composed"][-1]["kind"] == "done"
    assert chat_env["composed"][-1]["must"] == {"nickname": "Rafi"}
    assert chat_env["classified"] == []


def test_cancel_button_never_executes(client, chat_env):
    events = _post(client, "Cancel", {"confirm": False})
    assert chat_env["fulfills"] == []
    assert _result(events)["payload"] == {"executed": False, "cancelled": True}
    assert chat_env["composed"][-1]["kind"] == "declined"


def test_code_typed_at_a_yes_no_step_is_never_executed_nor_shown_to_a_model(client, chat_env, monkeypatch):
    async def never(self, *a, **k):
        raise AssertionError("no model call may see a typed secret")

    monkeypatch.setattr(httpx.AsyncClient, "post", never)
    events = _post(client, "482916")
    assert chat_env["fulfills"] == []
    assert chat_env["classified"] == []
    # The same yes/no is asked again, composed without the typed digits.
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"
    composed = chat_env["composed"][-1]
    assert composed["kind"] == "confirm"
    assert composed["must"] == {"nickname": "Rafi"}
    assert "482916" not in json.dumps(chat_env["composed"])
    assert composed["message"] == "(the customer submitted the secure verification form)"


def test_composer_gets_the_conversation_so_far(client, chat_env):
    _post(client, "Confirm", {"confirm": True})
    assert chat_env["composed"][-1]["history"] == [
        ("Customer", "change my nickname to Rafi"), ("Assistant", "confirm: nickname: Rafi")]
    assert chat_env["composed"][-1]["message"] == "Confirm"


def test_amount_the_customer_never_wrote_is_asked_for_not_used(client, chat_env):
    chat_env["session"] = []
    chat_env["route"] = BankingService("transfer", "wallet_transfer", "bkash",
                                       {"walletNumber": "01812345678", "amount": 3000})
    events = _post(client, "send 5000 to bkash 01812345678")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    asked = chat_env["composed"][-1]
    assert asked["kind"] == "ask"
    assert asked["facts"]["missing"] == [chat_module._CLARIFICATION_FIELD_DESCRIPTIONS["amount"]]
    assert "3000" not in json.dumps(asked)
    assert chat_env["fulfills"] == []


def test_amount_with_a_unit_word_reaches_the_transfer_summary(client, chat_env):
    chat_env["session"] = []
    chat_env["route"] = BankingService("transfer", "wallet_transfer", "bkash",
                                       {"walletNumber": "01812345678", "amount": 50000})
    events = _post(client, "send 50k to bkash 01812345678")
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE"
    assert result["payload"]["amount"] == 50000
    assert result["payload"]["executed"] is False  # never executed in chat
    summary = chat_env["composed"][-1]
    assert summary["kind"] == "summary"
    assert summary["must"] == {"amount": "Tk 50000", "wallet number": "01812345678"}
    assert chat_env["fulfills"] == []
