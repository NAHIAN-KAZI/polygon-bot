"""T-77: app/conversation/composer.py -- every customer-facing message is written by the
model from structured facts, and made safe by validation, not fixed sentences.

The composer is tested directly here (conftest only fakes it at its app.routes.chat
import site). Ollama is never reached: httpx.AsyncClient.post / .stream are patched.
"""
import asyncio
import json

import httpx
import pytest

from app.conversation import composer
from app.conversation.composer import (
    _find_value,
    _label_kept,
    build_messages,
    check_reply,
    compose,
    compose_stream,
    facts_listing,
    generate_chat,
    unsupported_numbers,
)
from app.conversation.persona import GLOBAL_PERSONA, KIND_EXAMPLE, KIND_PURPOSE, LLM_DOWN_MESSAGE


# --- httpx fakes ----------------------------------------------------------------


class _Resp:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"role": "assistant", "content": self._text}}


def _model_replies(monkeypatch, *replies):
    """Each /api/chat call returns the next reply; an Exception instance is raised.
    Returns the list of request bodies sent."""
    queue = list(replies)
    sent = []

    async def fake_post(self, url, *args, **kwargs):
        sent.append(kwargs.get("json"))
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _Resp(reply)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return sent


class _Stream:
    def __init__(self, pieces, fail=None):
        self._lines = [json.dumps({"message": {"content": p}, "done": False}) for p in pieces]
        self._lines.append(json.dumps({"message": {"content": ""}, "done": True}))
        self._fail = fail

    async def __aenter__(self):
        if self._fail:
            raise self._fail
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _stream_replies(monkeypatch, pieces, fail=None):
    sent = []

    def fake_stream(self, method, url, **kwargs):
        sent.append(kwargs.get("json"))
        return _Stream(pieces, fail)

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    return sent


def _run(coro):
    return asyncio.run(coro)


def _collect(gen):
    async def go():
        return [piece async for piece in gen]
    return asyncio.run(go())


# --- check_reply ------------------------------------------------------------------


def test_check_reply_accepts_a_reply_with_every_exact_value_attached_to_its_label():
    text = "Just to confirm: you'd like to freeze your card ending 0293. Shall I go ahead?"
    assert check_reply(text, "{}", {"card ending": "0293"}) is None


def test_check_reply_rejects_a_missing_exact_value():
    reason = check_reply("Shall I freeze your card?", "{}", {"card ending": "0293"})
    assert reason == 'it did not include the exact value "0293" (card ending)'


def test_check_reply_rejects_a_value_detached_from_its_label():
    # A card ending must never turn into "phone number 0293".
    reason = check_reply("Phone number 0293 is on file for your card.", "{}", {"card ending": "0293"})
    assert reason == '"0293" must stay attached to "card ending"'


def test_check_reply_accepts_an_amount_written_with_separators_or_spacing():
    must = {"amount": "Tk 5000"}
    assert check_reply("You're sending an amount of Tk 5,000 today.", "{}", must) is None
    assert check_reply("The amount is 5000 taka.", "{}", must) is None


def test_check_reply_rejects_numbers_not_in_the_facts():
    reason = check_reply("Your card ending 0293 has a limit of Tk 75,000.", '{"card": "0293"}',
                         {"card ending": "0293"})
    assert reason == "it contained numbers that are not in the facts: 75,000"


def test_check_reply_ignores_short_numbers_and_accepts_numbers_from_the_facts():
    assert check_reply("You have 2 cards; balance Tk 1,250.", '{"balance": "Tk 1250"}', {}) is None


def test_check_reply_rejects_dollars():
    assert check_reply("Your balance is $500.", '{"balance": 500}', {}) == "it used a currency other than Tk"


@pytest.mark.parametrize("text", [
    "Your balance is €500.", "That costs £20.", "It is ₹300.", "You pay 5 USD for that.", "About 10 EUR.",
])
def test_check_reply_rejects_any_foreign_currency(text):
    assert check_reply(text, '{"fee": "5"}', {}) == "it used a currency other than Tk"


@pytest.mark.parametrize("text", [
    "**Your balance** is Tk 500.",
    "Here you go:\n- Savings Tk 500\n- Current Tk 200",
    "Here you go:\n* Savings Tk 500",
    "# Balance\nTk 500",
])
def test_check_reply_rejects_markdown(text):
    assert check_reply(text, '{"a": "500", "b": "200"}', {}) == "it used markdown formatting; write plain text"


def test_check_reply_allows_hyphens_and_asterisks_inside_a_sentence():
    assert check_reply("Your e-mail is a-b@c.com - noted * thanks.", '{"x": "a-b@c.com"}', {}) is None


def test_check_reply_rejects_an_unmasked_long_number_not_in_the_facts():
    reason = check_reply("Your account 100126000056 has Tk 500.", '{"balance": "Tk 500"}', {})
    assert reason == "it contained a long number that is not in the facts"


