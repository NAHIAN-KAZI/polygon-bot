"""Live beneficiary-add round trip through /chat, then removal of the test record.

Run inside the backend container with EVAL_API_KEY, EVAL_USERNAME, EVAL_PASSWORD set:
  python experiments/live_beneficiary_add_test.py

Adds an obviously fake nickname via the chat flow (ask -> yes/no confirmation ->
add), then soft-deletes every beneficiary carrying that nickname with
DELETE beneficiary/v1/beneficiaries/{id}, so the account is left as it was.
"""
import asyncio
import sys

import httpx

from app.banking.adapters import real
from experiments.live_freeze_test import chat, login, show

NICKNAME = "ClaudeTestDeleteMe"
ACCOUNT = "100126000015"  # a dev test account at Polygon Bank


async def test_records(token):
    body = await real._call("GET", "/beneficiary/v1/beneficiaries", token, params={"page": 0, "size": 100})
    items = body.get("data") if isinstance(body, dict) else body
    if isinstance(items, dict):
        items = items.get("content") or items.get("beneficiaries") or []
    return [b for b in items or [] if isinstance(b, dict) and b.get("nickname") == NICKNAME]


async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        token = await login(client)
        if await test_records(token):
            print("STOP: a test beneficiary already exists; clean it up first")
            return 1

        text, result = await chat(client, token, f"add a beneficiary named {NICKNAME}, account number {ACCOUNT}")
        show("1 ask", text, result)
        if result.get("type") == "CLARIFICATION_REQUIRED":
            text, result = await chat(client, token, f"nickname {NICKNAME}, account {ACCOUNT}")
            show("1b details", text, result)
        if result.get("type") != "CONFIRMATION_REQUIRED":
            print("STOP: never reached CONFIRMATION_REQUIRED; nothing added")
            return 1

        text, result = await chat(client, token, "yes")
        show("2 yes", text, result)

        records = await test_records(token)
        print(f"test beneficiaries now on the account: {len(records)}")
        for record in records:
            await real._call("DELETE", f"/beneficiary/v1/beneficiaries/{record['id']}", token)
        print(f"after cleanup: {len(await test_records(token))}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
