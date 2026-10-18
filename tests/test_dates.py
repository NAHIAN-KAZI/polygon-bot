"""Dates in banking requests: the prompt facts, the cleanup of what the model wrote, the Bangladesh day."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.banking import dates
from app.banking.routing import BankingService, build_system_prompt
from app.routes import chat as chat_module


# --- the date facts the classifier is given ---------------------------------


def test_prompt_states_today_and_the_format():
    line = dates.prompt_today_line(date(2026, 10, 18))
    assert "Sunday, 18 October 2026" in line
    assert "yyyy-MM-dd" in line
    assert "yyyy-MM" in line


def test_system_prompt_carries_todays_date(monkeypatch):
    monkeypatch.setattr(dates, "bank_today", lambda: date(2026, 10, 18))
    prompt = build_system_prompt({"categories": []}, None, True)
    assert "today is Sunday, 18 October 2026" in prompt


def test_bank_day_is_bangladesh_time():
    # 20:00 UTC on the 17th is already the 18th in Dhaka.
    assert dates.BANK_TZ.utcoffset(None) == timedelta(hours=6)
    late = datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc)
    assert late.astimezone(dates.BANK_TZ).date() == date(2026, 10, 18)


# --- calendar facts given to the model -------------------------------------


def test_calendar_facts_for_a_sunday():
    facts = dates.calendar_facts(date(2026, 10, 18))  # a Sunday
    assert facts["yesterday"] == "2026-10-17"
    assert facts["the last 7 days"] == "2026-10-12 to 2026-10-18"
    assert facts["this week"] == "2026-10-12 to 2026-10-18"
    assert facts["last week"] == "2026-10-05 to 2026-10-11"  # the model had said 9 to 13 October
    assert facts["this month"] == "2026-10-01 to 2026-10-18"
    assert facts["last month"] == "2026-09-01 to 2026-09-30"


def test_calendar_facts_cross_the_year_and_start_of_week():
    facts = dates.calendar_facts(date(2026, 1, 5))  # a Monday in early January
    assert facts["yesterday"] == "2026-01-04"
    assert facts["this week"] == "2026-01-05 to 2026-01-05"
    assert facts["last week"] == "2025-12-29 to 2026-01-04"
    assert facts["last month"] == "2025-12-01 to 2025-12-31"


def test_prompt_line_carries_the_facts():
    line = dates.prompt_today_line(date(2026, 10, 18))
    assert "last week is 2026-10-05 to 2026-10-11" in line
    assert "last month is 2026-09" in line


# --- startDate / endDate made safe -------------------------------------------


def test_a_proper_range_is_kept():
    out = dates.normalize_date_range({"startDate": "2026-10-01", "endDate": "2026-10-15"})
    assert out == {"startDate": "2026-10-01", "endDate": "2026-10-15"}


def test_a_lone_date_stays_open_ended_never_a_single_day():
    # "since the 8th" must not shrink to just the 8th; the adapter reads it as 8th through today.
    assert dates.normalize_date_range({"startDate": "2026-10-08"}) == {"startDate": "2026-10-08"}
    assert dates.normalize_date_range({"endDate": "2026-10-08"}) == {"endDate": "2026-10-08"}


def test_a_reversed_range_is_swapped():
    out = dates.normalize_date_range({"startDate": "2026-10-15", "endDate": "2026-10-01"})
    assert out == {"startDate": "2026-10-01", "endDate": "2026-10-15"}


def test_a_timestamp_is_cut_to_its_day():
    out = dates.normalize_date_range({"startDate": "2026-10-05T00:00:00Z", "endDate": "2026-10-06T23:59:59Z"})
    assert out == {"startDate": "2026-10-05", "endDate": "2026-10-06"}


@pytest.mark.parametrize("bad", ["5 October", "yesterday", "2026-13-40", "05/10/2026", "", 5])
def test_an_unreadable_date_is_dropped(bad):
    assert dates.normalize_date_range({"startDate": bad, "endDate": bad}) is None


def test_other_payload_fields_survive():
    out = dates.normalize_date_range({"accountNumber": "111", "startDate": "2026-10-05"})
    assert out == {"accountNumber": "111", "startDate": "2026-10-05"}


def test_no_dates_means_no_change():
    assert dates.normalize_date_range({"accountNumber": "111"}) == {"accountNumber": "111"}
    assert dates.normalize_date_range(None) is None


@pytest.mark.parametrize("raw, expected", [
    ("2026-09", "2026-09"), ("2026-09-15", "2026-09"), ("2026-9", "2026-09"),
    ("2026-13", None), ("September", None), (None, None),
])
def test_statement_month(raw, expected):
    assert dates.normalize_month(raw) == expected


# --- applied to the model's result -------------------------------------------


def _txn(payload):
    return BankingService("polygon_services", "transaction_history", None, payload)


def test_a_since_request_keeps_only_its_start():
    result = chat_module._normalize_dates(_txn({"startDate": "2026-10-08"}))
    assert result.payload == {"startDate": "2026-10-08"}


def test_a_single_day_stays_a_single_day():
    result = chat_module._normalize_dates(_txn({"startDate": "2026-10-05", "endDate": "2026-10-05"}))
    assert result.payload == {"startDate": "2026-10-05", "endDate": "2026-10-05"}


def test_a_bad_date_does_not_become_a_filter():
    result = chat_module._normalize_dates(_txn({"startDate": "last tuesday"}))
    assert result.payload is None  # the plain recent list, not a filter on a made-up date


def test_a_good_result_is_returned_unchanged():
    original = _txn({"startDate": "2026-10-01", "endDate": "2026-10-15"})
    assert chat_module._normalize_dates(original) is original


def test_other_services_are_left_alone():
    other = BankingService("account_info", "balance", None, {"startDate": "garbage"})
    assert chat_module._normalize_dates(other) is other


def test_statement_month_is_normalised():
    stmt = BankingService("card_info", "credit_card_statement", None, {"month": "2026-09-15"})
    assert chat_module._normalize_dates(stmt).payload == {"month": "2026-09"}
    bad = BankingService("card_info", "credit_card_statement", None, {"month": "last month"})
    assert chat_module._normalize_dates(bad).payload is None
