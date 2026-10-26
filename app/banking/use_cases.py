"""Everything the chatbot can do, as use cases grouped by intent (T-108).

This is DATA for the back office: it lists what can be switched on or off, and maps each use case to
the taxonomy keys it covers so the chat can check a switch once, before any bank call (T-109). It
never reads customer text. A use case id is "<category>.<service>" for a platform service and
"app_actions.<action id>" for an app action.

Kinds: answer (the bot shows information), confirmed_change (the bot changes something after a yes),
app_screen (the bot prepares it or hands over, the app finishes it), not_in_chat (the bot only explains).
`app_action` names the app action whose screen is offered when the use case is switched off.
"""
from dataclasses import dataclass

from app.banking import taxonomy, ui_actions

INTENTS: tuple[tuple[str, str], ...] = (
    ("CHECK_BALANCE", "Balance"),
    ("MINI_STATEMENT", "Statements and transactions"),
    ("ACCOUNT_INFO", "Account information"),
    ("FEES", "Fees"),
    ("TRANSFER", "Transfers, beneficiaries and payments"),
    ("CARD_MANAGEMENT", "Card management"),
    ("CARD_REPLACEMENT", "Card replacement"),
    ("LOST_OR_STOLEN_CARD", "Lost or stolen card"),
    ("CARD_ISSUE", "Disputes and complaints"),
    ("EDIT_PERSONAL_DETAILS", "Profile and personal details"),
    ("GENERAL", "General questions and greetings"),
    ("NOT_IN_CHAT", "Not available in chat"),
)
NOT_IN_CHAT = "NOT_IN_CHAT"


@dataclass(frozen=True)
class UseCase:
    id: str
    name: str
    intent: str
    kind: str
    keys: tuple[tuple[str, ...], ...] = ()
    rows: tuple[str, ...] = ()
    app_action: str | None = None
    switchable: bool = True
    app_label: str | None = None  # how the app screen is named to a customer, when the action's own name misleads


def _u(key: str, name: str, intent: str, kind: str, *more_keys: tuple[str, str], rows=(), app_action=None,
       app_label=None) -> UseCase:
    category, service = key.split(".", 1)
    return UseCase(key, name, intent, kind, ((category, service),) + more_keys, tuple(rows), app_action,
                   app_label=app_label)


_PLATFORM: tuple[UseCase, ...] = (
    _u("account_info.balance", "Check account balance", "CHECK_BALANCE", "answer"),
    _u("card_info.credit_card_summary", "Credit card limit and amount due", "CHECK_BALANCE", "answer"),
    _u("polygon_services.transaction_history", "Transaction history and statements", "MINI_STATEMENT", "answer",
       ("account_info", "account_transactions")),
    _u("card_info.credit_card_statement", "Credit card statement", "MINI_STATEMENT", "answer"),
    _u("account_info.accounts", "List my accounts", "ACCOUNT_INFO", "answer"),
    _u("account_info.cards", "List my cards", "ACCOUNT_INFO", "answer"),
    _u("account_info.device_history", "Devices signed in to my profile", "ACCOUNT_INFO", "answer"),
    _u("account_info.login_history", "Login history", "ACCOUNT_INFO", "answer"),
    _u("account_info.fd_profit_history", "Fixed deposit profit history", "ACCOUNT_INFO", "answer"),
    _u("account_info.dps_profit_history", "DPS profit history", "ACCOUNT_INFO", "answer"),
    _u("loan_services.my_loans", "My loans", "ACCOUNT_INFO", "answer"),
    _u("fees.fee_quote", "Fee quote for sending money", "FEES", "answer"),
    _u("transfer.bank_transfer", "Send money to a bank account", "TRANSFER", "app_screen"),
    _u("transfer.wallet_transfer", "Send money to a mobile wallet", "TRANSFER", "app_screen"),
    _u("polygon_services.beneficiary", "Saved beneficiaries and sending to one", "TRANSFER", "answer"),
    _u("beneficiary_management.beneficiary_add", "Add a beneficiary", "TRANSFER", "confirmed_change"),
    _u("transfer_info.gifts_received", "Gifts I received", "TRANSFER", "answer"),
    _u("transfer_info.email_transfers", "Email transfers", "TRANSFER", "answer"),
    _u("transfer_info.qr_payment_history", "QR payment history", "TRANSFER", "answer"),
    _u("transfer_info.transfer_limit", "My transfer limits", "TRANSFER", "answer"),
    _u("card_services.frezz_unfrezz", "Freeze a card", "CARD_MANAGEMENT", "confirmed_change",
       app_action="card_unfreeze", app_label="Freeze or unfreeze card"),
    _u("card_info.card_limit_requests", "Card limit change requests (status)", "CARD_MANAGEMENT", "answer"),
    _u("card_info.card_products", "Cards the bank offers", "CARD_MANAGEMENT", "answer"),
    _u("card_info.virtual_card_requests", "Virtual card requests (status)", "CARD_MANAGEMENT", "answer"),
    _u("card_info.replacement_requests", "Card replacement requests (status)", "CARD_REPLACEMENT", "answer"),
    _u("card_requests.report_lost_card", "Report a lost or stolen card", "LOST_OR_STOLEN_CARD", "app_screen"),
    _u("service_requests.disputes", "My transaction disputes (status)", "CARD_ISSUE", "answer"),
    _u("service_requests.raise_dispute", "Raise a transaction dispute", "CARD_ISSUE", "app_screen"),
    _u("support.submit_complaint", "File a complaint", "CARD_ISSUE", "confirmed_change"),
    _u("polygon_services.my_tickets", "My complaints and tickets (status)", "CARD_ISSUE", "answer"),
    _u("profile.profile", "My profile details", "EDIT_PERSONAL_DETAILS", "answer"),
    _u("profile.address", "My address and KYC status", "EDIT_PERSONAL_DETAILS", "answer"),
    _u("profile.contacts", "My registered phone numbers and emails", "EDIT_PERSONAL_DETAILS", "answer"),
    _u("profile.profile_change_requests", "Profile change requests (status)", "EDIT_PERSONAL_DETAILS", "answer"),
    _u("profile.contact_priority_requests", "Primary contact change requests (status)", "EDIT_PERSONAL_DETAILS", "answer"),
    _u("profile_update.update_nickname", "Change my nickname", "EDIT_PERSONAL_DETAILS", "confirmed_change"),
    _u("profile_update.update_address", "Change my address", "EDIT_PERSONAL_DETAILS", "confirmed_change"),
    _u("profile_update.update_email", "Change my email address", "EDIT_PERSONAL_DETAILS", "confirmed_change"),
    _u("profile_update.update_mobile", "Change my mobile number", "EDIT_PERSONAL_DETAILS", "confirmed_change"),
    _u("profile_update.update_profile_image", "Change my profile photo", "EDIT_PERSONAL_DETAILS", "app_screen"),
)

