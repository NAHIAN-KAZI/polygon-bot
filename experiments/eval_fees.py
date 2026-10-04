"""Live fees QA: single questions in every style plus multi-turn conversations.
Prints each customer message, the bot's full reply, the result type and the fee data.
Run inside the backend container with EVAL_API_KEY, EVAL_USERNAME, EVAL_PASSWORD set:
  python -m experiments.eval_fees
"""
import asyncio

import httpx

from experiments.live_freeze_test import chat, login

SINGLE = [
    "fees",
    "bkash charge",
    "bkash e 1000 pathale koto charge",
    "how much does it cost to send 5000 taka to nagad?",
    "rocket fee for 2500",
    "upay te 700 taka pathaile charge koto",
    "What would be the total charge if I transfer 20000 taka to another bank via NPSB?",
    "fee for sending 15000 to my brother's DBBL account",
    "charge for 3000 to another polygon bank account",
    "how much to move 10000 to my own account",
    "is there VAT on a 1000 taka bkash transfer?",
    "cash by code fee for 3000",
    "what are the charges for RTGS 500000",
    "Hello, I'm planning to pay my supplier 75,000 BDT at City Bank tomorrow. Before I do that, could you tell me exactly what fees and VAT I'd be charged?",
    "bkash e 1 lakh pathale koto charge",
    "fee for sending 2.5 lakh to another bank",
    "1 koti taka other bank e pathate koto lagbe",
    "50k nagad fee",
]

CONVERSATIONS = [
    ["fees", "bkash", "1000"],
    ["how much does it cost to send money?", "to nagad", "5000 taka"],
    ["charge koto?", "other bank e 20000"],
    ["what's the charge for 2000", "rocket"],
    ["bkash fee for 500", "and for nagad?", "what about 3000 to nagad"],
    ["I want to know the transfer fee", "to my friend's bank account at BRAC", "50k"],
    ["i want to know about fees of sebding money", "the fees of sending money", "bkash", "2 lakh"],
    ["i want to know the fees of money transfering", "mobile wallet 500 taka",
     "no i want to know about the fee if i send 500 in mobile wallet", "nagad"],
    ["how much is the fee to send money to bkash", "1000", "ok send it"],
]


def describe(r):
    p = r.get("payload") or {}
    if r.get("service") == "fee_quote" and r.get("type") == "BANKING_SERVICE":
        fees = p.get("fees") or {}
        action = (r.get("routing") or {}).get("action")
        return (f"fee_quote principal={p.get('principalAmount')} charge={fees.get('charge')} "
                f"vat={fees.get('vat')} total={p.get('totalAmount')} (poisha) action={action}")
    return f"{r.get('type')} {r.get('category') or ''}/{r.get('service') or ''}".strip()


async def turn(client, token, message):
    text, r = await chat(client, token, message)
    print(f"  Customer: {message}\n  Bot:      {text}\n            [{describe(r)}]\n")


async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        token = await login(client)
        print("=== Single questions ===\n")
        for message in SINGLE:
            await turn(client, token, message)
            await chat(client, token, "ok thanks")  # end the topic before the next one
        print("=== Multi-turn conversations ===\n")
        for i, convo in enumerate(CONVERSATIONS, 1):
            print(f"--- Conversation {i} ---")
            for message in convo:
                await turn(client, token, message)
            await chat(client, token, "ok thanks")


if __name__ == "__main__":
    asyncio.run(main())
