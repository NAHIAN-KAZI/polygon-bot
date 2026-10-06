"""Live card-freeze round trip through /chat, then an immediate unfreeze.

Run inside the backend container (needs app.* and network access to the bank's dev
platform), with EVAL_API_KEY, EVAL_USERNAME, EVAL_PASSWORD set:
  python experiments/live_freeze_test.py

Stops without freezing anything if the dev OTP service rejects the fixed test code
"0000" (that would mean real SMS codes are in use). Every freeze it causes is undone
in the same run via PATCH card/v1/cards/{id}/unfreeze.
"""
import asyncio
import json
import os
import sys

import httpx

from app.banking.adapters import real
from app.banking.identity import verify_jwt

CHAT = os.environ.get("EVAL_CHAT_URL", "http://localhost:8000/chat")
LOGIN = "https://internet-banking.dev-polygontech.xyz/auth/v1/auth/login"
API_KEY = os.environ.get("EVAL_API_KEY") or os.environ["API_KEY"]
USERNAME = os.environ["EVAL_USERNAME"]
PASSWORD = os.environ["EVAL_PASSWORD"]
TEST_OTP = "0000"


async def login(client):
    resp = await client.post(LOGIN, json={"username": USERNAME, "password": PASSWORD},
                             headers={"User-Agent": "curl/8.5.0"})
    resp.raise_for_status()
    return resp.json()["token"]["accessToken"]


async def chat(client, token, message, payload=None):
    body = {"message": message}
    if payload is not None:
        body["payload"] = payload
    resp = await client.post(CHAT, json=body, timeout=180,
                             headers={"X-API-Key": API_KEY, "Authorization": f"Bearer {token}"})
    text, result = "", {}
    for block in resp.text.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if lines.get("event") == "token":
            text += json.loads(lines["data"]).get("token", "")
        elif lines.get("event") == "result":
            result = json.loads(lines["data"])
    return text, result


def show(label, text, result):
    payload = {k: v for k, v in (result.get("payload") or {}).items() if k not in ("otp", "pin", "password")}
    print(f"{label}: {result.get('type')} {payload}\n   bot: {text[:220]}")


async def card_status(token, card_id):
    body = await real._call("GET", "/card/v1/cards", token)
    cards = body.get("data") if isinstance(body, dict) else body
    if isinstance(cards, dict):
        cards = cards.get("cards") or cards.get("content") or []
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        if str(card.get("id")) == str(card_id):
            return card.get("status")
    return None


async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        token = await login(client)
        identity = await verify_jwt(token)

        text, result = await chat(client, token, "my debit card was stolen, please freeze it")
        show("1 ask", text, result)
        if result.get("type") == "ACCOUNT_SELECTION_REQUIRED":
            first = (result.get("payload") or {}).get("accounts", [{}])[0]
            text, result = await chat(client, token, str(first.get("cardNumber", ""))[-4:])
            show("1b pick", text, result)
        if result.get("type") == "CLARIFICATION_REQUIRED":
            text, result = await chat(client, token, "it was stolen")
            show("1c reason", text, result)
        if result.get("type") != "OTP_REQUIRED":
            print("STOP: freeze flow never reached OTP_REQUIRED")
            return 1

        card_id = (result.get("payload") or {}).get("cardId")
        print(f"card {card_id} status before: {await card_status(token, card_id)}")

        text, result = await chat(client, token, "submit", {"otp": TEST_OTP, "password": PASSWORD})
        show("2 submit", text, result)
        status = await card_status(token, card_id)
        print(f"card {card_id} status after freeze step: {status}")
        if result.get("type") == "OTP_REQUIRED":
            print("STOP: test OTP rejected -- dev may be sending real SMS codes. Nothing frozen.")
            return 1

        # Restore: fresh OTP -> verificationToken -> unfreeze (not available in chat by design).
        await real.send_otp(identity.customer_id)
        verification_token = await real.verify_otp(identity.customer_id, TEST_OTP)
        await real._call("PATCH", f"/card/v1/cards/{card_id}/unfreeze", token,
                         json={"verificationToken": verification_token, "password": PASSWORD})
        print(f"card {card_id} status after unfreeze: {await card_status(token, card_id)}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
