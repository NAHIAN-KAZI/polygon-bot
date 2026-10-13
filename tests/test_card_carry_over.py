"""A card chosen in one turn ("2nd ta" -> card 0277) is reused when the next message is about
that same card ("freeze kore den") instead of asking again. The model reads whether it is the
same card; the model call is mocked and nothing reaches a network."""
import asyncio
import json
from datetime import datetime, timezone

import app.routes.chat as chat_module
from app.banking.session import ChatTurn


def _turns(request):
    return [ChatTurn(timestamp=datetime.now(timezone.utc), message="2nd ta",
                     classification={"type": "BANKING_SERVICE", "selected_card": request})]


def _model_says(monkeypatch, answer):
    async def post(path, body, timeout=None):
        return {"response": json.dumps(answer)}
    monkeypatch.setattr(chat_module.llm_backend, "post", post)


def test_same_card_is_carried_over(monkeypatch):
    _model_says(monkeypatch, {"same_card": True})
    got = asyncio.run(chat_module._card_from_last_turn(
        "freeze kore den", _turns({"cardId": 7, "cardLast4": "0277"})))
    assert got == {"cardId": 7, "cardLast4": "0277"}


def test_other_card_is_not_carried_over(monkeypatch):
    _model_says(monkeypatch, {"same_card": False})
    assert asyncio.run(chat_module._card_from_last_turn(
        "freeze my other card", _turns({"cardId": 7, "cardLast4": "0277"}))) is None


def test_nothing_to_carry_when_last_turn_had_no_card(monkeypatch):
    _model_says(monkeypatch, {"same_card": True})
    assert asyncio.run(chat_module._card_from_last_turn("freeze it", _turns({}))) is None
    assert asyncio.run(chat_module._card_from_last_turn("freeze it", [])) is None


def test_model_failure_asks_again(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(chat_module.llm_backend, "post", boom)
    assert asyncio.run(chat_module._card_from_last_turn(
        "freeze it", _turns({"cardId": 7, "cardLast4": "0277"}))) is None
