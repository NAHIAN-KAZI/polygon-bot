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
        f"{_render_taxonomy(taxonomy)}"
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


async def classify(
    message: str, recent_turns: list[ChatTurn] | None = None
) -> ClassificationResult:
    messages = [{"role": "system", "content": build_system_prompt(get_taxonomy())}]
    for turn in recent_turns or []:
        messages.append({"role": "user", "content": turn.message})
    messages.append({"role": "user", "content": message})

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

    tool_calls = data.get("message", {}).get("tool_calls") or []
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
        return UnknownService(category=category, service=service, subservice=subservice)

    return KbQuestion()
