"""Does the advisor give GOOD advice? Scenario checks with the real model and the real product cards (T-132).

Each scenario is a made-up customer (accounts, months of income and spending, holdings) and what good advice must,
and must not, contain. The customer's figures are computed by the real code path; only the bank is faked. Run
inside the bot container, where the product cards and the model are:

    docker compose run --rm --no-deps -T -v "$PWD:/app" backend python -m experiments.advisor_scenarios

Exit code 1 when a scenario fails. A failure is information, not necessarily a bug: gemma is not deterministic, so
read the printed picks before changing anything.
"""
import asyncio
import sys
from datetime import date

from app.advisor import advise, snapshot
from app.knowledge import product_cards

TODAY = date(2026, 10, 27)


def month(m, income, expense, cats):
    return {"month": m, "totalIncome": income * 100, "totalExpense": expense * 100,
            "expenseByCategory": [{"categoryName": n, "amount": a * 100} for n, a in cats.items()]}


def customer(balance, months, holds=None, loans=()):
    s = snapshot.Snapshot(as_of=TODAY)
    s.accounts = [{"accountNumber": "1234567890", "accountType": "SAVINGS", "cards": holds.get("debit", []) if holds else []}]
    s.ledgers = [{"identifier": "1234567890", "balance": balance * 100}]
    s.history = months
    s.credit_cards = holds.get("credit", []) if holds else []
    s.loans = [{"loanType": t, "emiAmountPoisha": 500_000, "outstandingPrincipalPoisha": 9_000_000,
                "annualInterestRatePercent": 14, "status": "ACTIVE"} for t in loans]
    if holds and holds.get("fd"):
        s.fixed_deposits = [{"id": 1}]
    if holds and holds.get("dps"):
        s.dps = [{"id": 1}]
    return s


STEADY = [month(m, 120_000, 70_000, {"Rent": 30_000, "Food": 20_000, "Transport": 8_000, "Shopping": 7_000, "Fun": 5_000})
          for m in ("2026-06", "2026-07", "2026-08", "2026-09")]
OVERSPENDER = [month(m, 60_000, 58_000, {"Rent": 20_000, "Food": 15_000, "Shopping": 14_000, "Fun": 9_000})
               for m in ("2026-06", "2026-07", "2026-08")] + \
              [month("2026-09", 60_000, 78_000, {"Rent": 20_000, "Food": 15_000, "Shopping": 14_000, "Fun": 29_000})]
NEWCOMER = [month("2026-09", 25_000, 20_000, {"Food": 12_000, "Transport": 8_000})]

SCENARIOS = [
    # name, snapshot, need, checks: list of (description, predicate(advice))
    ("rich saver asks which deposit", customer(900_000, STEADY),
     advise.Need(False, True, "which deposit to open", "grow savings", ()), "deposit",
     [("suggests something", lambda a, picks: len(picks) >= 1),
      ("all are deposit-like", lambda a, picks: all(any(w in p.card.kind for w in ("deposit", "dps", "savings", "account")) for p in picks)),
      ("never suggests a loan", lambda a, picks: not any("loan" in p.card.kind for p in picks))]),
    ("low balance, big-minimum deposit is flagged", customer(5_000, STEADY),
     advise.Need(False, True, "a fixed deposit", "", ()), "fixed deposit",
     [("the requirement check says the balance is not enough for any pick that needs more",
       lambda a, picks: all(any("not enough" in n for n in s["requirements against their figures"])
                            for s, p in zip(a.facts.get("suggested products", []), picks)
                            if p.card.min_opening_amount and p.card.min_opening_amount * 100 > 5_000 * 100))]),
    ("already holds a credit card: a card question does not push another credit card",
     customer(300_000, STEADY, holds={"credit": [{"id": 1}], "debit": [{"cardType": "DEBIT"}]}),
     advise.Need(False, True, "which card is best", "", ()), "card",
     [("a credit card pick says it is an extra or an upgrade, never 'new'",
       lambda a, picks: all(p.relation in ("extra", "upgrade") for p in picks if "credit" in p.card.kind))]),
    ("income too low for a loan that states a minimum income", customer(20_000, NEWCOMER),
     advise.Need(False, True, "a loan", "", ()), "loan",
     [("every loan pick that states a minimum income above theirs says so",
       lambda a, picks: all(any("below" in n for n in s["requirements against their figures"])
                            for s, p in zip(a.facts.get("suggested products", []), picks)
                            if p.card.min_monthly_income and p.card.min_monthly_income > 25_000))]),
    ("overspender: the category that jumped is named", customer(80_000, OVERSPENDER),
     advise.Need(True, False, "overspending", "", ()), "",
     [("Fun is in what grew", lambda a, picks: any(r["name"] == "Fun" for r in a.facts["grew compared with earlier months"])),
      ("a cut is suggested for a flexible category, not Rent",
       lambda a, picks: a.facts["ways to save"] and all(c["category"] != "Rent" for c in a.facts["ways to save"])),
      ("the total saving is computed from the customer's own numbers",
       lambda a, picks: "total possible saving per month" in a.facts)]),
    ("steady customer: no invented overspending", customer(300_000, STEADY),
     advise.Need(True, False, "where does my money go", "", ()), "",
     [("Rent or Food is among the biggest", lambda a, picks: any(r["name"] in ("Rent", "Food") for r in a.facts["where the money goes"]))]),
    ("a newcomer gets no trend claim", customer(30_000, NEWCOMER),
     advise.Need(True, False, "am I overspending", "", ()), "",
     [("no category change percentage is given", lambda a, picks: all(r["change percent"] is None for r in a.facts["where the money goes"]))]),
]


async def run() -> int:
    cards = product_cards.all_cards()
    if not cards:
        print("no product cards stored: build them first (POST /documents/{doc_id}/product-cards)")
        return 2
    failed = 0
    for name, snap, need, kind_word, checks in SCENARIOS:
        if need.product:
            kinds = tuple(k for k in advise.kinds_of(cards) if kind_word in k or (kind_word == "deposit" and any(w in k for w in ("deposit", "dps", "savings"))))
            need = advise.Need(need.spending, True, need.focus, need.goal, kinds)
        facts = snapshot.facts(snap)
        profile = advise.profile_for_model(facts)
        picks = await advise.pick_products(need, need.focus, profile, cards) if need.product else []
        advice = await advise.advise(need.focus, [], snap, need, cards)
        # advise() asks the model again; judge the facts it produced (picks come from the same call)
        picks = [next((c for c in cards if c.name == s["name"]), None) for s in advice.facts.get("suggested products", [])]
        relations = {s["name"]: s.get("compared with what they hold") for s in advice.facts.get("suggested products", [])}
        reverse = {"they hold nothing of this kind": "new", "they already hold one of this kind and this would be another": "extra",
                   "they hold one of this kind and this would be a better one": "upgrade"}
        picks = [advise.Pick(c, (), "", reverse.get(relations.get(c.name), "")) for c in picks if c]
        print(f"\n== {name}")
        print("   picks:", [p.card.name + f" ({p.card.kind})" for p in picks] or "none")
        for description, predicate in checks:
            try:
                ok = bool(predicate(advice, picks))
            except Exception as e:  # noqa: BLE001
                ok = False
                description += f" [check error: {type(e).__name__}]"
            failed += not ok
            print(("   ok   " if ok else "   FAIL ") + description)
    print(f"\n{failed} check(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
