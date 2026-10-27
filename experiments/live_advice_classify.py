"""Live probe: does the classifier send personal-advice questions to give_personal_advice, and leave everything
else where it was? Runs against the deployed model (read the container's env first).

    docker compose run --rm --no-deps -T -v "$PWD:/app" backend python -m experiments.live_advice_classify
"""
import asyncio
import sys

from app.banking import taxonomy
from app.banking.routing import AdviceQuestion, BankingService, Clarification, KbQuestion, classify

ADVICE = [
    "where does my money go every month?", "am I overspending?", "how can I spend less?",
    "which credit card is best for me?", "what deposit should I open with my savings?",
    "I want to save more, what do you suggest?", "which loan would suit me?", "what is the best account for someone like me",
    "amar taka kothay jay?", "ami kon card nile bhalo hobe?", "আমার কোন ডিপোজিট নেওয়া উচিত?", "how do I cut my expenses",
]
OTHER = {
    "what is the annual fee of the Visa Platinum card?": KbQuestion, "who is eligible for a personal loan?": KbQuestion,
    "which credit cards do you offer?": (KbQuestion, BankingService), "what are your savings accounts?": KbQuestion,
    "how can I contact customer care?": KbQuestion, "how much did I spend last month?": BankingService,
    "show my balance": BankingService, "my last 5 transactions": BankingService,
    "send 500 taka to my wife": (BankingService, Clarification),   # no destination: it asks where "freeze my card": BankingService, "hi": (Clarification, KbQuestion),
    "what is a fixed deposit?": KbQuestion, "can I get a car loan?": (KbQuestion, AdviceQuestion),   # either reading is fair
}


async def main() -> int:
    await taxonomy.initialize_taxonomy()   # the server does this at startup; routing needs the service list
    wrong = 0
    for message in ADVICE:
        result = await classify(message)
        ok = isinstance(result, AdviceQuestion)
        wrong += not ok
        print(("ok   " if ok else "MISS ") + f"advice  | {message} -> {type(result).__name__}")
    for message, expected in OTHER.items():
        result = await classify(message)
        ok = isinstance(result, expected if isinstance(expected, tuple) else (expected,))
        wrong += not ok
        detail = f" {result.category}/{result.service}" if isinstance(result, BankingService) else ""
        print(("ok   " if ok else "MISS ") + f"other   | {message} -> {type(result).__name__}{detail}")
    print(f"\n{len(ADVICE) + len(OTHER) - wrong} of {len(ADVICE) + len(OTHER)} as expected")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
