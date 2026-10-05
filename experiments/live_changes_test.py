"""Live test of the T-75/T-76 change flows through /chat, each verified against the
bank and reverted where the bank allows. Run inside the backend container with
EVAL_API_KEY, EVAL_USERNAME, EVAL_PASSWORD set:
  python -m experiments.live_changes_test

Order matters: nickname, address, complaint, dispute (no bank write), beneficiary
add (+delete), email (+revert), mobile (+revert, which signs the session out).
Every OTP is the dev environment's fixed test code. Stops at the first failure of a
step that changes data, so nothing is left half-changed silently.
"""
import asyncio
import os
import sys

import httpx

from app.banking.adapters import real
from experiments.live_freeze_test import chat, login

TEST_OTP = "0000"
ORIGINAL_NICKNAME = "taslim_islamic"   # was changed to "new value" by an earlier session
TEST_ADDRESS = "TEST ADDRESS - please ignore, House 1, Road 1, Dhaka"
TEST_EMAIL = "taslim.chatbot.test@example.com"
TEST_PHONE = "01399999901"
COMPLAINT_TEXT = "TEST - please ignore. Chatbot QA check of the complaint flow."
BENEFICIARY = "ClaudeTestDeleteMe"


def say(step, message, text, result):
    payload = {k: v for k, v in (result.get("payload") or {}).items() if k not in ("otp", "pin", "password")}
    print(f"[{step}] Customer: {message}\n        Bot: {text}\n        -> {result.get('type')} "
          f"{result.get('category')}/{result.get('service')} {payload}\n", flush=True)


async def profile(token):
    body = await real._call("GET", "/auth/v1/user", token)
    return body.get("data", body)


async def demographic(token):
    body = await real._call("GET", "/customer/v1/me/demographic", token)
    return body.get("data", body)


async def converse(client, token, step, messages):
    result = {}
    for message, payload in messages:
        text, result = await chat(client, token, message, payload) if payload else await chat(client, token, message)
        say(step, message, text, result)
    return result


ONLY = set(filter(None, os.environ.get("ONLY", "").split(",")))  # e.g. ONLY=complaint,dispute


def wanted(step):
    return not ONLY or step in ONLY


async def main():
    failures = []
    async with httpx.AsyncClient(timeout=60) as client:
        token = await login(client)
        before = await profile(token)
        print(f"BEFORE: nickName={before.get('nickName')!r} email={before.get('email')!r} "
              f"phone=...{str(before.get('phone'))[-4:]}\n", flush=True)

        if wanted('nickname'):
            # 1. nickname (restores the account)
            r = await converse(client, token, "nickname", [
                (f"change my nickname to {ORIGINAL_NICKNAME}", None), ("yes", None)])
            nick = (await profile(token)).get("nickName")
            print(f"   VERIFY nickname now {nick!r}\n", flush=True)
            if nick != ORIGINAL_NICKNAME:
                failures.append("nickname")

        if wanted('address'):
            # 2. address (cannot be cleared again -- partial update ignores nulls)
            await converse(client, token, "address", [
                (f"change my present address to {TEST_ADDRESS}", None), ("yes", None)])
            present = (await demographic(token)).get("presentAddress")
            print(f"   VERIFY presentAddress now {present!r}\n", flush=True)
            if TEST_ADDRESS.split(",")[0] not in str(present):
                failures.append("address")

        if wanted('complaint'):
            # 3. complaint
            await converse(client, token, "complaint", [
                (f"I want to file a complaint about the mobile app: {COMPLAINT_TEXT}", None), ("yes", None)])
            complaints = await real._call("GET", "/support/v1/complaints", token)
            found = COMPLAINT_TEXT[:20] in str(complaints)
            print(f"   VERIFY complaint listed: {found}\n", flush=True)
            if not found:
                failures.append("complaint")

        if wanted('dispute'):
            # 4. dispute: transaction matched from the account's history (never submitted)
            r = await converse(client, token, "dispute", [
                ("I sent 5000 taka by bKash on 29 September but it never reached, the money was deducted", None)])
            if r.get("type") == "TRANSACTION_SELECTION_REQUIRED":
                first = (r.get("payload") or {}).get("transactions", [{}])[0]
                r = await converse(client, token, "dispute", [("Selected", {"transactionId": first.get("transactionId")})])
            if r.get("type") == "CLARIFICATION_REQUIRED":
                r = await converse(client, token, "dispute", [("the money was deducted but never reached", None)])
            print(f"   VERIFY dispute summary: executed={(r.get('payload') or {}).get('executed')} "
                  f"ref={(r.get('payload') or {}).get('transactionReferenceNo')}\n", flush=True)

        if wanted('beneficiary'):
            # 5. beneficiary add + delete
            await converse(client, token, "beneficiary", [
                (f"add a beneficiary named {BENEFICIARY}, account number 100126000015", None), ("yes", None)])
            listed = await real._call("GET", "/beneficiary/v1/beneficiaries", token, params={"page": 0, "size": 100})
            items = listed.get("data") if isinstance(listed, dict) else listed
            if isinstance(items, dict):
                items = items.get("content") or items.get("beneficiaries") or []
            mine = [b for b in items or [] if isinstance(b, dict) and b.get("nickname") == BENEFICIARY]
            print(f"   VERIFY beneficiary added: {len(mine)} record(s)", flush=True)
            for b in mine:
                await real._call("DELETE", f"/beneficiary/v1/beneficiaries/{b['id']}", token)
            print(f"   cleanup: deleted {len(mine)}\n", flush=True)
            if not mine:
                failures.append("beneficiary")

        if wanted('email'):
            # 6. email change + revert
            original_email = before.get("email")
            for target in (TEST_EMAIL, original_email):
                await converse(client, token, "email", [
                    (f"change my email to {target}", None), ("Verify", {"otp": TEST_OTP})])
                now = (await profile(token)).get("email")
                print(f"   VERIFY email now {now!r}\n", flush=True)
                if now != target:
                    failures.append(f"email->{target}")
                    break

        if wanted('mobile'):
            # 7. mobile change + revert (the bank signs the session out after each change)
            original_phone = before.get("phone")
            for target in (TEST_PHONE, original_phone):
                await converse(client, token, "mobile", [
                    (f"change my mobile number to {target}", None), ("Verify", {"otp": TEST_OTP})])
                token = await login(client)
                now = (await profile(token)).get("phone")
                print(f"   VERIFY phone now ...{str(now)[-4:]}\n", flush=True)
                if now != target:
                    failures.append(f"mobile->...{str(target)[-4:]}")
                    break

        after = await profile(token)
        print(f"AFTER: nickName={after.get('nickName')!r} email={after.get('email')!r} "
              f"phone=...{str(after.get('phone'))[-4:]}", flush=True)
    print("FAILURES:", failures or "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
