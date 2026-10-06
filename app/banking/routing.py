"""Intent classification for /chat messages (ADR-0004, FR-ROUTE-01..05).

A single Ollama /api/chat tool-calling request decides whether a message is a
KB question, a banking-service request, or ambiguous. Per the T-11 spike, this
only works reliably with an explicit, numbered, rule-based system prompt that
embeds the live taxonomy — a minimal prompt or a tool-schema-only approach
without real taxonomy values reliably guesses a banking-service route instead
of asking for clarification.
"""

import json
import re
from dataclasses import dataclass

import httpx

from app.banking.session import ChatTurn
from app.banking import ui_actions
from app.banking.taxonomy import get_taxonomy, is_valid_path
from app.config import settings


@dataclass(frozen=True)
class KbQuestion:
    pass


@dataclass(frozen=True)
class BankingService:
    category: str
    service: str
    subservice: str | None = None
    payload: dict | None = None


@dataclass(frozen=True)
class Clarification:
    question: str
    # Names of the services the customer could have meant (the stage-1 domain's services),
    # so the reply can offer concrete choices instead of "what do you need?".
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnknownService:
    category: str
    service: str
    subservice: str | None = None


ClassificationResult = KbQuestion | BankingService | Clarification | UnknownService


_INVALID_PATH_CORRECTION = (
    "That category/service/subservice doesn't exist. Re-check the list above "
    "and either pick a real id, or call ask_clarification if you're not sure."
)


def _echoes(text: str, instruction: str) -> bool:
    """True when most of `text`'s words come from our own instruction -- the model
    repeating our prompt back instead of writing to the customer."""
    words = re.findall(r"[a-z]+", text.lower())
    source = set(re.findall(r"[a-z]+", instruction.lower()))
    return bool(words) and sum(w in source for w in words) / len(words) >= 0.6


def _only_category_of(service: str) -> str | None:
    """The single category holding `service` in the live taxonomy, or None if the id
    is unknown or (ambiguously) used by more than one category."""
    homes = {
        category.get("id")
        for category in (get_taxonomy() or {}).get("categories", [])
        for item in category.get("services", [])
        if item.get("id") == service
    }
    return homes.pop() if len(homes) == 1 else None


