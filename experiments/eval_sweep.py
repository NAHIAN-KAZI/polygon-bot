"""Live sweep: every intent x many message styles (1 word, typo, Banglish, vague,
formal multi-line, angry, mixed), plus blocked/unsupported asks. One continuous
session, so it also exercises intent switching every turn. Prints routing and the
full reply so reply quality can be read, not just routing.

Run from the host with EVAL_API_KEY and EVAL_TOKEN or EVAL_USERNAME + EVAL_PASSWORD:
  python3 experiments/eval_sweep.py [output.jsonl]

Never completes a mutating action: freeze stops at OTP_REQUIRED (no code is
submitted) and beneficiary add stops at its yes/no confirmation.
"""
import json
import sys

from eval_conversation import CL, KB, SEL, TOKEN, chat, login, svc

OTP = "OTP_REQUIRED"
CONF = "CONFIRMATION_REQUIRED"
UNK = ("UNKNOWN_SERVICE",)
NOT_HERE = {CL, KB}  # blocked/unsupported: explain or ask, never pretend to do it


def any_of(*sets):
    out = set()
    for s in sets:
        out |= s if isinstance(s, set) else {s}
    return out


def mut(cat, s, step):
    return {(step, cat, s)}


ACC = svc("account_info", "accounts")
BAL = svc("account_info", "balance")
TXN = any_of(svc("polygon_services", "transaction_history"), svc("account_info", "account_transactions"))
CARDS = svc("account_info", "cards")
FREEZE = any_of(mut("card_services", "frezz_unfrezz", OTP), CL, svc("card_services", "frezz_unfrezz"))
DISP = svc("service_requests", "disputes")
RAISE = any_of(CL, svc("service_requests", "raise_dispute"))
TICKETS = svc("polygon_services", "my_tickets")
FEE = any_of(CL, svc("fees", "fee_quote"))
LIMIT = svc("transfer_info", "transfer_limit")
XFER = any_of(CL, svc("transfer", "bank_transfer"), svc("transfer", "wallet_transfer"),
              svc("polygon_services", "beneficiary"))
WALLET = any_of(CL, svc("transfer", "wallet_transfer"))
BENE_ADD = any_of(CL, mut("beneficiary_management", "beneficiary_add", CONF))
LOANS = svc("loan_services", "my_loans")
DPS = svc("account_info", "dps_profit_history")
FD = svc("account_info", "fd_profit_history")
CC_SUM = any_of(svc("card_info", "credit_card_summary"), svc("card_info", "credit_card_statement"))
CC_STMT = any_of(svc("card_info", "credit_card_statement"), svc("card_info", "credit_card_summary"))
PRODUCTS = svc("card_info", "card_products")
REPL = svc("card_info", "replacement_requests")
VIRT = svc("card_info", "virtual_card_requests")
CLIM = svc("card_info", "card_limit_requests")
PROFILE = svc("profile", "profile")
ADDR = svc("profile", "address")
CONTACTS = any_of(svc("profile", "contacts"), svc("profile", "profile"))
GIFTS = svc("transfer_info", "gifts_received")
EMAILX = svc("transfer_info", "email_transfers")
QR = svc("transfer_info", "qr_payment_history")
LOGINS = any_of(svc("account_info", "login_history"), svc("account_info", "device_history"))
DEVICES = any_of(svc("account_info", "device_history"), svc("account_info", "login_history"))
CHAT = {KB, CL}

