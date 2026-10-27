import asyncio
import json

import pytest

import app.routes.documents as documents_module
from app.knowledge import product_cards
from app.knowledge.product_cards import ProductCard

from tests.conftest import AUTH_HEADERS

GOOD = {"is_product": True, "kind": " Credit Card ", "summary": "A premium card.",
        "eligibility": ["Resident of Bangladesh", "Age 21 to 65", "", 7],
        "fees": ["Annual fee BDT 5,000"], "rates": [], "benefits": ["Lounge access"],
        "best_for": ["frequent travellers"], "minimum": "BDT 100,000"}


def test_a_good_answer_becomes_a_card_with_cleaned_fields():
    card = product_cards.parse(GOOD, "Visa Infinite", "Cards", "https://x/y")
    assert card.kind == "credit card" and card.name == "Visa Infinite" and card.group == "Cards"
    assert card.eligibility == ["Resident of Bangladesh", "Age 21 to 65", "7"]   # empty dropped, number kept as text
    assert card.minimum == "BDT 100,000" and card.source_url == "https://x/y" and card.rates == []


def test_numbers_the_text_states_are_read_as_numbers_and_nonsense_is_dropped():
    raw = {**GOOD, "min_monthly_income": "40,000", "min_age": 22, "max_age": "60", "min_opening_amount": 50000.0}
    card = product_cards.parse(raw, "Personal Loan", "Loans", None)
    assert (card.min_monthly_income, card.min_age, card.max_age, card.min_opening_amount) == (40000.0, 22, 60, 50000.0)
    bad = {**GOOD, "min_monthly_income": "about forty", "min_age": -3, "max_age": 900, "min_opening_amount": True}
    card = product_cards.parse(bad, "A", "B", None)
    assert (card.min_monthly_income, card.min_age, card.max_age, card.min_opening_amount) == (None, None, None, None)
    assert product_cards.parse(GOOD, "A", "B", None).min_age is None


def test_pages_that_are_not_products_and_unusable_answers_make_no_card():
    assert product_cards.parse({**GOOD, "is_product": False}, "FAQ", "Help", None) is None
    assert product_cards.parse({**GOOD, "is_product": "yes"}, "A", "B", None) is None
    assert product_cards.parse({**GOOD, "kind": ""}, "A", "B", None) is None
    for raw in (None, [], "text", {}):
        assert product_cards.parse(raw, "A", "B", None) is None


def test_lists_are_capped_and_long_items_cut():
    raw = {**GOOD, "benefits": [f"benefit {i} " + "x" * 400 for i in range(20)], "best_for": "not a list"}
    card = product_cards.parse(raw, "A", "B", None)
    assert len(card.benefits) == 8 and all(len(b) <= 220 for b in card.benefits) and card.best_for == []


def test_the_prompt_carries_the_text_as_data_and_is_cut_to_the_setting(monkeypatch):
    monkeypatch.setattr(product_cards.settings, "PRODUCT_CARD_TEXT_CHARS", 50)
    prompt = product_cards.build_prompt("Visa Infinite", "Cards", "a" * 200 + "TAIL")
    assert "Visa Infinite" in prompt and "TAIL" not in prompt and "ignore them" in prompt


def test_chunks_are_grouped_by_product_in_page_order_and_others_are_ignored():
    chunks = [{"product": "A", "group": "G", "text": "second", "chunk_index": 2, "source_url": None},
              {"product": "A", "group": "G", "text": "first", "chunk_index": 1, "source_url": "https://a"},
              {"product": "B", "group": "G", "text": "b text", "chunk_index": 3},
              {"product": None, "group": "G", "text": "orphan", "chunk_index": 4},
              {"product": "C", "group": "G", "text": "", "chunk_index": 5}]
    grouped = product_cards.group_by_product(chunks)
    assert [(g["name"], g["text"], g["source_url"]) for g in grouped] == [("A", "first\n\nsecond", "https://a"),
                                                                           ("B", "b text", None)]


def _fake_model(monkeypatch, answers):
    async def post(path, body, timeout=None):
        name = next(n for n in answers if json.dumps(n) in body["prompt"])
        value = answers[name]
        if isinstance(value, Exception):
            raise value
        return {"response": json.dumps(value)}

    monkeypatch.setattr(product_cards.llm_backend, "post", post)


def test_build_makes_a_card_per_product_and_one_failure_does_not_stop_the_rest(monkeypatch):
    _fake_model(monkeypatch, {"Visa": GOOD, "FAQ": {"is_product": False}, "Loan": RuntimeError("model down")})
    chunks = [{"product": n, "group": "G", "text": "t", "chunk_index": i} for i, n in enumerate(("Visa", "FAQ", "Loan"))]
    cards = asyncio.run(product_cards.build(chunks))
    assert [c.name for c in cards] == ["Visa"]


def test_cards_are_stored_per_document_replaced_and_removed(monkeypatch, tmp_path):
    monkeypatch.setattr(product_cards.settings, "PRODUCT_CARDS_PATH", str(tmp_path / "cards.json"))
    assert product_cards.all_cards() == [] and product_cards.summary() == []
    a, b = ProductCard("A", "G", "card"), ProductCard("B", "G", "loan", rates=["14%"])
    product_cards.save("d1", "f1.md", [a])
    product_cards.save("d2", "f2.md", [b])
    assert {c.name for c in product_cards.all_cards()} == {"A", "B"}
    assert [(s["doc_id"], s["cards"]) for s in product_cards.summary()] == [("d1", 1), ("d2", 1)]
    product_cards.save("d1", "f1.md", [a, ProductCard("A2", "G", "card")])
    assert len(product_cards.all_cards()) == 3
    product_cards.remove("d1")
    product_cards.remove("missing")
    assert [c.name for c in product_cards.all_cards()] == ["B"] and product_cards.all_cards()[0].rates == ["14%"]