def test_check_reply_accepts_masked_numbers_and_long_runs_that_are_in_the_facts():
    facts = '{"account": "••••••••1234", "balance": "Tk 500"}'
    assert check_reply("Your account ••••••••1234 has Tk 500.", facts, {}) is None
    # a masked form whose last digits aren't in the facts is still an unsupported number
    assert check_reply("Your account ••••••••9999 has Tk 500.", facts, {}) is not None
    assert check_reply("Reference 20260105123456 was paid.", '{"ref": "20260105123456"}', {}) is None
    assert check_reply("Reference 20260105123456 was paid.", "{}", {"reference": "20260105123456"}) is None


def test_check_reply_non_amount_values_must_be_verbatim():
    # "57 Lake Road" shares digits with "House 5, Road 7" but is not that address.
    must = {"present address": "House 5, Road 7"}
    assert check_reply("Your present address will be 57 Lake Road.", "{}", must) is not None
    assert check_reply("Your present address will be House 5, Road 7.", "{}", must) is None


def test_check_reply_amount_with_cents_is_accepted_against_a_whole_amount():
    assert check_reply("The amount is Tk 5,000.00.", "{}", {"amount": "Tk 5000"}) is None


def test_check_reply_rejects_empty_and_overlong_replies():
    assert check_reply("", "{}", {}) == "the reply was empty"
    assert check_reply("a" * 901, "{}", {}) == "the reply was too long"
    assert check_reply("a" * 900, "{}", {}) is None


def test_unsupported_numbers_ignores_thousands_separators():
    assert unsupported_numbers("Tk 90,000.00 then 31,000", '{"balance": "90000.00"}') == ["31,000"]


def test_find_value_and_label_kept():
    assert _find_value("Tk 5000", "send Tk 5,000 now") == "5,000"
    assert _find_value("0293", "no digits here") is None
    assert _label_kept("card ending", "0293", "your card ••0293")
    assert not _label_kept("card ending", "0293", "0293 is your phone")


# --- facts_listing / build_messages ---------------------------------------------------


def test_facts_listing_is_plain_label_value_lines_skipping_empties():
    listing = facts_listing({"what": "card frozen", "options": ["a", "b"], "none": None, "empty": ""})
    assert listing == "what: card frozen\noptions: a; b"


def test_facts_listing_with_nothing_to_say_is_the_down_message():
    assert facts_listing({"x": None}) == LLM_DOWN_MESSAGE


def _user(messages):
    assert [m["role"] for m in messages] == ["system", "user"]
    return messages[1]["content"]


def test_build_messages_shape_system_persona_then_one_user_message():
    messages = build_messages("confirm", {"change": "freeze the card", "empty": None}, "freeze it",
                              [("Customer", "hi")], {"card ending": "0293"})
    assert messages[0] == {"role": "system", "content": GLOBAL_PERSONA}
    user = _user(messages)
    assert user.startswith("Here is an example of this kind of message (different facts):\n"
                           + KIND_EXAMPLE["confirm"])
    assert "Now the real one." in user
    assert f"Your task: {KIND_PURPOSE['confirm']}" in user
    assert 'Include, in your own words but with exact values:' in user
    assert '- card ending: 0293  (write "0293" exactly)' in user
    assert "- change: freeze the card" in user  # confirm mentions every fact
    assert "- empty" not in user
    assert "Customer: hi" in user
    assert "rejected because" not in user
    assert GLOBAL_PERSONA not in user


def test_build_messages_order_example_then_customer_then_facts_then_task_then_reply():
    user = _user(build_messages("answer", {"balance": "Tk 500"}, "what is my balance",
                                [("Assistant", "earlier")], {}))
    marks = [user.index(x) for x in (
        "Here is an example", "Now the real one.", "Conversation so far:",
        "Customer: what is my balance", 'Facts (JSON): {"balance": "Tk 500"}', "Your task:")]
    assert marks == sorted(marks)
    assert user.endswith("Reply:")
    assert "Include, in your own words" not in user  # nothing exact to include


@pytest.mark.parametrize("kind", sorted(KIND_PURPOSE))
def test_build_messages_every_kind_carries_its_own_example_and_purpose(kind):
    user = _user(build_messages(kind, {"x": "y"}, "hello", None, {}))
    assert KIND_EXAMPLE[kind] in user
    assert KIND_PURPOSE[kind] in user
    assert user.endswith("Reply:")


def test_build_messages_unknown_kind_falls_back_to_answer_and_names_the_retry_reason():
    user = _user(build_messages("no_such_kind", {}, "", None, {},
                                retry_reason="it used a currency other than Tk"))
    assert KIND_PURPOSE["answer"] in user and KIND_EXAMPLE["answer"] in user
    assert "Your previous reply was rejected because it used a currency other than Tk. Fix that." in user
    assert user.index("rejected because") < user.index("Your task:")