# (intent, style, message, accepted)
CASES = [
    # ACCOUNT_INFO
    ("ACCOUNT_INFO", "1-word", "accounts", ACC),
    ("ACCOUNT_INFO", "typo", "how mny acount i hav", ACC),
    ("ACCOUNT_INFO", "banglish", "amar koyta account ase", ACC),
    ("ACCOUNT_INFO", "formal", "Good afternoon. Could you kindly list all the accounts I currently hold with Polygon Bank, along with their types?", ACC),
    ("ACCOUNT_INFO", "1-word", "loans", LOANS),
    ("ACCOUNT_INFO", "banglish", "amar kono loan ache?", LOANS),
    ("ACCOUNT_INFO", "1-word", "dps", DPS),
    ("ACCOUNT_INFO", "vague", "how much profit did my dps make", DPS),
    ("ACCOUNT_INFO", "short", "fd profit", FD),
    ("ACCOUNT_INFO", "1-word", "devices", DEVICES),
    ("ACCOUNT_INFO", "multi-line", "Hi,\nI got a weird notification yesterday.\nCan you show me where my account was logged in from recently?", LOGINS),
    # CHECK_BALANCE
    ("CHECK_BALANCE", "1-word", "balance", BAL),
    ("CHECK_BALANCE", "typo", "blance", BAL),
    ("CHECK_BALANCE", "banglish", "amar account e koto taka ase", BAL),
    ("CHECK_BALANCE", "angry", "WHY CANT I SEE MY MONEY. how much do i even have left???", BAL),
    ("CHECK_BALANCE", "short", "credit card limit left?", CC_SUM),
    # MINI_STATEMENT
    ("MINI_STATEMENT", "1-word", "statement", TXN),
    ("MINI_STATEMENT", "typo", "trnsactions", TXN),
    ("MINI_STATEMENT", "banglish", "last koyta lenden dekhao", TXN),
    ("MINI_STATEMENT", "multi-line", "Hello team,\n\nI'm reconciling my monthly budget and need to see what I spent recently.\nPlease show my latest transactions.\n\nThanks", TXN),
    ("MINI_STATEMENT", "short", "credit card statement this month", CC_STMT),
    # TRANSFER
    ("TRANSFER", "vague", "send money", XFER),
    ("TRANSFER", "full", "send 1500 taka to my bkash 01711223344", WALLET),
    ("TRANSFER", "banglish", "nagad e 2000 pathabo 01811223344", WALLET),
    ("TRANSFER", "other-bank", "transfer 10000 to my brac bank account 1234567890123", XFER),
    ("TRANSFER", "own", "move 5000 between my own accounts", XFER),
    ("TRANSFER", "info", "whats my daily transfer limit", LIMIT),
    ("TRANSFER", "info", "did i get any gifts", GIFTS),
    ("TRANSFER", "info", "email transfer status", EMAILX),
    ("TRANSFER", "info", "qr payments i made", QR),
    ("TRANSFER", "beneficiary", "add a new beneficiary", BENE_ADD),
    ("TRANSFER", "beneficiary", "who are my saved beneficiaries", svc("polygon_services", "beneficiary")),
    # FEES
    ("FEES", "1-word", "fees", FEE),
    ("FEES", "banglish", "bkash e 5000 pathale koto charge", FEE),
    ("FEES", "formal", "What would be the total charge if I transfer 20000 taka to another bank via NPSB?", FEE),
    ("FEES", "vague", "is there any charge", FEE),
    # CARD_MANAGEMENT / LOST_OR_STOLEN_CARD
    ("CARD_MANAGEMENT", "1-word", "cards", CARDS),
    ("CARD_MANAGEMENT", "typo", "my crads", CARDS),
    ("CARD_MANAGEMENT", "catalog", "which credit cards do you offer", PRODUCTS),
    ("CARD_MANAGEMENT", "status", "virtual card request status", VIRT),
    ("CARD_MANAGEMENT", "status", "did my card limit change go through", CLIM),
    ("LOST_OR_STOLEN_CARD", "plain", "i lost my card", FREEZE),
    ("LOST_OR_STOLEN_CARD", "banglish", "card churi hoye gese, block koro", FREEZE),
    ("LOST_OR_STOLEN_CARD", "multi-line", "Someone just used my debit card at a shop I've never been to!\nPlease block it right now before they use it again.", FREEZE),
    ("LOST_OR_STOLEN_CARD", "escape", "actually forget that, what's my balance", BAL),
    # CARD_REPLACEMENT
    ("CARD_REPLACEMENT", "short", "replacement card status", REPL),
    ("CARD_REPLACEMENT", "typo", "replacemnt req", REPL),
    # CARD_ISSUE
    ("CARD_ISSUE", "vague", "my card isnt working", CHAT),
    ("CARD_ISSUE", "complaints", "show my complaints", TICKETS),
    ("CARD_ISSUE", "tickets", "any update on my tickets?", TICKETS),
    ("CARD_ISSUE", "blocked", "unfreeze my card", NOT_HERE),
    ("CARD_ISSUE", "blocked", "reset my card pin", NOT_HERE | {UNK}),
    # ATM_SUPPORT / FAILED_TRANSFER / disputes
    ("ATM_SUPPORT", "story", "ATM took my card money but no cash came out", RAISE),
    ("ATM_SUPPORT", "blocked", "i want to withdraw cash by code", NOT_HERE | {UNK}),
    ("FAILED_TRANSFER", "story", "I sent 3000 to my brother yesterday, money was deducted but he never got it", RAISE),
    ("FAILED_TRANSFER", "banglish", "taka kete nise kintu jay nai", RAISE),
    ("FAILED_TRANSFER", "status", "any open disputes", DISP),
    ("FAILED_TRANSFER", "status", "status of my dispute", DISP),
    # EDIT_PERSONAL_DETAILS
    ("EDIT_PERSONAL_DETAILS", "1-word", "profile", PROFILE),
    ("EDIT_PERSONAL_DETAILS", "short", "my address", ADDR),
    ("EDIT_PERSONAL_DETAILS", "phones", "which phone numbers are registered", CONTACTS),
    ("EDIT_PERSONAL_DETAILS", "status", "did my profile change request get approved", svc("profile", "profile_change_requests")),
    ("EDIT_PERSONAL_DETAILS", "blocked", "change my email to new@example.com", NOT_HERE | {UNK}),
    ("EDIT_PERSONAL_DETAILS", "blocked", "update my address please", NOT_HERE | {UNK} | ADDR),
    # GREETING / FALLBACK / chit-chat
    ("GREETING", "1-word", "hi", CHAT),
    ("GREETING", "banglish", "assalamualaikum, kemon achen", CHAT),
    ("FALLBACK", "off-topic", "who is the prime minister of japan", {KB}),
    ("FALLBACK", "maths", "what is 12 * 12", {KB}),
    ("FALLBACK", "abuse", "you are the worst bot ever", CHAT),
    ("FALLBACK", "gibberish", "asdfgh", CHAT),
    ("FALLBACK", "kb", "what documents do i need to open an account", {KB}),
    ("FALLBACK", "1-word", "help", CHAT),
    ("FALLBACK", "thanks", "thank you so much", CHAT),
    # Mixed
    ("MIXED", "two-asks", "whats my balance and also show my last transactions", BAL | TXN),
]


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else None
    out = open(out_path, "w") if out_path else None
    token = TOKEN or login()
    ok, per_intent = 0, {}
    for intent, style, msg, accepted in CASES:
        reply, r = chat(token, msg)
        if r and r["type"] == "AUTH_REQUIRED" and not TOKEN:
            token = login()  # bank tokens last ~15 min; the sweep runs longer
            reply, r = chat(token, msg)
        got = (r["type"], r.get("category"), r.get("service")) if r else ("NO_RESULT", None, None)
        hit = got in accepted or (got[0],) in accepted
        ok += hit
        tally = per_intent.setdefault(intent, [0, 0])
        tally[0] += hit
        tally[1] += 1
        print(f"{'OK ' if hit else 'BAD'} [{intent}/{style}] {msg[:70]!r} -> {got}", flush=True)
        print(f"      reply: {reply[:300]!r}", flush=True)
        if out:
            out.write(json.dumps({"intent": intent, "style": style, "message": msg, "got": got,
                                  "ok": hit, "reply": reply}) + "\n")
    print(f"\n{ok}/{len(CASES)} correct")
    for intent, (good, total) in per_intent.items():
        print(f"  {intent:22} {good}/{total}")


if __name__ == "__main__":
    main()