# ---- routes ---------------------------------------------------------------------------------------------------------

async def _embed(texts):
    return [[0.1] * 384 for _ in texts]


@pytest.fixture
def docs(client, isolated_catalog, monkeypatch):
    scheduled = []
    monkeypatch.setattr(documents_module, "embed_texts", _embed)
    monkeypatch.setattr(documents_module, "upsert_chunks", lambda *a: None)
    monkeypatch.setattr(documents_module, "delete_by_doc_id", lambda doc_id: None)
    monkeypatch.setattr(documents_module, "_schedule_product_cards",
                        lambda doc_id, filename, chunks: scheduled.append((doc_id, filename, chunks)))
    return scheduled


def _upload(client, name="kb.md"):
    md = b"# Bank\n\n## Cards\n\n### Visa Infinite\n\nA premium card for travellers.\n\nSource: https://x/visa\n"
    return client.post("/documents", headers=AUTH_HEADERS, files={"file": (name, md, "text/markdown")})


def test_an_upload_schedules_the_product_cards_of_what_it_stored(client, docs):
    resp = _upload(client)
    assert resp.status_code == 200 and set(resp.json()) == {"doc_id", "filename", "chunk_count"}
    doc_id, filename, chunks = docs[0]
    assert doc_id == resp.json()["doc_id"] and filename == "kb.md"
    assert any(c.get("product") == "Visa Infinite" and c.get("group") == "Cards" for c in chunks)


def test_replacing_a_document_removes_the_old_documents_cards(client, docs, monkeypatch):
    first = _upload(client).json()["doc_id"]
    product_cards.save(first, "kb.md", [ProductCard("Old", "G", "card")])
    _upload(client)
    assert product_cards.all_cards() == []


def test_deleting_a_document_removes_its_cards(client, docs):
    doc_id = _upload(client).json()["doc_id"]
    product_cards.save(doc_id, "kb.md", [ProductCard("Old", "G", "card")])
    assert client.delete(f"/documents/{doc_id}", headers=AUTH_HEADERS).status_code == 200
    assert product_cards.all_cards() == []


def test_the_cards_listing_and_rebuild_endpoints(client, docs, monkeypatch):
    doc_id = _upload(client).json()["doc_id"]
    docs.clear()
    monkeypatch.setattr(documents_module, "iter_payloads",
                        lambda fields, d: iter([{"product": "Visa Infinite", "group": "Cards", "text": "t"}]))
    resp = client.post(f"/documents/{doc_id}/product-cards", headers=AUTH_HEADERS)
    assert resp.status_code == 202 and resp.json() == {"doc_id": doc_id, "status": "building"}
    assert docs[0][0] == doc_id and docs[0][2][0]["product"] == "Visa Infinite"
    assert client.post("/documents/nope/product-cards", headers=AUTH_HEADERS).status_code == 404
    product_cards.save(doc_id, "kb.md", [ProductCard("Visa Infinite", "Cards", "credit card")])
    listed = client.get("/documents/product-cards", headers=AUTH_HEADERS).json()
    assert [(s["doc_id"], s["cards"]) for s in listed] == [(doc_id, 1)]
    assert client.get("/documents/product-cards").status_code in (401, 403)


SCREENS = {"dps_open": "Open a DPS: open or start a new DPS", "card_apply": "Apply for a card: debit, prepaid or virtual"}


def test_the_screen_answer_is_a_real_screen_id_or_nothing():
    assert product_cards.parse_screen({"screen": "dps_open"}, SCREENS) == "dps_open"
    for raw in ({"screen": "made_up"}, {"screen": None}, {"screen": 5}, {"screen": ["dps_open"]}, {}, None, "dps_open"):
        assert product_cards.parse_screen(raw, SCREENS) is None


def test_the_screen_question_is_small_and_lists_the_screens_from_the_registry():
    card = ProductCard("Goal Based DPS", "Deposit accounts", "deposit account", summary="A monthly savings scheme.")
    prompt = product_cards.build_prompt("Goal Based DPS", "Deposit accounts", "text")
    assert "apply_via" not in prompt                                   # the big extraction no longer asks it
    question = product_cards.screen_prompt(card, SCREENS)
    assert "Goal Based DPS" in question and "dps_open: Open a DPS" in question and "answer null" in question
    from app.banking import ui_actions
    screens = product_cards.application_screens()
    assert set(screens) == set(ui_actions.APPLY_FOR_ACTIONS) and screens["dps_open"].startswith(ui_actions.get("dps_open").name)


def test_extraction_then_one_screen_question_labels_the_card_and_a_failed_question_leaves_it_unlabelled(monkeypatch):
    calls = []

    async def post(path, body, timeout=None):
        calls.append(body["prompt"])
        if "application screens" in body["prompt"]:
            if screens_fail:
                raise RuntimeError("down")
            return {"response": json.dumps({"screen": "dps_open"})}
        return {"response": json.dumps(GOOD)}

    monkeypatch.setattr(product_cards.llm_backend, "post", post)
    monkeypatch.setattr(product_cards, "application_screens", lambda: SCREENS)
    screens_fail = False
    card = asyncio.run(product_cards.extract("Goal Based DPS", "Deposit accounts", "text", None))
    assert card.apply_via == "dps_open" and len(calls) == 2
    screens_fail = True
    card = asyncio.run(product_cards.extract("Goal Based DPS", "Deposit accounts", "text", None))
    assert card is not None and card.apply_via is None
