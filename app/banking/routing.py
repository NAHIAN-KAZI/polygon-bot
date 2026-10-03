"""Intent classification for /chat messages (ADR-0004, FR-ROUTE-01..05).

A single Ollama /api/chat tool-calling request decides whether a message is a
KB question, a banking-service request, or ambiguous. Per the T-11 spike, this
only works reliably with an explicit, numbered, rule-based system prompt that
embeds the live taxonomy — a minimal prompt or a tool-schema-only approach
without real taxonomy values reliably guesses a banking-service route instead
of asking for clarification.
"""

import json
from dataclasses import dataclass

import httpx

from app.banking.session import ChatTurn
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


@dataclass(frozen=True)
class UnknownService:
    category: str
    service: str
    subservice: str | None = None


ClassificationResult = KbQuestion | BankingService | Clarification | UnknownService


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
        "send money to an EXISTING saved beneficiary by their name, or list beneficiaries",
        ("nameQuery", "amount"),
    ),
    ("beneficiary_management", "beneficiary_add"): (
        "add/save/register a NEW beneficiary (any add-a-beneficiary request; route even if name or account number is missing)",
        ("nickname", "accountNumber"),
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
    ("card_info", "card_limit_requests"): ("status of their card limit-change requests", ()),
    ("card_info", "card_products"): (
        "which cards the bank offers: any question about the card types/products available "
        "(not general knowledge — this bank's own live catalog)",
        (),
    ),
    ("card_info", "virtual_card_requests"): ("status of their virtual card requests", ()),
    ("card_info", "replacement_requests"): ("status of their card replacement requests", ()),
    ("card_info", "credit_card_summary"): (
        "credit card limit, outstanding/due amount, available credit",
        ("cardId",),
    ),
    ("card_info", "credit_card_statement"): (
        "credit card statement (billed or unbilled) for a month",
        ("cardId", "month", "isBilled"),
    ),
    ("profile", "profile"): ("the customer's own profile details (name, email, phone)", ()),
    ("profile", "address"): ("the customer's registered address / KYC status", ()),
    ("profile", "contacts"): ("which phone numbers and email addresses are registered with the bank for them", ()),
    ("profile", "profile_change_requests"): ("status of their profile change requests", ()),
    ("profile", "contact_priority_requests"): ("status of their primary-contact change requests", ()),
    ("transfer_info", "gifts_received"): ("money gifts the customer has RECEIVED from others (incoming only, never sending)", ()),
    ("transfer_info", "email_transfers"): ("history/status of their email transfers", ("id",)),
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
    ("fees", "fee_quote"): (
        "live fee/charge for a transaction type and amount",
        ("transactionType", "amount"),
    ),
    ("transfer", "bank_transfer"): (
        "send/transfer money to their own account, another Polygon Bank account, or an "
        "account at another bank (a bank named by name or abbreviation); subservice required",
        ("accountNumber", "amount"),
    ),
    ("transfer", "wallet_transfer"): (
        "send to a mobile wallet number (subservice = provider)",
        ("walletNumber", "amount"),
    ),
    ("card_services", "frezz_unfrezz"): (
        "freeze/block a card ONLY when the customer says it is lost, stolen or compromised, or "
        "explicitly asks to block/freeze it. A card problem that doesn't say what is wrong is "
        "NOT this (ask_clarification). Never for unfreezing",
        ("reason",),
    ),
}