def test_every_purpose_has_an_example_and_examples_are_plain_tk_text():
    assert set(KIND_EXAMPLE) == set(KIND_PURPOSE)
    for kind, example in KIND_EXAMPLE.items():
        assert example.strip(), kind
        # the examples must pass the same checks a real reply has to pass
        assert composer._MARKDOWN_RE.search(example) is None, kind
        assert not any(sym in example for sym in composer._FOREIGN_CURRENCY), kind
        assert composer._UNMASKED_RE.search(example) is None, kind


def test_build_messages_masks_long_digit_runs_in_message_and_history():
    messages = build_messages("answer", {}, "my account 100126000056",
                              [("Customer", "card 4001230000000251")], {})
    everything = json.dumps(messages, ensure_ascii=False)
    assert "100126000056" not in everything and "4001230000000251" not in everything
    assert "••••••••0056" in everything and "••••••••••••0251" in everything


def test_build_messages_for_a_missing_message_still_ends_with_reply():
    assert _user(build_messages("greet", {}, "", None, {})).endswith("Reply:")


# --- compose ----------------------------------------------------------------------


def test_compose_returns_the_first_reply_that_passes(monkeypatch):
    sent = _model_replies(monkeypatch, "Your card ending 0293 is now frozen.")
    out = _run(compose("done", {"what": "the card was frozen"}, must_include={"card ending": "0293"}))
    assert out == "Your card ending 0293 is now frozen."
    assert len(sent) == 1
    assert sent[0]["options"]["temperature"] == 0.1


def test_compose_retries_once_at_temperature_zero_with_the_reason(monkeypatch):
    sent = _model_replies(monkeypatch, "Your card is frozen.", "Your card ending 0293 is now frozen.")
    out = _run(compose("done", {"what": "the card was frozen"}, must_include={"card ending": "0293"}))
    assert out == "Your card ending 0293 is now frozen."
    assert len(sent) == 2
    assert sent[1]["options"]["temperature"] == 0.0
    assert 'rejected because it did not include the exact value "0293"' in sent[1]["messages"][1]["content"]


def test_compose_falls_back_to_the_facts_when_both_attempts_fail(monkeypatch):
    _model_replies(monkeypatch, "Your balance is $5.", "Your balance is Tk 999,999.")
    out = _run(compose("answer", {"balance": "Tk 500"}, must_include={"account ending": "0056"}))
    assert out == "balance: Tk 500\naccount ending: 0056"


def test_compose_unreachable_model_is_the_one_fixed_message(monkeypatch):
    _model_replies(monkeypatch, httpx.ConnectError("down"))
    assert _run(compose("answer", {"balance": "Tk 500"})) == LLM_DOWN_MESSAGE


def test_compose_model_down_on_the_retry_is_also_the_fixed_message(monkeypatch):
    _model_replies(monkeypatch, "Your balance is $5.", httpx.ReadTimeout("slow"))
    assert _run(compose("answer", {"balance": "Tk 500"})) == LLM_DOWN_MESSAGE


def test_compose_drops_empty_must_include_values(monkeypatch):
    _model_replies(monkeypatch, "Okay, nothing was changed.")
    out = _run(compose("declined", {"what": "x"}, must_include={"card ending": None, "nickname": ""}))
    assert out == "Okay, nothing was changed."


def test_compose_strips_quotes_around_the_reply(monkeypatch):
    _model_replies(monkeypatch, '  "Hello there!"  ')
    assert _run(compose("greet", {})) == "Hello there!"


# --- compose_stream ---------------------------------------------------------------


def test_compose_stream_yields_whole_sentences(monkeypatch):
    _stream_replies(monkeypatch, ["Your card ending 02", "93 is frozen. ", "You can ", "unfreeze it."])
    out = _collect(compose_stream("done", {"what": "frozen"}, must_include={"card ending": "0293"}))
    assert out == ["Your card ending 0293 is frozen.", " You can unfreeze it."]


def test_compose_stream_appends_a_missing_exact_value_as_data(monkeypatch):
    _stream_replies(monkeypatch, ["Your card is frozen now. ", "Anything else?"])
    out = _collect(compose_stream("done", {"what": "frozen"}, must_include={"card ending": "0293"}))
    assert "".join(out) == "Your card is frozen now. Anything else?\nCard ending: 0293"


def test_compose_stream_stops_before_an_unsupported_number_and_keeps_exact_values(monkeypatch):
    _stream_replies(monkeypatch, ["Your transfer is ready. ", "The fee is Tk 999", " today."])
    out = "".join(_collect(compose_stream("summary", {"what": "x"}, must_include={"amount": "Tk 5000"})))
    assert "999" not in out
    assert out == "Your transfer is ready.\nAmount: Tk 5000"


