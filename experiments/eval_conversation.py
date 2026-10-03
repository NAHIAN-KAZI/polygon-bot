"""Live multi-turn eval against the real /chat endpoint, one continuous session.

Each turn switches intent and message style (1-2 words, vague, long paragraph,
off-topic, Banglish). A turn passes when the result type/category/service is in
its accepted set. Run from the host with EVAL_API_KEY plus either EVAL_TOKEN (a
fresh access token) or EVAL_USERNAME + EVAL_PASSWORD:
  python3 experiments/eval_conversation.py
"""
import json
import os
import sys
import urllib.request

BASE = "http://192.168.12.41:8000/chat"
LOGIN = "https://internet-banking.dev-polygontech.xyz/auth/v1/auth/login"
API_KEY = os.environ["EVAL_API_KEY"]
USERNAME = os.environ.get("EVAL_USERNAME")
PASSWORD = os.environ.get("EVAL_PASSWORD")
# A pre-fetched access token (EVAL_TOKEN) skips login entirely -- use it when the
# bank asks for a CAPTCHA (HTTP 320), which this script never solves.
TOKEN = os.environ.get("EVAL_TOKEN")

CL = ("CLARIFICATION_REQUIRED", None, None)
KB = ("KB_ANSWER", None, None)
SEL = "ACCOUNT_SELECTION_REQUIRED"


def bs(cat, svc):
    return ("BANKING_SERVICE", cat, svc)


def svc(cat, s):
    """Any non-error outcome routed to this service (data, selection, or a specific clarification)."""
    return {bs(cat, s), (SEL, cat, s), ("SERVICE_UNAVAILABLE", cat, s)}


# (message, accepted outcomes)
TURNS = [
    ("how many accounts do i have", svc("account_info", "accounts")),
    ("i want to raise a dispute", {CL} | svc("service_requests", "raise_dispute")),
    ("balance", svc("account_info", "balance")),
    ("hmm", {CL, KB}),
    ("cards", svc("account_info", "cards")),
    ("Hi, I was trying to pay my electricity bill yesterday and I noticed that the app "
     "deducted money twice from my savings account. I am really worried about this, can "
     "you help me report this problem?", {CL} | svc("service_requests", "raise_dispute")),
    ("what is the capital of france", {KB}),
    ("my loans", svc("loan_services", "my_loans")),
    ("dps profit", svc("account_info", "dps_profit_history")),
    ("show my complaints", svc("polygon_services", "my_tickets")),
    ("any open disputes?", svc("service_requests", "disputes")),
    ("fees?", {CL}),
    ("koto taka charge lagbe bkash e 1000 pathale", svc("fees", "fee_quote")),
    ("whats my transfer limit", svc("transfer_info", "transfer_limit")),
    ("show my profile", svc("profile", "profile")),
    ("what address do you have for me", svc("profile", "address")),
    ("did anyone send me a gift", svc("transfer_info", "gifts_received")),
    ("qr payment history", svc("transfer_info", "qr_payment_history")),
    ("what credit card limit do i have left", svc("card_info", "credit_card_summary")),
    ("what kind of cards does the bank offer", svc("card_info", "card_products")),
    ("status of my card replacement", svc("card_info", "replacement_requests")),
    ("last 5 transactions", svc("polygon_services", "transaction_history")),
    ("I want to send 2000 taka to my bkash 01812345678", svc("transfer", "wallet_transfer")),
    ("thanks", {CL, KB}),
    ("freeze my card", {CL, ("OTP_REQUIRED", "card_services", "frezz_unfrezz")}
     | svc("card_services", "frezz_unfrezz")),
    ("the physical one", {CL}),
    ("nevermind, how much money do i have", svc("account_info", "balance")),
    ("ami ekta dispute korte chai", {CL} | svc("service_requests", "raise_dispute")),
    ("bkash fee", {CL} | svc("fees", "fee_quote")),
    ("500", svc("fees", "fee_quote")),
    ("lon ase?", svc("loan_services", "my_loans")),
    ("ok what about my credit card bill", svc("card_info", "credit_card_summary")),
    ("I would also like to know the current transfer limits on my primary account, if possible.",
     svc("transfer_info", "transfer_limit")),
    ("u r useless", {KB, CL}),
    ("statement dao", svc("polygon_services", "transaction_history")),
]


def login():
    req = urllib.request.Request(
        LOGIN, data=json.dumps({"username": USERNAME, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "curl/8.5.0"},
    )
    return json.load(urllib.request.urlopen(req, timeout=30))["token"]["accessToken"]


def chat(token, message):
    req = urllib.request.Request(
        BASE, data=json.dumps({"message": message}).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY,
                 "Authorization": f"Bearer {token}"},
    )
    text, result, event = [], None, None
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw in resp:
            line = raw.decode().rstrip("\n")
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "token":
                    text.append(data["token"])
                elif event == "result":
                    result = data
    return "".join(text), result


def main():
    token = TOKEN or login()
    ok = 0
    for msg, accepted in TURNS:
        reply, r = chat(token, msg)
        got = (r["type"], r.get("category"), r.get("service")) if r else ("NO_RESULT", None, None)
        hit = got in accepted
        ok += hit
        print(f"{'OK ' if hit else 'BAD'} {msg[:60]!r:64} -> {got}")
        print(f"      reply: {reply[:150]!r}")
    print(f"\n{ok}/{len(TURNS)} turns correct")
    sys.exit(0 if ok == len(TURNS) else 1)


if __name__ == "__main__":
    main()