# Stage 1 of classification: the model first picks ONE domain (small, easy
# choice), then stage 2 picks the service among only that domain's services.
# One prompt holding all ~35 services confused llama3.1:8b (90/107 on the eval).
DOMAINS: dict[str, tuple[str, frozenset[tuple[str, str]]]] = {
    "accounts": (
        "their balance, their accounts, transactions/statements/spending, login activity, devices or phones logged in to their banking",
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
                   ("card_info", "credit_card_statement"), ("card_services", "frezz_unfrezz")}),
    ),
    "transfers": (
        "sending money (to a bank account, a mobile wallet, or a saved person), adding a "
        "beneficiary, their transfer limits, gifts received, email transfers, QR payments",
        frozenset({("transfer", "bank_transfer"), ("transfer", "wallet_transfer"),
                   ("polygon_services", "beneficiary"),
                   ("beneficiary_management", "beneficiary_add"),
                   ("transfer_info", "transfer_limit"), ("transfer_info", "gifts_received"),
                   ("transfer_info", "email_transfers"), ("transfer_info", "qr_payment_history")}),
    ),
    "fees": ("what a transaction costs: fees, charges, VAT", frozenset({("fees", "fee_quote")})),
    "disputes": (
        "a problem with a transaction, raising or viewing disputes, complaints and support tickets",
        frozenset({("service_requests", "disputes"), ("service_requests", "raise_dispute"),
                   ("polygon_services", "my_tickets")}),
    ),
    "profile": (
        "their personal details: profile, address, contact numbers/emails, and their requests "
        "to change them",
        frozenset({("profile", "profile"), ("profile", "address"), ("profile", "contacts"),
                   ("profile", "profile_change_requests"),
                   ("profile", "contact_priority_requests")}),
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


def build_system_prompt(
    taxonomy: dict, allowed: frozenset | None = None, include_other: bool = True
) -> str:
    return (
        "You classify ONE customer message for a bank's chat assistant by calling exactly one "
        "tool. Customers write in English, Bangla or Banglish (romanized Bangla) with any "
        "phrasing — understand what they mean, don't match keywords.\n\n"
        "Decide in this order:\n"
        "A. If the message — however short, informal, rude or misspelled — is about the "
        "customer's own banking (their money, balance, accounts, cards, loans, deposits, "
        "profits, transactions, transfers, fees, complaints/disputes), it is a service "
        "request: call route_banking_service when one supported service below fits its "
        "meaning, otherwise ask_clarification.\n"
        "B. A greeting or an empty/unclear banking message -> ask_clarification.\n"
        "C. Only general banking knowledge (\"what is...\", \"how does... work\") other than "
        "fees, non-banking topics, or pure abuse with no request -> answer_kb_question.\n"
        "ask_clarification questions are always your OWN short question naming exactly what "
        "is unclear in THIS message.\n\n"
        "Rules:\n"
        "1. Match the MEANING of the message to a supported service's description below; "
        "most customer requests are one of them.\n"
        "2. Route as soon as the service is clear. Missing payload fields are collected "
        "later automatically — never ask_clarification just because a field is missing. "
        "Only when the message names a topic but no clear ask, so several services fit "
        "equally, call ask_clarification.\n"
        "3. Fees/charges/costs are never answer_kb_question, even when asked like general "
        "info (\"what do you know about / tell me about fees\"). Any message asking what something "
        "costs — even one describing an action (\"if I send/withdraw..., what's the charge?\") "
        "— is fees/fee_quote, not the action itself. If no transaction type is named at all, "
        "ask_clarification. A complaint about a charge already taken is a dispute, not a "
        "fee quote.\n"
        "4. Transfers: route to transfer only when the destination TYPE is known (own account, "
        "another Polygon Bank account, another bank, or a named wallet provider) — choose the "
        "matching subservice. No destination type -> ask_clarification. Sending money to a "
        "person by NAME -> polygon_services/beneficiary (name in nameQuery), never transfer. "
        "Asking to add/save a new beneficiary (even if a name and account number are given) "
        "-> beneficiary_management/beneficiary_add. Nothing is executed in chat; details are only "
        "gathered.\n"
        "5. Freeze/block only when the customer says the card is lost, stolen, compromised "
        "or should be blocked; a card problem that doesn't say what is wrong -> "
        "ask_clarification. UNfreezing/UNblocking a card (making it usable again) is NOT available in chat: "
        "never route it — call ask_clarification, in your own words saying so and asking "
        "what else they need.\n"
        "6. Pass subservice ONLY for a service that lists subservices; otherwise omit it. "
        "Copy category and service exactly as they appear together on ONE line below; never "
        "use a subservice id as the service. Viewing existing disputes -> "
        "service_requests/disputes; viewing existing complaints/tickets -> "
        "polygon_services/my_tickets; wanting to raise/file/open a dispute (even with no "
        "details yet) or describing a problem with a transaction (charged twice, money "
        "deducted but not received) -> service_requests/raise_dispute.\n"
        "8. A one- or two-word message naming something the customer has (\"balance\", "
        "\"cards\", \"loans\", \"profile\", \"limit\") -> that lookup service. What the bank "
        "offers (card types/products) is card_info/card_products, not answer_kb_question.\n"
        "7. payload: only fields listed for that service, only values the customer actually "
        "stated (amount as a number, account/wallet numbers as strings). Never invent or "
        "reuse values from this prompt. Omit unknown fields. Never put a PIN, password, OTP "
        "or CVV in payload.\n\n"
        f"{_render_taxonomy(taxonomy, allowed, include_other)}\n\n"
        "Decision patterns (<...> = whatever the customer actually said):\n"
        "- \"show my login activity\" -> route_banking_service(category=\"account_info\", "
        "service=\"login_history\") (any simple lookup: pick the supported service whose "
        "description matches)\n"
        "- \"send <amount> to my <wallet provider> <number>\" -> route_banking_service("
        "category=\"transfer\", service=\"wallet_transfer\", subservice=<provider id>, "
        "payload={\"walletNumber\": \"<number>\", \"amount\": <amount>})\n"
        "- \"send money to <person name>\" -> route_banking_service(category="
        "\"polygon_services\", service=\"beneficiary\", payload={\"nameQuery\": \"<person "
        "name>\"})\n"
        "- \"if I <action> <amount> via <method>, what is the fee?\" -> route_banking_service("
        "category=\"fees\", service=\"fee_quote\", payload={\"transactionType\": \"<method>\", "
        "\"amount\": <amount>})\n"
        "- \"I want to transfer money\" (no destination type) -> ask_clarification "
        "(in your own words, ask where they want to send it)\n"
        "- \"<topic> help\", \"<topic> info\", \"fees?\" — a topic with no clear ask -> "
        "ask_clarification (in your own words, ask what exactly they need; for fees, which "
        "transaction type and amount)\n"
        "- \"I lost my card, block it\" -> route_banking_service(category=\"card_services\", "
        "service=\"frezz_unfrezz\"); \"unblock my card\" -> ask_clarification (in your own "
        "words, say unblocking isn't available in chat)\n"
        "- \"what is a <banking product>?\", weather, maths, chit-chat -> answer_kb_question()"
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
    prompt = (
        "You route a bank customer's chat message to ONE domain. Customers write English, "
        "Bangla or Banglish (romanized Bangla), often one or two words, misspelled or "
        "informal. Read a misspelled word by how it sounds and Banglish as its English "
        "meaning (e.g. 'pathabo' = I will send, 'koto' = how much, 'ase' = is there, "
        "'dekhao' = show), then pick the domain by meaning. A banking word on its own, even "
        "misspelled, belongs to its banking domain, not general.\n"
        f"Domains:\n{domains}\n{context}\n"
        f'Customer message: "{message}"\n\n'
        'Respond only with JSON: {"domain": "<one domain key>"}'
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_CLASSIFY_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "think": settings.OLLAMA_THINK,
                    "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": 0},
                },
            )
            resp.raise_for_status()
            domain = json.loads(resp.json().get("response") or "{}").get("domain")
    except Exception:
        return None
    return domain if domain in DOMAINS else None


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
    if recent_turns:
        last = recent_turns[-1].classification or {}
        if last.get("category") and last.get("service"):
            allowed.add((last["category"], last["service"]))
    return frozenset(allowed), False