def test_compose_stream_bad_first_sentence_uses_the_checked_non_streamed_path(monkeypatch):
    _stream_replies(monkeypatch, ["You'll pay $5. ", "Okay."])
    _model_replies(monkeypatch, "Your fee is Tk 5.")
    out = _collect(compose_stream("answer", {"fee": "Tk 5"}))
    assert out == ["Your fee is Tk 5."]


def test_compose_stream_unreachable_model_is_the_fixed_message(monkeypatch):
    _stream_replies(monkeypatch, [], fail=httpx.ConnectError("down"))
    _model_replies(monkeypatch, httpx.ConnectError("down"))
    assert _collect(compose_stream("answer", {"x": "y"})) == [LLM_DOWN_MESSAGE]


def test_compose_stream_empty_stream_falls_back_to_compose(monkeypatch):
    _stream_replies(monkeypatch, [])
    _model_replies(monkeypatch, "Hi Rafi!")
    assert _collect(compose_stream("greet", {"name": "Rafi"})) == ["Hi Rafi!"]


@pytest.mark.parametrize("kind", sorted(KIND_PURPOSE))
def test_every_kind_has_a_purpose_not_a_sentence_to_copy(kind):
    # Purposes describe what to do; the persona owns the wording.
    assert KIND_PURPOSE[kind] and '"' not in KIND_PURPOSE[kind]


def test_max_tokens_is_capped(monkeypatch):
    sent = _model_replies(monkeypatch, "Hello!")
    _run(compose("greet", {}))
    assert sent[0]["options"]["num_predict"] == composer._MAX_TOKENS == 400
    assert sent[0]["messages"][0] == {"role": "system", "content": GLOBAL_PERSONA}


def test_check_reply_non_amount_value_must_be_verbatim():
    """A free-text value (address) is never matched by its digits alone."""
    reply = "Your present address will be 57 Lake Road."
    assert check_reply(reply, "{}", {"present address": "House 5, Road 7"}) is not None


def test_check_reply_amount_with_trailing_zeros_is_supported():
    """The same amount written "5,000.00" passes both the exact-value and number checks."""
    assert check_reply("The amount is Tk 5,000.00 in total.", '{"amount": "Tk 5000"}', {"amount": "Tk 5000"}) is None


# --- generate_chat ------------------------------------------------------------------


MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_generate_chat_posts_to_api_chat_and_reads_message_content(monkeypatch):
    seen = {}

    async def fake_post(self, url, *args, **kwargs):
        seen["url"], seen["json"] = url, kwargs["json"]
        return _Resp('  "Hello there"  ')

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert _run(generate_chat(MESSAGES, 0.3)) == "Hello there"
    assert seen["url"].endswith("/api/chat")
    assert seen["json"]["messages"] == MESSAGES
    assert seen["json"]["stream"] is False
    assert seen["json"]["options"]["temperature"] == 0.3
    assert seen["json"]["options"]["num_predict"] == 400
    assert "prompt" not in seen["json"]


@pytest.mark.parametrize("body", [{}, {"message": None}, {"message": {}}, {"message": {"content": None}}])
def test_generate_chat_missing_content_is_empty_text(monkeypatch, body):
    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return body

    async def fake_post(self, url, *args, **kwargs):
        return R()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert _run(generate_chat(MESSAGES, 0.0)) == ""


@pytest.mark.parametrize("error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow"), ValueError("bad body")])
def test_generate_chat_returns_none_when_the_model_fails(monkeypatch, error):
    _model_replies(monkeypatch, error)
    assert _run(generate_chat(MESSAGES, 0.1)) is None


def test_generate_chat_http_error_status_is_none(monkeypatch):
    class R:
        def raise_for_status(self):
            raise httpx.HTTPStatusError("500", request=None, response=None)

    async def fake_post(self, url, *args, **kwargs):
        return R()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert _run(generate_chat(MESSAGES, 0.1)) is None


def test_compose_stream_posts_messages_to_api_chat(monkeypatch):
    urls = []

    def fake_stream(self, method, url, **kwargs):
        urls.append((url, kwargs["json"]))
        return _Stream(["Hello!"])

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    assert _collect(compose_stream("greet", {})) == ["Hello!"]
    url, body = urls[0]
    assert url.endswith("/api/chat")
    assert body["messages"][0]["content"] == GLOBAL_PERSONA and body["stream"] is True


def test_compose_stream_stops_on_a_foreign_currency_symbol(monkeypatch):
    _stream_replies(monkeypatch, ["Your fee is €5. ", "Okay."])
    _model_replies(monkeypatch, "Your fee is Tk 5.")
    assert _collect(compose_stream("answer", {"fee": "Tk 5"})) == ["Your fee is Tk 5."]