def _coerce_payload(raw: object) -> dict | None:
    """Normalize a tool-call `payload` argument into a dict or None.

    Ollama tool-calling (observed with qwen3:8b) can sometimes serialize the
    nested `payload` object as a JSON-encoded string instead of a real nested
    object. Downstream code (BankingService adapters) expects payload to be a
    dict or None, so coerce a JSON string into its parsed dict here rather
    than letting a `str` flow through and crash with `.get()` on a string
    later. Anything that isn't a dict (already, or after parsing) collapses
    to None instead of raising.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(raw, dict):
        return None
    # The model fills fields it has no value for with "" / null (e.g.
    # {"cardId": "", "isBilled": "", "month": ""}); an empty value is an unknown
    # value, so drop it -- downstream then asks for it or applies its default.
    cleaned = {k: v for k, v in raw.items() if v is not None and not (isinstance(v, str) and not v.strip())}
    return cleaned or None


# (category, service) -> (what the customer gets, payload fields it accepts).
# Only services with a real implementation behind them are listed; every other
# live taxonomy entry renders name-only. Field names mirror app/routes/chat.py's
# _REQUIRED_PAYLOAD_FIELDS and app/banking/adapters/real.py exactly.
SERVICE_DESCRIPTIONS: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {
    ("account_info", "balance"): ("current balance / how much money they have", ()),
    ("account_info", "accounts"): ("list or count of the customer's own bank accounts (account numbers, types)", ()),
    ("account_info", "device_history"): ("devices registered/logged in to their profile", ()),
    ("account_info", "login_history"): ("past login activity", ()),
    ("account_info", "cards"): ("list of the customer's cards", ()),
    ("account_info", "fd_profit_history"): ("profit earned on their fixed deposits (FD)", ()),
    ("account_info", "dps_profit_history"): ("profit earned on their DPS savings schemes", ()),
    ("loan_services", "my_loans"): (
        "overview/list/status of loans the customer currently holds",
        (),
    ),
    ("polygon_services", "transaction_history"): (
        "ANY request about transactions, spending, a statement or recent activity, for any or a "
        "specific account (which account is checked afterwards automatically)",
        ("startDate", "endDate"),
    ),
    ("polygon_services", "beneficiary"): (
        'send money to a saved beneficiary by their name, or list the saved beneficiaries',
        ("nameQuery", "amount"),
    ),
    ("beneficiary_management", "beneficiary_add"): (
        'add, save or register a new beneficiary (a recipient the customer wants to keep for later transfers), even when the name or account number is not given yet',
        ("nickname", "accountNumber", "bankName", "branchName", "routingNumber"),
    ),
    ("service_requests", "disputes"): ("VIEW the customer's existing transaction disputes and their status", ()),
    ("polygon_services", "my_tickets"): (
        "VIEW the customer's existing complaints / support tickets and their status",
        (),
    ),
    # account_info/account_transactions is deliberately NOT offered to the model: it
    # overlaps transaction_history (which already resolves/asks which account), and
    # two near-identical choices made llama3.1:8b ask "what do you mean" instead.
    # It stays in the taxonomy for explicit category+service requests.
    ("card_info", "card_limit_requests"): ('view the status of limit-change requests the customer has already submitted (it only shows existing requests)', ()),
    ("card_info", "card_products"): (
        "which cards the bank offers: any question about the card types/products available "
        "(not general knowledge — this bank's own live catalog)",
        (),
    ),
    ("card_info", "virtual_card_requests"): ('view the status of virtual-card requests the customer has already submitted (it only shows existing requests)', ()),
    ("card_info", "replacement_requests"): ('view the status of card replacement requests the customer has already submitted (it only shows existing requests)', ()),
    ("card_info", "credit_card_summary"): (
        "view the credit card's limit, outstanding or due amount and available credit (information only, no payment)",
        ("cardId",),
    ),
    ("card_info", "credit_card_statement"): (
        'view the credit card statement (billed or unbilled) for a month (information only, no payment)',
        ("cardId", "month", "isBilled"),
    ),
    ("profile", "profile"): ("the customer's own profile details (name, email, phone)", ()),
    ("profile", "address"): ("the customer's registered address / KYC status", ()),
    ("profile", "contacts"): ('the phone numbers and email addresses registered for the customer (which numbers or emails are on their account)', ()),
    ("profile", "profile_change_requests"): ('view the status of profile-change requests the customer has already submitted (it only shows existing requests)', ()),
    ("profile", "contact_priority_requests"): ('view the status of primary-contact change requests the customer has already submitted (it only shows existing requests)', ()),
    ("transfer_info", "gifts_received"): ("money gifts the customer has RECEIVED from others (incoming only, never sending)", ()),
    ("transfer_info", "email_transfers"): ("history/status of their email transfers", ()),
    ("transfer_info", "qr_payment_history"): ("history of their QR payments", ()),
    ("transfer_info", "transfer_limit"): (
        "their transfer limits (daily/weekly/per-transaction) and remaining amount",
        (),
    ),
    ("service_requests", "raise_dispute"): (
        "report a NEW problem with a transaction (money deducted but not received, failed "
        "or wrong transaction, wrong charge) or raise a new dispute",
        ("accountNumber", "transactionReferenceNo", "remarks"),
    ),
    ("card_requests", "report_lost_card"): (
        'the customer says their card is lost, stolen or was used by someone else and wants to report it or get it replaced, without asking to block it. reasonCode is one of LOST, STOLEN, DAMAGED, EXPIRED, OTHER',
        ("reasonCode",),
    ),
    ("support", "submit_complaint"): (
        "ANY message saying they want to make/file/lodge a complaint or complain (route it "
        "even if the complaint text is short, odd or a test; never ask_clarification for it) "
        "-- a NEW complaint about the bank's service, staff, app, an account, a "
        "card or a loan (a money problem with one specific transaction is raise_dispute "
        "instead). category is one of ACCOUNT, CARD, TRANSACTION, LOAN_DEPOSIT, "
        "MOBILE_APP_TECHNICAL, SERVICE_QUALITY, OTHER; description = what they are "
        "complaining about, in their words",
        ("category", "description"),
    ),
    ("profile_update", "update_nickname"): ("change their nickname (display name) in the app", ("nickName",)),
    ("profile_update", "update_address"): (
        "change their present and/or permanent address (or district/division)",
        ("presentAddress", "permanentAddress", "district", "division"),
    ),
    ("profile_update", "update_email"): ("change the email address on their profile", ("newEmail",)),
    ("profile_update", "update_mobile"): (
        "change the mobile number registered with the bank",
        ("newPhone",),
    ),
    ("profile_update", "update_profile_image"): ("change or upload their profile photo", ()),
    ("fees", "fee_quote"): (
        "live fee/charge for sending money. transactionType: to another bank (any bank name, "
        "NPSB, BEFTN, RTGS) = other_bank; to someone else's Polygon Bank account = "
        "city_account; between their own accounts = own_account; mobile wallets = the "
        "provider id; cash by code = cash_by_code",
        ("transactionType", "amount"),
    ),
    ("transfer", "bank_transfer"): (
        "send/transfer money; subservice required: own_account = moving money between the "
        "customer's OWN accounts (their other account, between their accounts; which "
        "account is looked up for them, so route even with no account number); "
        "other_bank = to an account at ANY bank other than Polygon Bank (whenever a bank "
        "name or abbreviation is mentioned); city_account = to someone else's account at "
        "Polygon Bank itself",
        ("accountNumber", "amount"),
    ),
    ("transfer", "wallet_transfer"): (
        "send to a mobile wallet number (subservice = provider)",
        ("walletNumber", "amount"),
    ),
    ("card_services", "frezz_unfrezz"): (
        'temporarily block (freeze or lock) a card: the customer asks to freeze, block or lock it, including when the card is also lost or stolen and they want it blocked right now. Unfreezing is a different request',
        ("reason",),
    ),
}


# Stage 1 of classification: the model first picks ONE domain (small, easy
# choice), then stage 2 picks the service among only that domain's services.
# One prompt holding all ~35 services confused llama3.1:8b (90/107 on the eval).
# T-79: every request the chat hands to the app (see ui_actions.py) is described like any service,
# with the optional fields the model may fill from what the customer wrote.
for _action in ui_actions.UI_ACTIONS.values():
    SERVICE_DESCRIPTIONS[(ui_actions.CATEGORY, _action.id)] = (
        _action.description, tuple(field for field, _ in _action.prefill))


DOMAINS: dict[str, tuple[str, frozenset[tuple[str, str]]]] = {
    "accounts": (
        "their balance, their list of accounts, transaction history, statements and what they spent, their login activity, and which devices are logged in",
        frozenset({("account_info", "balance"), ("account_info", "accounts"),
                   ("polygon_services", "transaction_history"),
                   ("account_info", "login_history"), ("account_info", "device_history")}),
    ),
    "deposits_loans": (
        "their loans, fixed deposits (FD/FDR), DPS, and the profit earned on them",
        frozenset({("loan_services", "my_loans"), ("account_info", "fd_profit_history"),
                   ("account_info", "dps_profit_history")}),
    ),
    "cards": (
        "their cards: listing them, card types the bank offers, card requests (limit change, "
        "virtual card, replacement), credit card limit/due/bill/statement, blocking a lost "
        "or stolen card, or any other card problem",
        frozenset({("account_info", "cards"), ("card_info", "card_products"),
                   ("card_info", "card_limit_requests"), ("card_info", "virtual_card_requests"),
                   ("card_info", "replacement_requests"), ("card_info", "credit_card_summary"),
                   ("card_info", "credit_card_statement"), ("card_services", "frezz_unfrezz"),
                   ("card_requests", "report_lost_card")}),
    ),
    "transfers": (
        "sending money (to a bank account, a mobile wallet or a saved person), saving a new "
        "recipient (beneficiary), their transfer limits, gifts received, email transfers, QR payment history",
        frozenset({("transfer", "bank_transfer"), ("transfer", "wallet_transfer"),
                   ("polygon_services", "beneficiary"),
                   ("beneficiary_management", "beneficiary_add"),
                   ("transfer_info", "transfer_limit"), ("transfer_info", "gifts_received"),
                   ("transfer_info", "email_transfers"), ("transfer_info", "qr_payment_history")}),
    ),
    "fees": ("what a transaction costs: fees, charges, VAT", frozenset({("fees", "fee_quote")})),
    "disputes": (
        "something that went wrong with money ALREADY sent, paid or withdrawn (deducted but "
        "not received, ATM gave no cash, charged twice, failed or wrong transaction), raising "
        "or viewing disputes, complaints and support tickets, or making a complaint",
        frozenset({("service_requests", "disputes"), ("service_requests", "raise_dispute"),
                   ("polygon_services", "my_tickets"), ("support", "submit_complaint")}),
    ),
    "profile": (
        "their personal details and the contact details registered for them (phone numbers, "
        "email, address, nickname, profile photo), changing those details, and the status of "
        "change requests",
        frozenset({("profile", "profile"), ("profile", "address"), ("profile", "contacts"),
                   ("profile", "profile_change_requests"),
                   ("profile", "contact_priority_requests"),
                   ("profile_update", "update_nickname"), ("profile_update", "update_address"),
                   ("profile_update", "update_email"), ("profile_update", "update_mobile"),
                   ("profile_update", "update_profile_image")}),
    ),
    "other": (
        "other bank services: bill/utility payments, mobile recharge, cheque books, applying "
        "for loans/cards/deposits, partners, remittance",
        frozenset(),
    ),
    "general": (
        "not about their own banking or this bank's products: greetings, thanks, general "
        "knowledge, off-topic, abuse, or too unclear to tell",
        frozenset(),
    ),
}


for _domain, (_desc, _keys) in list(DOMAINS.items()):
    DOMAINS[_domain] = (_desc, _keys | ui_actions.keys_for_domain(_domain))


def fee_transaction_types(taxonomy: dict | None = None) -> list[str]:
    """The bank's own transaction-type ids a fee quote accepts (`appSettingsId`):
    the leaves of the live transfer menu (wallet providers, own/city/other bank).
    Free text like "bkash transfer" or "NPSB" is a 404 on the bank's side."""
    taxonomy = taxonomy if taxonomy is not None else (get_taxonomy() or {})
    ids: list[str] = []
    for category in taxonomy.get("categories", []):
        if category.get("id") != "transfer":
            continue
        for service in category.get("services", []):
            subs = [sub["id"] for sub in service.get("subServices") or [] if sub.get("id")]
            # A menu item with no sub-types (e.g. cash_by_code) is itself a type.
            ids.extend(subs or ([service["id"]] if service.get("id") else []))
    return ids