async def classify(
    message: str, recent_turns: list[ChatTurn] | None = None
) -> ClassificationResult:
    allowed, include_other = await _domain_scope(message, recent_turns)
    messages = [{
        "role": "system",
        "content": build_system_prompt(get_taxonomy(), allowed, include_other),
    }]
    if recent_turns:
        last_turn = recent_turns[-1]
        last_classification = last_turn.classification or {}
        pending_question = last_classification.get("question") or "a clarifying question"
        if last_classification.get("type") == "ACCOUNT_SELECTION_REQUIRED":
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
                'question above (by its type, e.g. "savings"/"credit", or by the last few '
                'digits of its number, e.g. "0015"). In that case, call route_banking_service '
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
                '\n- "how many accounts do i have?" -> does not name any of the specific '
                "listed accounts at all — it's a different, already-identified request type "
                "(asking how many accounts exist) — classify it independently per the general "
                'rules above (e.g. route_banking_service(category="account_info", '
                'service="accounts")). Never reinterpret this as a transfer just because it '
                'says "accounts".\n'
                '- "savings" or "the savings account please" -> clearly names one of the '
                f"listed accounts by type — route_banking_service({service_args}, "
                'payload={"accountType": "savings"}).\n'
                '- "the one ending 0015" -> clearly names one of the listed accounts by its '
                f"number — route_banking_service({service_args}).\n"
                '- "what is the weather today" or "I want to transfer money to another bank" '
                "-> a genuine subject change unrelated to picking an account — classify "
                "independently per the general rules above (e.g. a KB/decline, or the "
                "Transfer-specific rule's own path respectively), never treated as an "
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
                "asked for (a transaction type, method, amount, account type, etc.) — even when "
                "it's phrased as a full sentence describing an action/intent rather than a bare "
                'word (e.g. "I want to transfer money to bkash" IS naming a transaction type, not '
                "a subject change). Only treat the new message as a genuinely new, unrelated "
                "request when it changes the subject to a different KIND of thing entirely (e.g. "
                "the pending question was about fees, but the new message instead asks about "
                "balance, account info, or login history)."
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
            if "fee quote" in pending_question.lower():
                worked_example = (
                    "\n- If the new message names a transaction type/method (e.g. bKash, Nagad, "
                    "another bank, ATM, cash) — with or without an amount, and however it's "
                    'phrased (a bare word or a full sentence like "I want to transfer money from '
                    'bank to bkash") — call route_banking_service(category="fees", '
                    'service="fee_quote", payload={"transactionType": "<method named>", ...amount '
                    "if present}). This is the only acceptable route_banking_service call for this "
                    "reply — never beneficiary, never a transfer/wallet action, never any other "
                    "category/service, even though the message is phrased like an action "
                    "request.\n"
                    "- If the new message still gives no transaction type at all, call "
                    "ask_clarification repeating the same kind of question.\n"
                    "- Only classify independently per the general rules above if the new message "
                    "is a genuine subject change (different kind of thing entirely, not just a "
                    "different phrasing of the fee answer)."
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
            return Clarification(question=retry_arguments.get("question") or _CLARIFICATION_FALLBACK)
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

        # First attempt hallucinated a category/service/subservice id that doesn't exist
        # anywhere in the real taxonomy (confirmed live: genuine model nondeterminism, not
        # a fixable prompt/schema issue — see T-23). Retry once with a corrective message
        # before falling back to a generic clarification, so a wrong-but-plausible guess
        # doesn't become a confident "that's not available" to the customer.
        retry_messages = messages + [
            {"role": "assistant", "content": "", "tool_calls": [tool_calls[0]]},
            {
                "role": "user",
                "content": (
                    "That category/service/subservice doesn't exist. Re-check the list above "
                    "and either pick a real id, or call ask_clarification if you're not sure."
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
            return Clarification(question=retry_arguments.get("question") or _CLARIFICATION_FALLBACK)
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
