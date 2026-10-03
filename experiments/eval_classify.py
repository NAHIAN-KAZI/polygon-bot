"""Isolated classify() accuracy eval (no session context). Run inside the backend container:
docker compose exec -T backend python experiments/eval_classify.py
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from app.banking.routing import BankingService, Clarification, KbQuestion, UnknownService, classify
from app.banking.taxonomy import initialize_taxonomy

C, K = "CLARIFY", "KB"
CASES = [
    ("what's my balance?", ("account_info", "balance")),
    ("balance koto", ("account_info", "balance")),
    ("how much money do i have", ("account_info", "balance")),
    ("how many accounts do i have?", ("account_info", "accounts")),
    ("show my accounts", ("account_info", "accounts")),
    ("acc info", [C, ("account_info", "accounts")]),
    ("show my login history", ("account_info", "login_history")),
    ("which devices are logged in", ("account_info", "device_history")),
    ("show my cards", ("account_info", "cards")),
    ("card list", ("account_info", "cards")),
    ("what cards do i have", ("account_info", "cards")),
    ("show my loan", ("loan_services", "my_loans")),
    ("show my loans", ("loan_services", "my_loans")),
    ("do i have any loan", ("loan_services", "my_loans")),
    ("show my dps profit history", ("account_info", "dps_profit_history")),
    ("dps profit", ("account_info", "dps_profit_history")),
    ("how much profit did my fixed deposit earn", ("account_info", "fd_profit_history")),
    ("show my disputes", ("service_requests", "disputes")),
    ("any open complaint or dispute?", [("service_requests", "disputes"), ("polygon_services", "my_tickets")]),
    ("i want to raise a dispute", ("service_requests", "raise_dispute")),
    ("atm took my money but no cash came out", ("service_requests", "raise_dispute")),
    ("last transactions", ("polygon_services", "transaction_history")),
    ("show my statement", ("polygon_services", "transaction_history")),
    ("fees?", C),
    ("what is the fee for sending 1000 to bkash", ("fees", "fee_quote")),
    ("charge koto bkash e 500 pathale", ("fees", "fee_quote")),
    ("I want to transfer money", C),
    ("send 2000 to my bkash 01812345678", ("transfer", "wallet_transfer")),
    ("transfer 5000 to account 1234567890 via other bank", ("transfer", "bank_transfer")),
    ("send money to Ashan", ("polygon_services", "beneficiary")),
    ("add a beneficiary named Rahim account 123456789", ("beneficiary_management", "beneficiary_add")),
    ("freeze my card", ("card_services", "frezz_unfrezz")),
    ("i lost my card block it", ("card_services", "frezz_unfrezz")),
    ("I need help with my card", C),
    ("hi", C),
    ("my complaints", ("polygon_services", "my_tickets")),
    ("show my tickets", ("polygon_services", "my_tickets")),
    ("transactions of my savings account", ("polygon_services", "transaction_history")),
    ("card limit change request status", ("card_info", "card_limit_requests")),
    ("which cards can i apply for", ("card_info", "card_products")),
    ("my virtual card request", ("card_info", "virtual_card_requests")),
    ("is my replacement card ready", ("card_info", "replacement_requests")),
    ("credit card due amount", ("card_info", "credit_card_summary")),
    ("credit card statement this month", ("card_info", "credit_card_statement")),
    ("my profile", ("profile", "profile")),
    ("what is my registered address", ("profile", "address")),
    ("which phone numbers are on my account", ("profile", "contacts")),
    ("status of my profile update request", ("profile", "profile_change_requests")),
    ("gift received", ("transfer_info", "gifts_received")),
    ("email transfers i sent", ("transfer_info", "email_transfers")),
    ("qr payments", ("transfer_info", "qr_payment_history")),
    ("how much can i transfer per day", ("transfer_info", "transfer_limit")),
    ("Assalamualaikum, I opened a DPS last year and I want to know how much profit it has "
     "made so far, can you check that for me please?", ("account_info", "dps_profit_history")),
    # --- persona sweep: low-literacy / average / sophisticated, per service ---
    ("blance plz", ("account_info", "balance")),
    ("amar account e koto taka ase", ("account_info", "balance")),
    ("Could you please let me know the current available balance in my savings account?", ("account_info", "balance")),
    ("my acount list", ("account_info", "accounts")),
    ("I'd like an overview of all the accounts I currently hold with Polygon Bank, including deposits.", ("account_info", "accounts")),
    ("who logged in my acc", ("account_info", "login_history")),
    ("For security reasons, I want to review the recent sign-in activity on my internet banking profile.", ("account_info", "login_history")),
    ("my phones connected", ("account_info", "device_history")),
    ("kard", ("account_info", "cards")),
    ("Please list every debit and credit card currently issued under my name.", ("account_info", "cards")),
    ("lon", ("loan_services", "my_loans")),
    ("amar kono loan ase?", ("loan_services", "my_loans")),
    ("I would like to review the outstanding loans I have with the bank and their current status.", ("loan_services", "my_loans")),
    ("fdr profit koto", ("account_info", "fd_profit_history")),
    ("Can you provide the profit history accrued on my fixed deposit account so far?", ("account_info", "fd_profit_history")),
    ("dps er labh", ("account_info", "dps_profit_history")),
    ("trnsction", ("polygon_services", "transaction_history")),
    ("ki ki khoroch korsi ei mash e", ("polygon_services", "transaction_history")),
    ("Kindly share a list of my most recent debits and credits so I can reconcile my expenses.", ("polygon_services", "transaction_history")),
    ("disput", [("service_requests", "disputes"), ("service_requests", "raise_dispute"), C]),
    ("i paid but money gone 2 times plz help", ("service_requests", "raise_dispute")),
    ("I'd like to formally dispute a card transaction from last week that I did not authorize.", ("service_requests", "raise_dispute")),
    ("my complain status", ("polygon_services", "my_tickets")),
    ("What is the current status of the support tickets I raised earlier?", ("polygon_services", "my_tickets")),
    ("bkash fee 500", ("fees", "fee_quote")),
    ("What would be the total charges, including VAT, for transferring 25000 taka to another bank?", ("fees", "fee_quote")),
    ("send tk", C),
    ("50k pathabo dbbl e acc 1234567890", ("transfer", "bank_transfer")),
    ("Please arrange a transfer of 15000 taka from my account to my Nagad wallet 01712345678.", ("transfer", "wallet_transfer")),
    ("taka pathao rahim ke", ("polygon_services", "beneficiary")),
    ("save my brother as beneficiery", ("beneficiary_management", "beneficiary_add")),
    ("card hariye gese", ("card_services", "frezz_unfrezz")),
    ("My debit card was stolen this morning; please block it immediately to prevent misuse.", ("card_services", "frezz_unfrezz")),
    ("unblock card", C),
    ("credit card bill koto", [("card_info", "credit_card_summary"), ("card_info", "credit_card_statement")]),
    ("What is the minimum amount due on my credit card and when is it payable?", ("card_info", "credit_card_summary")),
    ("my statment of credit card", ("card_info", "credit_card_statement")),
    ("new card types", ("card_info", "card_products")),
    ("replacmnt card status", ("card_info", "replacement_requests")),
    ("my info", [("profile", "profile"), C]),
    ("What personal details do you currently have on file for me?", ("profile", "profile")),
    ("adress", ("profile", "address")),
    ("limit koto", [("transfer_info", "transfer_limit"), ("card_info", "credit_card_summary"), ("card_info", "card_limit_requests"), C]),
    ("What is the maximum amount I'm allowed to transfer in a single day from my account?", ("transfer_info", "transfer_limit")),
    ("gift pelam?", ("transfer_info", "gifts_received")),
    ("email transfer status", ("transfer_info", "email_transfers")),
    ("qr te ki pay korsi", ("transfer_info", "qr_payment_history")),
    ("tumi ke", [K, C]),
    ("ur stupid", [K, C]),
    ("Who won the football world cup in 2022?", K),
    ("What documents are required to open a savings account?", K),
    ("what is 15 times 23", K),
    ("weather in dhaka", K),
    ("what is a savings account", K),
]


def label(r):
    if isinstance(r, BankingService):
        return (r.category, r.service)
    if isinstance(r, Clarification):
        return C
    if isinstance(r, KbQuestion):
        return K
    if isinstance(r, UnknownService):
        return ("UNKNOWN", r.category, r.service)
    return repr(r)


async def main():
    await initialize_taxonomy()
    ok = 0
    for msg, want in CASES:
        got = label(await classify(msg, []))
        hit = got in want if isinstance(want, list) else got == want
        ok += hit
        print(f"{'OK ' if hit else 'BAD'} {msg!r:55} want={want} got={got}")
    print(f"\n{ok}/{len(CASES)} correct")


asyncio.run(main())