def _render_taxonomy(
    taxonomy: dict, allowed: frozenset | None = None, include_other: bool = True
) -> str:
    """Render the live taxonomy for the classifier prompt.

    Services with an entry in SERVICE_DESCRIPTIONS (i.e. a real implementation)
    are listed first, one self-contained line each, with what the customer gets and
    the payload fields it accepts. Every other live entry is listed name-only,
    one line per category. Only ids present in the live taxonomy are rendered.
    `allowed` limits the described services to one domain's set; `include_other`
    controls the name-only section.
    """
    supported = []
    other = []
    for category in taxonomy.get("categories", []):
        described_lines = []
        other_services = []
        for service in category.get("services", []):
            subs = ", ".join(
                f"{sub['id']} ({sub['name']})" for sub in service.get("subServices", [])
            )
            described = SERVICE_DESCRIPTIONS.get((category["id"], service["id"]))
            if described and allowed is not None and (category["id"], service["id"]) not in allowed:
                continue
            if described:
                description, fields = described
                line = (
                    f'- category="{category["id"]}" service="{service["id"]}": {description}'
                )
                if subs:
                    line += f". subservices: {subs}"
                else:
                    line += ". no subservice"
                if fields:
                    line += f". payload: {', '.join(fields)}"
                if (category["id"], service["id"]) == ("fees", "fee_quote"):
                    types = fee_transaction_types(taxonomy)
                    if types:
                        line += f". transactionType must be one of: {', '.join(types)}"
                described_lines.append(line)
            else:
                other_services.append(
                    f"{service['id']} ({service['name']})" + (f" [{subs}]" if subs else "")
                )
        supported.extend(described_lines)
        if other_services and include_other:
            other.append(
                f"- {category['id']} ({category['name']}): " + "; ".join(other_services)
            )
    sections = []
    if supported:
        sections.append("Supported services:\n" + "\n".join(supported))
    if other:
        sections.append(
            "Other services (category: service [subservices]) — use only when the message "
            "clearly names exactly one of these:\n" + "\n".join(other)
        )
    return "\n\n".join(sections)


