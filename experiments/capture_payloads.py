"""Capture real /chat `result` events for every implemented service, for the
per-intent handoff docs. Run inside the backend container with EVAL_API_KEY,
EVAL_USERNAME, EVAL_PASSWORD set:
  python -m experiments.capture_payloads experiments/results/payloads.json

Read-only services use the direct route (category+service). Conversational flows
stop before anything changes: transfer/dispute summaries never execute, freeze
stops at OTP_REQUIRED (no code submitted), beneficiary add stops at its yes/no.
"""
import asyncio
import json
import sys

import httpx

from experiments.live_freeze_test import API_KEY, CHAT, login

DIRECT = [
    ("account_info", "balance"), ("account_info", "accounts"), ("account_info", "cards"),
    ("account_info", "device_history"), ("account_info", "login_history"),
    ("account_info", "account_transactions"), ("account_info", "fd_profit_history"),
    ("account_info", "dps_profit_history"), ("loan_services", "my_loans"),
    ("polygon_services", "transaction_history"), ("polygon_services", "beneficiary"),
    ("polygon_services", "my_tickets"), ("service_requests", "disputes"),
    ("card_info", "card_limit_requests"), ("card_info", "card_products"),
    ("card_info", "virtual_card_requests"), ("card_info", "replacement_requests"),
    ("card_info", "credit_card_summary"), ("card_info", "credit_card_statement"),
    ("profile", "profile"), ("profile", "address"), ("profile", "contacts"),
    ("profile", "profile_change_requests"), ("profile", "contact_priority_requests"),
    ("transfer_info", "gifts_received"), ("transfer_info", "email_transfers"),
    ("transfer_info", "qr_payment_history"), ("transfer_info", "transfer_limit"),
]

FLOWS = {
    "wallet_transfer": ["send 1500 taka to my bkash 01711223344"],
    "bank_transfer": ["transfer 10000 to my brac bank account 1234567890123"],
    "transfer_clarify": ["send money"],
    "fee_quote": ["bkash e 5000 pathale koto charge"],
    "fee_clarify": ["fees"],
    "raise_dispute": ["I want to raise a dispute: 3000 taka was deducted but never reached my brother, "
                      "account 100126000056, reference TXN123456"],
    "freeze_otp": ["my card was stolen, block it"],
    "freeze_vague": ["my card isnt working"],
    "unfreeze_blocked": ["unfreeze my card"],
    "beneficiary_add": ["add a beneficiary named ClaudeTestDeleteMe, account number 100126000015"],
    "beneficiary_cancel": ["no"],
    "greeting": ["hi"],
    "off_topic": ["who is the prime minister of japan"],
    "kb": ["what is a savings account"],
}


async def post(client, token, body):
    resp = await client.post(CHAT, json=body, timeout=180,
                             headers={"X-API-Key": API_KEY, "Authorization": f"Bearer {token}"})
    events = []
    for block in resp.text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields:
            events.append({"event": fields["event"], "data": json.loads(fields.get("data", "null"))})
    return events


async def main():
    out = {}
    async with httpx.AsyncClient(timeout=60) as client:
        token = await login(client)
        for category, service in DIRECT:
            out[f"{category}/{service}"] = await post(
                client, token, {"message": "show", "category": category, "service": service})
        for name, messages in FLOWS.items():
            for message in messages:
                out[f"flow:{name}"] = await post(client, token, {"message": message})
    with open(sys.argv[1], "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("captured", len(out))


if __name__ == "__main__":
    asyncio.run(main())
