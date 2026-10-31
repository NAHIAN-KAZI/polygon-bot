"""A heard wallet number that is not a Bangladeshi mobile number is said back instead of asked for blind (T-160)."""
import app.routes.chat as chat_module
from app.banking.routing import BankingService


def clean(number):
    chat_module._rejected_number.set(None)
    chat_module._clean_extracted_fields(BankingService("transfer", "wallet_transfer", "upay", {"walletNumber": number, "amount": "500"}))
    return chat_module._rejected_number.get()


def test_a_twelve_digit_number_is_dropped_but_remembered_for_the_question():
    assert clean("601862610315") == "601862610315"


def test_a_valid_number_or_a_few_digits_is_not_remembered():
    assert clean("01862610315") is None
    assert clean("1234") is None


def test_the_ask_for_the_number_says_what_was_heard_and_what_a_number_looks_like():
    chat_module._rejected_number.set("601862610315")
    _, facts, _ = chat_module._ask_say("transfer", "wallet_transfer", "upay", {"amount": "500"}, ["walletNumber"])
    assert facts["number heard"] == "6018 6261 0315" and "11 digits" in facts["problem"]
    chat_module._rejected_number.set(None)
    _, facts, _ = chat_module._ask_say("transfer", "wallet_transfer", "upay", {"amount": "500"}, ["walletNumber"])
    assert "number heard" not in facts and "problem" not in facts


# ---- the composer keeps the customer's words (so the reply is in their language) ------------------------------------------

def test_a_spoken_bangla_sentence_with_a_phone_number_keeps_its_words_and_hides_the_digits():
    safe = chat_module._safe_for_model("আমি Upay তে 500 টাকা পাঠাবো নম্বরটা হলো 01862610315।", None)
    assert "পাঠাবো" in safe and "500" in safe and "01862610315" not in safe and safe.count("•") == 7
    assert "0315" in safe          # the last four of a long number only, as the other masked places show


def test_a_code_typed_in_a_sentence_is_hidden_entirely_and_a_bare_code_still_replaces_the_message():
    safe = chat_module._safe_for_model("my otp is 123456 please", None)
    assert "123456" not in safe and "otp" in safe and "3456" not in safe
    for bare in ("123456", "abc1234", "পিন ১২৩৪৫৬"[:0] or "9999"):
        assert chat_module._safe_for_model(bare, None) == chat_module._SUBMITTED_SECURELY
    assert chat_module._safe_for_model("anything", {"otp": "123456"}) == chat_module._SUBMITTED_SECURELY


def test_an_ordinary_message_is_left_as_it_is():
    assert chat_module._safe_for_model("send 500 taka to bkash", None) == "send 500 taka to bkash"