# How the model reads a written amount. Guidance for the model, not a lookup in code:
# the unit words are part of what the customer wrote, so they must be applied, never dropped.
AMOUNT_GUIDANCE = (
    "a plain number of taka with any unit the customer wrote applied (thousand/k/hajar "
    "= ×1,000; lakh/lac = ×100,000; crore/koti = ×10,000,000, fractions allowed) — "
    "never drop a unit and never round"
)


def build_system_prompt(
    taxonomy: dict, allowed: frozenset | None = None, include_other: bool = True
) -> str:
    return (
        "You classify ONE customer message for a bank's chat assistant by calling exactly one "
        "tool. Customers write in English, Bangla or Banglish (romanized Bangla) with any "
        "phrasing — understand what they mean, don't match keywords.\n\n"
        "Anything about the customer's own banking (money, balance, accounts, cards, loans, "
        "deposits, transactions, transfers, fees, complaints, disputes, profile) is a service "
        "request, however short, informal, rude or misspelled.\n\n"
        "DECIDE IN THIS ORDER\n"
        "1. The customer wants to see or change something that one service below describes "
        "-> route_banking_service for that service. Read misspelled and very short messages "
        "by sound and meaning: a single word naming something the customer owns (balance, "
        "loan, cards, transactions) is that lookup.\n"
        "2. The customer asks what a transfer or transaction would cost (fee, charge, VAT), "
        "however it is worded -> fees/fee_quote. A transfer type and amount are asked for "
        "afterwards, so route first. A complaint about a charge already taken is a dispute.\n"
        "3. The customer wants to send money -> a transfer service as soon as the destination "
        "type is known: their own account (own_account, always, their accounts are looked up), "
        "another Polygon Bank account, another bank, or a named wallet provider, with the "
        "matching subservice; an account or wallet number with a bank or provider also "
        "counts. A saved person's name -> polygon_services/beneficiary with nameQuery. "
        "Saving a new recipient -> beneficiary_management/beneficiary_add. No destination at "
        "all -> ask_clarification asking where to send it.\n"
        "4. Cards: lost or stolen -> card_requests/report_lost_card; the customer also (or "
        "only) asks to block, freeze or lock it -> the card freeze service; a card problem "
        "that doesn't say what is wrong -> ask_clarification asking what the problem is.\n"
        "5. A topic with no ask (the message names an area such as fees, a card or a transfer "
        "and nothing the customer wants done) -> ask_clarification asking what exactly they "
        "need. Wanting to change a profile detail -> the matching profile_update service, "
        "never a lookup, with a new value in payload only if they wrote it.\n"
        "6. The customer wants to DO something in the app that the app_actions services below "
        "cover (change, cancel, apply, pay, reset, unfreeze, star, delete, submit...) -> the "
        "matching app_actions service, with any detail they gave in payload. A lookup of what "
        "they already have or submitted stays a lookup. Something no service below covers at "
        "all -> ask_clarification, saying in your own words that this can be done in the app "
        "and asking what else they need; never pick the nearest-looking lookup for it.\n"
        "7. General banking knowledge (other than fees), non-banking topics and abuse with no "
        "request -> answer_kb_question. A greeting, or a message with nothing to act on -> "
        "ask_clarification.\n\n"
        "HOW TO FILL THE CALL\n"
        "- Copy category and service exactly as they appear together on one line below, and "
        "give subservice only for a service that lists subservices.\n"
        "- payload holds only fields listed for that service and only values the customer "
        f"wrote (amount: {AMOUNT_GUIDANCE}; account and wallet numbers as digit strings). "
        "Leave unknown fields out; PINs, passwords, OTPs and CVVs stay out.\n"
        "- Missing details are collected later, so route first. Your ask_clarification "
        "question is your own short question about exactly what is unclear.\n"
        "- Viewing existing disputes -> service_requests/disputes; existing complaints or "
        "tickets -> polygon_services/my_tickets; raising a dispute or describing a problem "
        "with a past transaction -> service_requests/raise_dispute; what the bank offers "
        "(card types) -> card_info/card_products.\n\n"
        f"{_render_taxonomy(taxonomy, allowed, include_other)}"
    )


