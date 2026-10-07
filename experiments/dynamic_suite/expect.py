"""What the bot should do for each row of INTENT_IMPLEMENTATION_STATUS.md (test
expectations only -- the bot itself has no such table).

  (category, service[, subservice])  routed to that service (any flow state of it)
  NOT_IN_CHAT                         not offered in chat: the bot must say so / ask, never route or claim it was done
  KB                                  knowledge-base / off-topic / greeting style answer
Keyed by the row's number prefix ("1.6") or its name for unnumbered rows.
"""
from app.banking import ui_actions

NOT_IN_CHAT = "NOT_IN_CHAT"
KB = "KB"

EXPECT = {
    "1.1": ("account_info", "accounts"), "1.2": ("account_info", "accounts"),
    "1.5": NOT_IN_CHAT, "1.6": ("loan_services", "my_loans"),
    "1.7": ("account_info", "fd_profit_history"), "1.8": ("account_info", "dps_profit_history"),
    "— Cards list": ("account_info", "cards"), "— Account transactions": ("polygon_services", "transaction_history"),
    "2.1": NOT_IN_CHAT, "2.2": ("service_requests", "raise_dispute"), "2.3": ("service_requests", "disputes"),
    "3.1": NOT_IN_CHAT, "3.2": NOT_IN_CHAT, "3.3": ("service_requests", "raise_dispute"),
    "3.4": ("service_requests", "disputes"), "3.5": ("support", "submit_complaint"),
    "3.6": ("polygon_services", "my_tickets"),
    "4.1": ("card_services", "frezz_unfrezz"), "4.2": NOT_IN_CHAT, "4.3": NOT_IN_CHAT, "4.4": NOT_IN_CHAT,
    "4.5": NOT_IN_CHAT, "4.6": NOT_IN_CHAT, "4.7": NOT_IN_CHAT, "4.8": ("card_info", "card_limit_requests"),
    "4.9": NOT_IN_CHAT, "4.10": ("card_info", "card_products"), "4.11": NOT_IN_CHAT, "4.13": NOT_IN_CHAT,
    "4.15": NOT_IN_CHAT, "4.16": ("card_info", "virtual_card_requests"), "4.17": NOT_IN_CHAT,
    "4.19": NOT_IN_CHAT, "4.20": NOT_IN_CHAT, "4.21": NOT_IN_CHAT, "4.22": NOT_IN_CHAT, "4.23": NOT_IN_CHAT,
    "5.1": ("card_info", "replacement_requests"), "5.2": NOT_IN_CHAT,
    "6.1": ("account_info", "balance"), "6.2": ("card_info", "credit_card_summary"),
    "7.1": ("profile", "profile"), "7.2": ("profile_update", "update_nickname"),
    "7.3/7.4": ("profile_update", "update_profile_image"), "7.5": ("profile_update", "update_mobile"),
    "7.6": ("profile_update", "update_email"), "7.7": ("profile", "address"),
    "7.8": ("profile_update", "update_address"), "7.9": NOT_IN_CHAT, "7.10": ("profile", "contacts"),
    "7.11": NOT_IN_CHAT, "7.12": ("profile", "profile_change_requests"), "7.13": NOT_IN_CHAT,
    "7.14": ("profile", "contact_priority_requests"),
    "8.1": ("polygon_services", "transaction_history"), "8.2": ("service_requests", "raise_dispute"),
    "8.3": ("service_requests", "disputes"), "8.4": ("support", "submit_complaint"),
    "8.5": ("polygon_services", "my_tickets"),
    "10.1": ("fees", "fee_quote"),
    "12.1": ("card_requests", "report_lost_card"), "12.2": ("card_services", "frezz_unfrezz"),
    "13.1": ("polygon_services", "transaction_history"), "13.2": ("polygon_services", "transaction_history"),
    "13.3": ("card_info", "credit_card_statement"),
    "14.1": ("transfer", "bank_transfer", "own_account"), "14.2": ("transfer", "bank_transfer", "city_account"),
    "14.3": ("transfer", "bank_transfer", "other_bank"), "14.4": NOT_IN_CHAT, "14.5": NOT_IN_CHAT,
    "14.6": ("transfer_info", "gifts_received"), "14.7": NOT_IN_CHAT, "14.9": NOT_IN_CHAT,
    "14.10": ("transfer_info", "email_transfers"), "14.11": ("transfer_info", "email_transfers"),
    "14.12": NOT_IN_CHAT, "14.13": NOT_IN_CHAT, "14.14": ("transfer", "wallet_transfer"),
    "14.16": NOT_IN_CHAT, "14.17": NOT_IN_CHAT, "14.18": ("transfer_info", "qr_payment_history"),
    "14.19": ("polygon_services", "beneficiary"), "14.20": ("beneficiary_management", "beneficiary_add"),
    "14.21": NOT_IN_CHAT, "14.22": NOT_IN_CHAT, "14.23": NOT_IN_CHAT, "14.24": NOT_IN_CHAT, "14.25": NOT_IN_CHAT,
    "14.27": ("transfer_info", "transfer_limit"), "14.28": NOT_IN_CHAT, "14.29": NOT_IN_CHAT,
}

# Intents with no table of endpoints: described in the doc as conversational.
EXTRA_ROWS = [
    ("GREETING", "Greeting and small talk", "a hello, thanks or friendly chit-chat with the bank's assistant", KB),
    ("FALLBACK", "General bank knowledge and off-topic", "a general question about banking products, or something unrelated to banking", KB),
]


def key_of(name: str) -> str:
    return name if name.startswith("—") else name.split(" ", 1)[0]


# T-79: rows the chat hands to the app are expected to return the matching app action.
for _action in ui_actions.UI_ACTIONS.values():
    for _row in _action.rows:
        EXPECT[_row] = (ui_actions.CATEGORY, _action.id)
