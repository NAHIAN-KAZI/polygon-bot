"""Transfer understanding probe (gather only: nothing is ever sent). Random account/phone numbers and
amounts in many phrasings; checks the type the bot picks and that the number and amount are prefilled.
Run in the backend container with EVAL_* set:  python -m experiments.transfer_probe"""
import asyncio
import json
import os
import random
import re

import httpx

os.environ.setdefault("EVAL_API_KEY", os.environ.get("API_KEY", ""))
from experiments.live_freeze_test import chat, login  # noqa: E402

rng = random.Random(int(os.environ.get("SEED", "7")))
phone = lambda: "01" + rng.choice("3456789") + "".join(rng.choice("0123456789") for _ in range(8))
acct = lambda n=13: "".join(rng.choice("0123456789") for _ in range(n))
AMOUNTS = [("500", 500), ("1,250", 1250), ("5k", 5000), ("2 lakh", 200000), ("750 taka", 750), ("20000", 20000), ("1.5k", 1500)]
WALLETS = ["bkash", "nagad", "rocket", "upay"]
BANKS = ["DBBL", "BRAC Bank", "City Bank", "Islami Bank", "Sonali Bank", "EBL"]


def cases():
    out = []
    for _ in range(2):
        for w in WALLETS:
            p, (a, v) = phone(), rng.choice(AMOUNTS)
            for t in (f"send {a} to {w} {p}", f"{w} e {a} pathao {p}", f"transfer {a} taka to my {w} number {p}",
                      f"i want to send {p} {w} {a}"):
                out.append((t, ("wallet_transfer", w), {"walletNumber": p, "amount": v}))
    for _ in range(3):
        b, ac, (a, v) = rng.choice(BANKS), acct(), rng.choice(AMOUNTS)
        for t in (f"send {a} to account {ac} at {b}", f"transfer {a} to {b} account number {ac}",
                  f"i need to send money to another bank, {b}, account {ac}, amount {a}"):
            out.append((t, ("bank_transfer", "other_bank"), {"accountNumber": ac, "amount": v}))
    for _ in range(3):
        ac, (a, v) = "1001260" + acct(5), rng.choice(AMOUNTS)
        for t in (f"send {a} to Polygon Bank account {ac}", f"transfer {a} to another polygon bank account {ac}"):
            out.append((t, ("bank_transfer", "city_account"), {"accountNumber": ac, "amount": v}))
    for t in ("move 3000 from my savings to my other account", "transfer 5k between my own accounts"):
        out.append((t, ("bank_transfer", "own_account"), {}))
    for t in ("I want to transfer money", "send money", "send 500 taka"):
        out.append((t, ("ASK", None), {}))
    return out


async def main():
    results = []
    async with httpx.AsyncClient(timeout=120) as client:
        token = await login(client)
        for msg, (svc, sub), want in cases():
            text, r = await chat(client, token, msg)
            if r.get("type") == "AUTH_REQUIRED":
                token = await login(client); text, r = await chat(client, token, msg)
            payload = r.get("payload") or {}
            got = (r.get("service"), r.get("subservice"))
            if svc == "ASK":
                ok_route = r.get("type") in ("CLARIFICATION_REQUIRED", "ACCOUNT_SELECTION_REQUIRED") or (r.get("service") in ("bank_transfer", "wallet_transfer") and not r.get("subservice"))
            else:
                ok_route = got == (svc, sub) or (r.get("type") == "CLARIFICATION_REQUIRED" and "pending" in payload and payload["pending"].get("service") == svc and payload["pending"].get("subservice") == sub)
            pend = (payload.get("pending") or {})
            prefilled = {k: payload.get(k) for k in ("walletNumber", "accountNumber", "amount") if payload.get(k) is not None}
            missing = pend.get("missingFields")
            ok_fields = all(str(prefilled.get(k, "")).replace(" ", "") == str(v) or (k == "amount" and float(prefilled.get(k, 0) or 0) == v) for k, v in want.items() if k in prefilled) if prefilled else None
            results.append((ok_route, msg, svc, sub, r.get("type"), got, prefilled, missing, ok_fields, text[:90]))
            print(("OK  " if ok_route else "BAD ") + f"{msg[:62]!r:66} want={svc}/{sub} got={r.get('type')} {got} prefilled={prefilled} missing={missing}", flush=True)
            if r.get("type") in ("CLARIFICATION_REQUIRED", "ACCOUNT_SELECTION_REQUIRED", "CONFIRMATION_REQUIRED"):
                await chat(client, token, "cancel")
    n = len(results); ok = sum(1 for x in results if x[0])
    print(f"\nroute correct: {ok}/{n}")
    bad_fields = [x for x in results if x[8] is False]
    print("prefilled values wrong:", len(bad_fields))
    for x in bad_fields: print("  ", x[1], x[6])


asyncio.run(main())