def build_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "answer_kb_question",
                "description": (
                    "Answer a general knowledge-base question that is not a request to perform "
                    "an action on the customer's own account."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "route_banking_service",
                "description": (
                    "Route the message to the banking service whose description matches what "
                    "the customer means, using ids from the provided taxonomy list."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "The category id from the taxonomy list.",
                        },
                        "service": {
                            "type": "string",
                            "description": "The service id from the taxonomy list.",
                        },
                        "subservice": {
                            "type": "string",
                            "description": "The subservice id from the taxonomy list, if any.",
                        },
                        "payload": {
                            "type": "object",
                            "description": (
                                "Only the payload fields listed for the chosen service, with "
                                "values the customer actually stated. Omit entirely if none."
                            ),
                        },
                    },
                    "required": ["category", "service"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ask_clarification",
                "description": (
                    "Ask the customer a short clarifying question, written for this message, "
                    "when no single service clearly fits. Never guess a service."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The clarifying question to ask the customer.",
                        },
                    },
                    "required": ["question"],
                },
            },
        },
    ]


_CLARIFICATION_FALLBACK = "Could you tell me more specifically what you'd like to do?"


async def _post_classification(messages: list[dict]) -> list[dict]:
    async with httpx.AsyncClient(timeout=None) as client:
        resp = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": settings.OLLAMA_CLASSIFY_MODEL,
                "messages": messages,
                "tools": build_tools(),
                "stream": False,
                "think": settings.OLLAMA_THINK,
                "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0},
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("message", {}).get("tool_calls") or []


class _Domain(str):
    """A DOMAINS key that also remembers what the customer wants from it: "see" (look at
    information they have) or "do" (have something changed, created, cancelled, paid or sent).
    A plain str everywhere else, so existing callers and test patches are unaffected."""
    wants: str | None = None


# Services that DO something (or start doing it); everything else in a domain only shows
# information. Used to keep "I want to change my limit" away from "status of my limit requests".
_DO_KEYS = frozenset({
    ("card_services", "frezz_unfrezz"), ("card_requests", "report_lost_card"),
    ("transfer", "bank_transfer"), ("transfer", "wallet_transfer"),
    ("polygon_services", "beneficiary"), ("beneficiary_management", "beneficiary_add"),
    ("support", "submit_complaint"), ("service_requests", "raise_dispute"),
    ("profile_update", "update_nickname"), ("profile_update", "update_address"),
    ("profile_update", "update_email"), ("profile_update", "update_mobile"),
    ("profile_update", "update_profile_image"),
}) | ui_actions.keys()


_DOMAIN_EXAMPLES = (
    ("blance", "accounts", "see"),
    ("amar card ta hariye gese", "cards", "do"),
    ("hi, last week i paid a shop and it got charged twice, what do i do", "disputes", "do"),
    ("what's the weather like", "general", "see"),
)


async def _pick_domain(message: str, recent_turns: list[ChatTurn] | None) -> str | None:
    """Stage 1: which domain is this message about? Returns a DOMAINS key, or None
    on any failure (caller then falls back to the full single-stage prompt)."""
    domains = "\n".join(f"- {key}: {desc}" for key, (desc, _) in DOMAINS.items())
    context = ""
    if recent_turns:
        last = recent_turns[-1].classification or {}
        question = last.get("question")
        if question:
            context = (
                f'\nThe assistant just asked the customer: "{question}". If the new message '
                "answers that question, pick the domain that question is about.\n"
            )
    system = (
        "You route a bank customer's chat message to ONE domain, by what the customer wants.\n"
        "1. Customers write English, Bangla or Banglish (romanized Bangla), often in one or "
        "two words, with typos or missing letters. Read a word by how it sounds, and Banglish "
        "by its English meaning.\n"
        "2. A banking word on its own belongs to its banking domain.\n"
        "3. Choose the domain whose description covers what they want to see, do or fix.\n"
        '4. Also say what they want: "see" when they want to look at information they have (a '
        'balance, a list, a status, a statement), or "do" when they want something changed, '
        'created, cancelled, applied for, paid, sent, reset or fixed.\n\n'
        f"Domains:\n{domains}\n{context}\n"
        'Reply only with JSON: {"domain": "<one domain key>", "wants": "see" or "do"}'
    )
    # Worked examples as earlier turns (a typo, Banglish, a messy request, a non-banking
    # message): the shape of a good answer for the 8B, not an exhaustive list.
    messages = [{"role": "system", "content": system}]
    for sample, answer, wants in _DOMAIN_EXAMPLES:
        messages += [{"role": "user", "content": sample},
                     {"role": "assistant", "content": json.dumps({"domain": answer, "wants": wants})}]
    messages.append({"role": "user", "content": message})
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_CLASSIFY_MODEL,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0},
                },
            )
            resp.raise_for_status()
            parsed = json.loads((resp.json().get("message") or {}).get("content") or "{}")
            domain = parsed.get("domain")
    except Exception:
        return None
    if domain not in DOMAINS:
        return None
    picked = _Domain(domain)
    picked.wants = parsed.get("wants") if parsed.get("wants") in ("see", "do") else None
    return picked


