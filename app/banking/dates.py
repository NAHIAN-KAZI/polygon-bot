"""Dates for banking requests: the bank's calendar day, and the date fields a customer's message fills.

The assistant works in Bangladesh time. A transaction at 02:00 on the 5th (BST) is 20:00 on the 4th
in UTC, so a "show the 5th" request has to cut the day at BST midnight, not UTC midnight.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Bangladesh Standard Time. No daylight saving is in use.
BANK_TZ = timezone(timedelta(hours=6))


def bank_today() -> date:
    return datetime.now(BANK_TZ).date()


_MONTH_NUMBERS = ", ".join(
    f"{name} {number:02d}"
    for number, name in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August", "September",
         "October", "November", "December"],
        start=1,
    )
)


def calendar_facts(today: date) -> dict[str, str]:
    """Date arithmetic done in code, so the model reads it instead of calculating it.

    The model got "last week" wrong (a five-day span, off by a week) when left to work it out from
    today's date. Weeks run Monday to Sunday.
    """
    monday = today - timedelta(days=today.weekday())
    first_of_month = today.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return {
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "the last 7 days": f"{(today - timedelta(days=6)).isoformat()} to {today.isoformat()}",
        "this week": f"{monday.isoformat()} to {today.isoformat()}",
        "last week": f"{(monday - timedelta(days=7)).isoformat()} to {(monday - timedelta(days=1)).isoformat()}",
        "this month": f"{first_of_month.isoformat()} to {today.isoformat()}",
        "last month": f"{last_month_start.isoformat()} to {last_month_end.isoformat()}",
    }


def prompt_today_line(today: date | None = None) -> str:
    """The date facts the classifier needs to turn "yesterday" or "5 October" into a real date.

    It states facts and conventions only; the model still reads the customer's own words.
    """
    today = today or bank_today()
    facts = "; ".join(f"{name} is {value}" for name, value in calendar_facts(today).items())
    return (
        f"- Dates: today is {today:%A}, {today.day} {today:%B %Y} (Bangladesh time). Write every date "
        "in a payload as yyyy-MM-dd; a statement month as yyyy-MM "
        f"(this month is {today:%Y-%m}, last month is {calendar_facts(today)['last month'][:7]}). "
        f"Calendar facts: {facts}. Month numbers: {_MONTH_NUMBERS}. A day named without a year is "
        "its most recent past occurrence; the number next to a month name is the day, never the month. "
        "One day means startDate and endDate are that same date; \"since X\" or \"from X\" gives only "
        "startDate; \"until X\" gives only endDate. Leave dates out when the customer named none.\n"
    )


def parse_day(value: object) -> date | None:
    """A strict yyyy-MM-dd (a longer timestamp is cut to its date); anything else is None."""
    if value is None:
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def normalize_date_range(payload: dict | None) -> dict | None:
    """startDate/endDate made valid, or dropped.

    Each must be a real yyyy-MM-dd date. A reversed pair is swapped. A date on one side only stays
    one-sided: it is an open range ("since the 8th" is the 8th through today, "until the 8th" is
    everything up to it), which the adapter reads that way. Widening it would be safer than
    narrowing it, so a lone date is never turned into a single day. Nothing usable leaves the
    payload without the keys, so the customer gets the plain recent list rather than a wrong filter.
    """
    if not payload:
        return payload
    out = {k: v for k, v in payload.items() if k not in ("startDate", "endDate")}
    start = parse_day(payload.get("startDate"))
    end = parse_day(payload.get("endDate"))
    if start is not None and end is not None and start > end:
        start, end = end, start
    if start is not None:
        out["startDate"] = start.isoformat()
    if end is not None:
        out["endDate"] = end.isoformat()
    return out or None


def normalize_month(value: object) -> str | None:
    """A yyyy-MM month (a full date is cut to its month); anything else is None."""
    if value is None:
        return None
    text = str(value).strip()[:7]
    try:
        year, month = text.split("-")
        if len(year) == 4 and 1 <= int(month) <= 12:
            return f"{int(year):04d}-{int(month):02d}"
    except ValueError:
        pass
    return None
