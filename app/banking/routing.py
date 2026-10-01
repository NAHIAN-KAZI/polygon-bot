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
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _render_taxonomy(taxonomy: dict) -> str:
    lines = []
    for category in taxonomy.get("categories", []):
        lines.append(f"- {category['id']} ({category['name']})")
        for service in category.get("services", []):
            lines.append(f"  - {service['id']} ({service['name']})")
            for sub in service.get("subServices", []):
                lines.append(f"    - {sub['id']} ({sub['name']})")
    return "\n".join(lines)


def build_system_prompt(taxonomy: dict) -> str:
    return (
        "You are a banking assistant classifying customer messages. You MUST call exactly one "
        "tool.\n\n"
        "Decision rules, in order:\n"
        "1. If the message asks for general information, explanation, or \"how does X work\" — "
        "NOT a request to perform an action on the customer's own account — call "
        "answer_kb_question. Exception: any message that is clearly asking about transaction "
        "fees/charges/costs — however it's phrased, including informational-sounding wording "
        "like \"what do you know about...\", \"tell me about...\", or \"can you explain...\" — "
        "is NEVER a KB topic. Fees are a live, quotable real-time service, not static "
        "background info, so always resolve fee questions via route_banking_service("
        "category=\"fees\", service=\"fee_quote\", ...) when the transaction type and amount "
        "are both known, or ask_clarification otherwise — never answer_kb_question.\n"
        "2. If the message clearly names a specific action the customer wants performed or "
        "checked on their own account, call route_banking_service with the category/service/"
        "subservice ids from the list below that best match. Only use ids that appear in this "
        "list — never invent one. Exception: if the message BOTH describes performing an "
        "action (transfer/send/withdraw/pay/replace/etc.) AND asks about its cost/fee/charge "
        "(e.g. \"what is the fee\", \"how much would it cost\", \"what will I be charged\"), "
        "classify by the cost question, not the action verb — route to category=\"fees\", "
        "service=\"fee_quote\" instead. The action mention is context for the fee lookup (it "
        "supplies transactionType/amount for the payload), not a request to execute the "
        "action itself.\n"
        "3. If the message is vague or does not name a specific action or service, call "
        "ask_clarification with a specific question asking what the customer wants to do. Do "
        "NOT guess a service or subservice in this case.\n\n"
        "Never call route_banking_service unless the message explicitly names an action or "
        "service that matches something in this list. When in doubt, prefer ask_clarification "
        "over guessing.\n\n"
        "Available categories, services, and subservices:\n"
        f"{_render_taxonomy(taxonomy)}\n\n"
        "Examples:\n"
        '- "what\'s my balance?" -> route_banking_service(category="account_info", '
        'service="balance")\n'
        '- "how many accounts do I have?" -> route_banking_service(category="account_info", '
        'service="accounts")\n'
        '- "what devices are logged in?" -> route_banking_service(category="account_info", '
        'service="device_history")\n'
        '- "show my login history" -> route_banking_service(category="account_info", '
        'service="login_history")\n'
        '- "I need help with my card" -> ask_clarification(question="Sure — what do you need '
        'help with on your card? For example, freezing/unfreezing it, resetting the PIN, or '
        'something else?")\n'
        '  (this is vague — "my card" could mean many different things, so ASK rather than '
        'guessing which card service they mean)\n'
        '- "I want to transfer money" -> ask_clarification(question="Sure — how would you like '
        'to transfer money? For example, to your own account, another bank, or a mobile wallet '
        'like bKash?")\n'
        '  (same reasoning — many transfer types exist, do not guess which one)\n'
        '- "send money to Ashan" -> route_banking_service(category="polygon_services", '
        'service="beneficiary", payload={"nameQuery": "Ashan"})\n'
        '  (the message names a specific person to send money to — that IS a specific, '
        'actionable request, even though no account number or bank was given. Look up that '
        'name as a saved beneficiary rather than asking which transfer type to use; put the '
        'name verbatim as it appeared in the message into payload.nameQuery)\n'
        '- "transfer 500 taka to Dipu" -> route_banking_service(category="polygon_services", '
        'service="beneficiary", payload={"nameQuery": "Dipu", "amount": 500})\n'
        '  (same pattern as above, plus the message also mentions an amount — include both '
        'nameQuery and amount together in the same payload)\n'
        '- "what\'s the fee for a bank transfer" -> route_banking_service(category="fees", '
        'service="fee_quote", payload={"transactionType": "other_bank"})\n'
        '- "how much does it cost to send money via bKash" -> route_banking_service('
        'category="fees", service="fee_quote", payload={"transactionType": "bkash"})\n'
        '  (put whatever transaction type the customer said verbatim into '
        'payload.transactionType — do not normalize or guess a different id for it — and '
        'include payload.amount too if an amount in taka was mentioned)\n'
        '- "how much fees for sending to other bank accounts?" -> ask_clarification(question='
        '"Sure — how much would you like to send to another bank account? I can give you the '
        'exact fee once I know the amount.")\n'
        '- "how much does it cost via qr transfer?" -> ask_clarification(question="Sure — how '
        'much would you like to send via QR transfer? I can give you the exact fee once I know '
        'the amount.")\n'
        '  (the transaction type IS named in both of these, but no amount was given — name the '
        'transaction type back to the customer and ask specifically for the amount, rather than '
        'asking a generic "which transaction type" question)\n'
        '- "what are your fees" -> ask_clarification(question="Sure — which transaction type '
        'would you like a fee quote for, and for what amount? For example, a bank transfer, '
        'bKash, or another wallet?")\n'
        '  (no transaction type or amount was named — this is vague like the card-help example '
        'above, so ASK rather than guessing which fee they mean)\n'
        '- "what do you know about fees?" -> ask_clarification(question="Sure — which '
        'transaction type would you like a fee quote for, and for what amount? For example, a '
        'bank transfer, bKash, or another wallet?")\n'
        '  (phrased informationally, like a KB question, but fees are always live-quotable via '
        'route_banking_service/ask_clarification, never a KB topic — same handling and same '
        'question as the "what are your fees" example above, never answer_kb_question)\n'
        '- "If i transfer 1000 from my account to bkash what is the fee?" -> '
        'route_banking_service(category="fees", service="fee_quote", payload='
        '{"transactionType": "bkash", "amount": 1000})\n'
        '  (this names an action verb — "transfer" — but the actual ask is the cost of doing '
        'it, not a request to execute the transfer. Classify by the cost question: route to '
        'fees/fee_quote and extract the transaction type and amount into payload, exactly as '
        'in the fee examples above)\n'
        '- "if I send 5000 taka to another bank account, how much would it cost?" -> '
        'route_banking_service(category="fees", service="fee_quote", payload='
        '{"transactionType": "other_bank", "amount": 5000})\n'
        '  (same pattern — "send" is an action verb, but "how much would it cost" is the real '
        'question, so this is a fee lookup, not a transfer request)\n'
        '- "what will I be charged if I withdraw 2000 from an ATM?" -> route_banking_service('
        'category="fees", service="fee_quote", payload={"transactionType": "atm_withdrawal", '
        '"amount": 2000})\n'
        '  (same pattern with a different action verb — "withdraw" — and cost phrasing "what '
        'will I be charged"; still a fee_quote, not an ATM withdrawal request)\n'
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
                    "Route the message to a specific banking service the customer explicitly "
                    "asked for, using ids from the provided taxonomy list."
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
                                "Extra structured details extracted from the message that the "
                                "service needs, if any. For example {\"nameQuery\": \"Ashan\"} "
                                "when the message names a person to send money to, optionally "
                                "combined with {\"amount\": 500} if an amount was also "
                                "mentioned. Omit entirely if nothing extra applies."
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
                    "Ask the customer a clarifying question when the message is vague or does "
                    "not name a specific action or service. Never guess in this case."
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
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("message", {}).get("tool_calls") or []


async def classify(
    message: str, recent_turns: list[ChatTurn] | None = None
) -> ClassificationResult:
    messages = [{"role": "system", "content": build_system_prompt(get_taxonomy())}]
    if recent_turns:
        last_turn = recent_turns[-1]
        pending_question = (last_turn.classification or {}).get("question") or "a clarifying question"
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