async def _domain_scope(
    message: str, recent_turns: list[ChatTurn] | None
) -> tuple[frozenset | None, bool]:
    """(allowed services, include name-only other services) for stage 2. A banking
    domain narrows stage 2 to that domain's services (plus the service a pending
    clarification is about, so a reply can still complete it); anything else keeps
    the full single-stage prompt."""
    domain = await _pick_domain(message, recent_turns)
    if domain is None or domain in ("general", "other"):
        return None, True
    allowed = set(DOMAINS[domain][1])
    wants = getattr(domain, "wants", None)
    if wants == "do":
        # Something to be changed, created or sent: not the lookups that only show status.
        # (Kept only when the domain has such services, so a misjudgement can't empty the menu.)
        allowed = (allowed & _DO_KEYS) or allowed
    elif wants == "see":
        allowed -= ui_actions.keys()
    # Fees and transfers are always offered together: "how much does it cost to send
    # 5000 to nagad?" reads like a transfer, and with the fee service missing from
    # stage 2 the model could only pick a transfer or ask.
    if domain in ("transfers", "fees"):
        allowed |= DOMAINS["transfers"][1] | DOMAINS["fees"][1]
    if recent_turns:
        last = recent_turns[-1].classification or {}
        if last.get("category") and last.get("service"):
            allowed.add((last["category"], last["service"]))
    return frozenset(allowed), False


def _subservice_ids(category: str, service: str) -> list[str]:
    """Subservice ids of one service, in taxonomy order, read from the live taxonomy."""
    for cat in (get_taxonomy() or {}).get("categories", []):
        if cat.get("id") != category:
            continue
        for svc in cat.get("services", []):
            if svc.get("id") == service:
                return [sub["id"] for sub in svc.get("subServices") or [] if sub.get("id")]
    return []


def _send_after_fee_hint(previous: dict) -> str:
    """After a fee quote, a wish to go ahead means: start THAT transfer. Destination ids
    come from the taxonomy, never a hardcoded wallet list."""
    if (previous.get("category"), previous.get("service")) != ("fees", "fee_quote"):
        return ""
    request = previous.get("request") or {}
    kind = request.get("transactionType")
    target = None
    for service in ("wallet_transfer", "bank_transfer"):
        if kind in _subservice_ids("transfer", service):
            target = f'category="transfer", service="{service}", subservice="{kind}"'
    if target is None:
        return ""
    amount = request.get("amount")
    payload = f', payload={{"amount": {amount}}}' if amount else ""
    return (
        "If the customer now wants to actually send that money, in any wording, call "
        f"route_banking_service({target}{payload}). "
    )


def _option_names(allowed: frozenset | None, limit: int = 8) -> tuple[str, ...]:
    """Plain names (from the live catalog) of the services in `allowed`, for offering choices."""
    if not allowed:
        return ()
    names: list[str] = []
    for category in (get_taxonomy() or {}).get("categories", []):
        for service in category.get("services", []):
            if (category.get("id"), service.get("id")) in allowed and service.get("name") not in names:
                names.append(service["name"])
    return tuple(names[:limit])


async def classify(
    message: str, recent_turns: list[ChatTurn] | None = None
) -> ClassificationResult:
    allowed, include_other = await _domain_scope(message, recent_turns)
    result = await _classify_scoped(message, recent_turns, allowed, include_other)
    if isinstance(result, Clarification) and not result.options:
        return Clarification(result.question, _option_names(allowed))
    return result


