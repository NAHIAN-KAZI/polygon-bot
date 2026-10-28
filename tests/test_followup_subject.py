"""A follow-up like "eta nile" is understood because the last answer's subject is kept and told to the classifier (T-149)."""
from datetime import datetime, timezone

import app.routes.chat as chat_module
from app.banking import routing
from app.banking.session import ChatTurn
from app.llm import build_prompt


def _turn(message, classification):
    return ChatTurn(timestamp=datetime.now(timezone.utc), message=message, classification=classification)


def test_a_knowledge_or_advice_turn_keeps_what_it_was_about():
    assert chat_module._topic_classification("KB_ANSWER", ["Visa Infinite", "Visa Infinite", "Lounge"]) == {
        "type": "KB_ANSWER", "category": None, "service": None, "subservice": None, "topic": ["Visa Infinite", "Lounge"]}
    assert chat_module._topic_classification("KB_ANSWER", []) is None
    assert len(chat_module._topic_classification("ADVICE_ANSWER", ["a", "b", "c", "d"])["topic"]) == 3


def test_the_last_answers_subject_is_found_only_for_a_knowledge_or_advice_turn_with_a_subject():
    kb = _turn("visa infinite card ta niye bolo", {"type": "KB_ANSWER", "topic": ["Polygon Visa Infinite Credit Card"]})
    assert routing._earlier_subject([kb]) == ("visa infinite card ta niye bolo", ["Polygon Visa Infinite Credit Card"])
    assert routing._earlier_subject([_turn("hi", {"type": "KB_ANSWER", "topic": []})]) is None
    assert routing._earlier_subject([_turn("balance", {"type": "BANKING_SERVICE", "topic": ["x"]})]) is None
    assert routing._earlier_subject([_turn("x", None)]) is None and routing._earlier_subject(None) is None


def test_the_note_names_the_subject_and_leaves_new_requests_alone():
    note = routing._subject_note(("tell me about it", ["Polygon Visa Infinite Credit Card"]))
    assert "Polygon Visa Infinite Credit Card" in note and "do not ask what it means" in note and "new request" in note
    assert "answer_kb_question" in note


def test_a_knowledge_answer_is_written_in_the_language_the_customer_wrote_in():
    prompt = build_prompt("q", [{"filename": "k.md", "text": "t"}], language="Bangla, in Bengali script")
    assert "Write the answer in Bangla, in Bengali script." in prompt
    assert "Write the answer in" not in build_prompt("q", [{"filename": "k.md", "text": "t"}])
    assert "Write the answer in English." in build_prompt("q", [], language="English")


def test_the_classifier_is_told_the_subject_of_a_knowledge_answer_and_does_not_think_it_asked_a_question(monkeypatch):
    import asyncio
    import json as _json

    seen = {}

    async def post_classification(messages, **extra):
        seen["messages"] = messages
        return [{"function": {"name": "answer_kb_question", "arguments": _json.dumps({})}}]

    async def domain(message, recent_turns):
        return None

    monkeypatch.setattr(routing, "_post_classification", post_classification)
    monkeypatch.setattr(routing, "_pick_domain", domain)
    last = _turn("visa infinite card ta niye bolo", {"type": "KB_ANSWER", "topic": ["Polygon Visa Infinite Credit Card"]})
    asyncio.run(routing.classify("Amar ki upokar hbe eta nile", recent_turns=[last]))
    text = _json.dumps(seen["messages"], ensure_ascii=False)
    assert "Polygon Visa Infinite Credit Card" in text and "EARLIER IN THIS CHAT" in text
    assert "PENDING CLARIFICATION" not in text