# The bot's own answers (knowledge base and small talk): listed so the back office sees them, not switchable.
_GENERAL: tuple[UseCase, ...] = (
    UseCase("general.knowledge_answers", "Answers from the knowledge base", "GENERAL", "answer", switchable=False),
    UseCase("general.greetings", "Greetings and small talk", "GENERAL", "answer", switchable=False),
)

# App actions follow their routing domain unless named here.
_APP_ACTION_INTENT = {"replacement_cancel": "CARD_REPLACEMENT", "quick_view_star": "ACCOUNT_INFO",
                      "qr_payment_cards": "CARD_MANAGEMENT"}
# Platform services the chat hands over to an app action (see chat.py `_PLATFORM_TO_APP_ACTION`): one use case.
_PLATFORM_ALIAS = {"mobile_recharge": (("payments", "mobile_recharge"),)}
_DOMAIN_INTENT = {"cards": "CARD_MANAGEMENT", "transfers": "TRANSFER", "profile": "EDIT_PERSONAL_DETAILS",
                  "accounts": "ACCOUNT_INFO", "fees": "FEES", "other": "TRANSFER"}


def _app_action_use_cases() -> tuple[UseCase, ...]:
    out = []
    for action in ui_actions.UI_ACTIONS.values():
        domain = action.domain[0] if isinstance(action.domain, tuple) else action.domain
        intent = _APP_ACTION_INTENT.get(action.id) or _DOMAIN_INTENT.get(domain, "TRANSFER")
        kind = "app_screen" if action.kind == "screen" else "not_in_chat"
        out.append(UseCase(f"{ui_actions.CATEGORY}.{action.id}", action.name, intent, kind,
                           ((ui_actions.CATEGORY, action.id),) + _PLATFORM_ALIAS.get(action.id, ()), action.rows,
                           app_action=action.id if action.kind == "screen" else None,
                           switchable=action.kind != "unavailable"))
    return tuple(out)


EXPLICIT: tuple[UseCase, ...] = _PLATFORM + _GENERAL + _app_action_use_cases()
_BY_ID = {u.id: u for u in EXPLICIT}
_BY_KEY = {key: u.id for u in EXPLICIT for key in u.keys}


def use_case_for(category: str | None, service: str | None, subservice: str | None = None) -> str | None:
    """The use case a routed (category, service) belongs to, or None (unknown or not in chat)."""
    return _BY_KEY.get((category, service))


def name_of(use_case_id: str) -> str | None:
    use_case = _BY_ID.get(use_case_id)
    return use_case.name if use_case else None


def app_label_of(use_case_id: str) -> str | None:
    use_case = _BY_ID.get(use_case_id)
    return use_case.app_label if use_case else None


def ui_action_for_use_case(use_case_id: str) -> "ui_actions.UiAction | None":
    """The app action whose screen is offered when this use case is switched off, if it has one."""
    use_case = _BY_ID.get(use_case_id)
    action = ui_actions.get(use_case.app_action) if use_case and use_case.app_action else None
    return action if action is not None and action.kind == "screen" and action.route else None


def _not_in_chat() -> list[UseCase]:
    """Platform services the bot never routes to (bill payments, partners, ...): listed from the live taxonomy."""
    found = []
    for category in taxonomy.get_taxonomy().get("categories", []):
        if category.get("id") == ui_actions.CATEGORY:
            continue
        for service in category.get("services", []):
            key = (category["id"], service["id"])
            if key in _BY_KEY:
                continue
            found.append(UseCase(f"{key[0]}.{key[1]}", service.get("name") or service["id"].replace("_", " "),
                                 NOT_IN_CHAT, "not_in_chat", (key,), switchable=False))
    return found


def all_use_cases() -> list[UseCase]:
    return list(EXPLICIT) + _not_in_chat()


def catalog() -> dict:
    """What `GET /chat/use-cases` returns: intents in display order, each with its use cases."""
    use_cases = all_use_cases()
    intents = []
    for intent_id, intent_name in INTENTS:
        members = [u for u in use_cases if u.intent == intent_id]
        if not members:
            continue
        intents.append({
            "id": intent_id, "name": intent_name,
            "useCases": [{
                "id": u.id, "name": u.name, "kind": u.kind,
                "appScreen": ui_action_for_use_case(u.id) is not None,
                "switchable": u.switchable,
                "keys": [list(k) for k in u.keys], "rows": list(u.rows),
            } for u in members],
        })
    return {"intents": intents}