async def _classify_scoped(
    message: str, recent_turns: list[ChatTurn] | None, allowed: frozenset | None, include_other: bool
) -> ClassificationResult:
    messages = [{
        "role": "system",
        "content": build_system_prompt(get_taxonomy(), allowed, include_other),
    }]
    if recent_turns:
        last_turn = recent_turns[-1]
        last_classification = last_turn.classification or {}
        pending_question = last_classification.get("question") or "a clarifying question"
        if last_classification.get("type") == "BANKING_SERVICE":
            # The last request was ANSWERED; the customer may follow up on it with just
            # the detail that changes ("and for nagad?", "what about 3000?").
            prev = f'category="{last_classification.get("category")}", service="{last_classification.get("service")}"'
            details = json.dumps(last_classification.get("request") or {}, ensure_ascii=False)
            messages.append({
                "role": "system",
                "content": (
                    "PREVIOUS ANSWERED REQUEST: the customer's last message "
                    f'"{last_turn.message}" was answered as route_banking_service({prev}) with '
                    f"payload {details}. If the new message is a short follow-up that only "
                    "changes or adds a detail of that same request (another provider, bank or "
                    "amount, \"and for X?\", \"what about Y?\"), call "
                    f"route_banking_service({prev}) with ONLY the changed/added details in "
                    "payload. " + _send_after_fee_hint(last_classification)
                    + "Otherwise ignore this and classify the new message on its own."
                ),
            })
        elif last_classification.get("type") == "ACCOUNT_SELECTION_REQUIRED":
            # T-59: ACCOUNT_SELECTION_REQUIRED is a structurally different pending state
            # from a genuine CLARIFICATION_REQUIRED (the general branch below) — it never
            # means the intent itself is ambiguous. The category/service/subservice are
            # already fully and certainly known (stored on the turn itself); the only open
            # question is which of the customer's own EXISTING accounts to use. Confirmed
            # live: feeding this through the generic branch below let the new message's
            # surface wording ("account(s)") collide with the Transfer-specific rule's own
            # "raw account number" examples, hijacking an unrelated message (e.g. "how many
            # accounts do i have?") into a transfer clarification. This dedicated branch
            # states the already-known category/service/subservice explicitly and rules out
            # transfer/wallet/beneficiary reinterpretation by name, rather than leaving the
            # model to infer "this has nothing to do with transfers" on its own.
            pending_category = last_classification.get("category")
            pending_service = last_classification.get("service")
            pending_subservice = last_classification.get("subservice")
            service_args = f'category="{pending_category}", service="{pending_service}"'
            if pending_subservice:
                service_args += f', subservice="{pending_subservice}"'
            general_reasoning = (
                "PENDING ACCOUNT SELECTION (read first — overrides the general decision "
                f"rules above for this one reply): the customer's request — "
                f"{pending_category}/{pending_service}"
                + (f"/{pending_subservice}" if pending_subservice else "")
                + f' — is ALREADY fully identified and certain. You asked "{pending_question}" '
                "only because the customer has more than one of THEIR OWN EXISTING accounts "
                "and the system needs to know which one to use for that already-identified "
                "request. This is purely picking among accounts the customer already owns — "
                "it has NOTHING to do with a transfer destination, a wallet, a beneficiary, or "
                "sending money anywhere, even though the word \"account\"/\"accounts\" appears "
                "in both the question and possibly the new message too; that word overlap is a "
                "coincidence, never a signal to route to transfer/wallet_transfer, "
                "transfer/bank_transfer, or polygon_services/beneficiary.\n"
                "Only treat the customer's new message below as answering this pending "
                "selection when it clearly names ONE of the specific accounts listed in the "
                "question above (by its type, or by the last few "
                "digits of its number). In that case, call route_banking_service "
                f"with EXACTLY {service_args} — the SAME category/service/subservice already "
                "identified, never a different one — and, if the message named the account's "
                'type, include it as payload={"accountType": "<type named>"} (omit payload '
                "entirely if only a number was named).\n"
                "If the new message does NOT clearly name one of the listed accounts, it is a "
                "fresh, unrelated message — classify it independently using ONLY the general "
                "decision rules above, exactly as if this pending selection had never "
                "happened. Never guess which account was meant."
            )
            worked_example = (
                "\n- A message about the customer's accounts in general (how many, which ones) "
                "names none of the listed accounts: classify it on its own.\n"
                "- A message naming one listed account's type or last digits answers the "
                "selection.\n"
                "- A different subject altogether: classify it on its own, never as an "
                "account-selection answer."
            )
        else:
            # T-53: broaden what counts as "answering" a pending clarification beyond bare
            # nouns/amounts/yes-or-no — a full-sentence reply that names the missing piece the
            # question asked for (e.g. "I want to transfer money to bkash" naming a transaction
            # type) is still an answer, not a new unrelated request, even though it reads like
            # one. This is a general context-continuity fix, not fees-specific: any pending
            # clarification's genuine answer can be phrased as a full sentence of intent.
            general_reasoning = (
                f'PENDING CLARIFICATION (read first — overrides the general decision rules above '
                f'for this one reply): you previously asked the customer "{pending_question}" in '
                f'response to their message "{last_turn.message}", and got no clear answer yet. As '
                "a general rule, treat the customer's new message below as the answer to THAT "
                "pending question whenever it names or implies the missing piece the question "
                "asked for — even when "
                "it's phrased as a full sentence describing an action rather than a bare word. "
                "Only treat the new message as a genuinely new, unrelated request when it "
                "changes the subject to a different KIND of thing entirely."
            )
            # The bulleted, imperative worked example below (naming the exact tool call to make)
            # is dramatically more reliable in practice than reasoning/narrative prose alone —
            # confirmed live (T-53) that qwen3:8b's tool-call choice needs a concrete grounded
            # example, not just an abstract rule, to reliably resist matching the new message's
            # surface wording (e.g. "transfer"/"bkash") to an unrelated taxonomy path. Only
            # include it when the pending question we actually asked was itself a fee-quote
            # question (detected from its own text) — never assert this fees/fee_quote-specific
            # resolution for some other pending clarification (e.g. a card-help question), where
            # it would be wrong.
            pending_category = last_classification.get("category")
            pending_service = last_classification.get("service")
            if pending_category and pending_service:
                # The pending question is about a KNOWN service (we asked for its missing
                # details). Name it -- the old check looked for the words "fee quote" in
                # the question text, which LLM-worded questions never contain, so fee
                # follow-ups ("bkash", "1000") lost their context.
                target = f'category="{pending_category}", service="{pending_service}"'
                if last_classification.get("subservice"):
                    target += f', subservice="{last_classification["subservice"]}"'
                missing = ", ".join(last_classification.get("missingFields") or []) or "the missing details"
                worked_example = (
                    f"\n- The pending question asked for: {missing}. If the new message gives any "
                    "of that — a bare word, a number, or a full sentence, however phrased — call "
                    f"route_banking_service({target}) with ONLY the details it gives in payload. "
                    "Never switch to a different service just because the wording overlaps "
                    "another feature.\n"
                    "- Only classify independently per the general rules above if the new message "
                    "is a genuine subject change (a different kind of thing entirely)."
                )
            else:
                worked_example = (
                    "\n- If the new message supplies the missing piece, resolve it using the SAME "
                    "category/service the pending question was already about — do not switch to a "
                    "different, unrelated category/service just because the new message's wording "
                    "happens to overlap with another feature's vocabulary.\n"
                    "- If the new message still doesn't supply what the pending question needs, "
                    "call ask_clarification, repeating what's still missing.\n"
                    "- Only classify independently per the general rules above if the new message "
                    "is a genuine subject change (a different kind of thing entirely, not just a "
                    "different phrasing of the same answer)."
                )
        if last_classification.get("type") != "BANKING_SERVICE":
            messages.append({
                "role": "system",
                "content": general_reasoning + worked_example,
            })
    messages.append({"role": "user", "content": message})

    tool_calls = await _post_classification(messages)
    if not tool_calls:
        # First attempt called no tool at all (confirmed live on genuine banking requests,
        # e.g. "how much money do I have in my account?") — retry once with a corrective
        # message rather than silently falling through to the KB/RAG path, which would give
        # a generic refusal instead of the real answer. See T-40.
        retry_messages = messages + [
            {
                "role": "user",
                "content": (
                    "You didn't call any tool. Call route_banking_service if this is a banking "
                    "request, ask_clarification if you're not sure what they want, or "
                    "answer_kb_question only if this is a general knowledge question unrelated "
                    "to the customer's own account."
                ),
            },
        ]
        retry_tool_calls = await _post_classification(retry_messages)
        if not retry_tool_calls:
            return Clarification(question=_CLARIFICATION_FALLBACK)

        retry_call = retry_tool_calls[0]["function"]
        retry_name = retry_call["name"]
        retry_arguments = retry_call.get("arguments", {})

        if retry_name == "answer_kb_question":
            return KbQuestion()
        if retry_name == "ask_clarification":
            question = retry_arguments.get("question") or ""
            # Live: the model "asked" the customer our own correction text back
            # ("That category/service/subservice doesn..."). Never show that.
            if not question or _echoes(question, _INVALID_PATH_CORRECTION):
                return Clarification(question=_CLARIFICATION_FALLBACK)
            return Clarification(question=question)
        if retry_name == "route_banking_service":
            retry_category = retry_arguments.get("category")
            retry_service = retry_arguments.get("service")
            retry_subservice = retry_arguments.get("subservice") or None
            retry_payload = _coerce_payload(retry_arguments.get("payload"))
            if retry_category and retry_service and is_valid_path(
                retry_category, retry_service, retry_subservice
            ):
                return BankingService(
                    category=retry_category,
                    service=retry_service,
                    subservice=retry_subservice,
                    payload=retry_payload,
                )
            return Clarification(question=_CLARIFICATION_FALLBACK)

        return Clarification(question=_CLARIFICATION_FALLBACK)

    call = tool_calls[0]["function"]
    name = call["name"]
    arguments = call.get("arguments", {})

    if name == "answer_kb_question":
        return KbQuestion()
    if name == "ask_clarification":
        return Clarification(question=arguments.get("question") or _CLARIFICATION_FALLBACK)
    if name == "route_banking_service":
        category = arguments.get("category")
        service = arguments.get("service")
        subservice = arguments.get("subservice") or None
        payload = _coerce_payload(arguments.get("payload"))
        if category and service and is_valid_path(category, service, subservice):
            return BankingService(
                category=category, service=service, subservice=subservice, payload=payload
            )
        # Right service under the wrong category (live: "trnsactions" ->
        # account_info/transaction_history). Service ids are unique, so the category
        # can be corrected instead of discarding a correct pick.
        home = _only_category_of(service) if service else None
        if home and is_valid_path(home, service, subservice):
            return BankingService(category=home, service=service, subservice=subservice, payload=payload)

        # First attempt hallucinated a category/service/subservice id that doesn't exist
        # anywhere in the real taxonomy (confirmed live: genuine model nondeterminism, not
        # a fixable prompt/schema issue — see T-23). Retry once with a corrective message
        # before falling back to a generic clarification, so a wrong-but-plausible guess
        # doesn't become a confident "that's not available" to the customer.
        retry_messages = messages + [
            {"role": "assistant", "content": "", "tool_calls": [tool_calls[0]]},
            {"role": "user", "content": _INVALID_PATH_CORRECTION},
        ]
        retry_tool_calls = await _post_classification(retry_messages)
        if not retry_tool_calls:
            return Clarification(question=_CLARIFICATION_FALLBACK)

        retry_call = retry_tool_calls[0]["function"]
        retry_name = retry_call["name"]
        retry_arguments = retry_call.get("arguments", {})

        if retry_name == "answer_kb_question":
            return KbQuestion()
        if retry_name == "ask_clarification":
            question = retry_arguments.get("question") or ""
            # Live: the model "asked" the customer our own correction text back
            # ("That category/service/subservice doesn..."). Never show that.
            if not question or _echoes(question, _INVALID_PATH_CORRECTION):
                return Clarification(question=_CLARIFICATION_FALLBACK)
            return Clarification(question=question)
        if retry_name == "route_banking_service":
            retry_category = retry_arguments.get("category")
            retry_service = retry_arguments.get("service")
            retry_subservice = retry_arguments.get("subservice") or None
            retry_payload = _coerce_payload(retry_arguments.get("payload"))
            if retry_category and retry_service and is_valid_path(
                retry_category, retry_service, retry_subservice
            ):
                return BankingService(
                    category=retry_category,
                    service=retry_service,
                    subservice=retry_subservice,
                    payload=retry_payload,
                )
            return Clarification(question=_CLARIFICATION_FALLBACK)

        return Clarification(question=_CLARIFICATION_FALLBACK)

    return KbQuestion()
