"""Intent classification for /chat messages (ADR-0004, FR-ROUTE-01..05).

A single Ollama /api/chat tool-calling request decides whether a message is a
KB question, a banking-service request, or ambiguous. Per the T-11 spike, this
only works reliably with an explicit, numbered, rule-based system prompt that
embeds the live taxonomy — a minimal prompt or a tool-schema-only approach
without real taxonomy values reliably guesses a banking-service route instead
of asking for clarification.
"""

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
        "answer_kb_question.\n"
        "2. If the message clearly names a specific action the customer wants performed or "
        "checked on their own account, call route_banking_service with the category/service/"
        "subservice ids from the list below that best match. Only use ids that appear in this "
        "list — never invent one.\n"
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
        'service="login_history")'
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
                "model": settings.OLLAMA_MODEL,
                "messages": messages,
                "tools": build_tools(),
                "stream": False,
                "think": True,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("message", {}).get("tool_calls") or []


async def classify(
    message: str, recent_turns: list[ChatTurn] | None = None
) -> ClassificationResult:
    messages = [{"role": "system", "content": build_system_prompt(get_taxonomy())}]
    for turn in recent_turns or []:
        messages.append({"role": "user", "content": turn.message})
    messages.append({"role": "user", "content": message})

    tool_calls = await _post_classification(messages)
    if not tool_calls:
        return KbQuestion()

    call = tool_calls[0]["function"]
    name = call["name"]
    arguments = call.get("arguments", {})

    if name == "answer_kb_question":
        return KbQuestion()
    if name == "ask_clarification":
        return Clarification(question=arguments["question"])
    if name == "route_banking_service":
        category = arguments["category"]
        service = arguments["service"]
        subservice = arguments.get("subservice") or None
        if is_valid_path(category, service, subservice):
            return BankingService(category=category, service=service, subservice=subservice)

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
            return Clarification(question=retry_arguments["question"])
        if retry_name == "route_banking_service":
            retry_category = retry_arguments["category"]
            retry_service = retry_arguments["service"]
            retry_subservice = retry_arguments.get("subservice") or None
            if is_valid_path(retry_category, retry_service, retry_subservice):
                return BankingService(
                    category=retry_category,
                    service=retry_service,
                    subservice=retry_subservice,
                )
            return Clarification(question=_CLARIFICATION_FALLBACK)

        return Clarification(question=_CLARIFICATION_FALLBACK)

    return KbQuestion()
