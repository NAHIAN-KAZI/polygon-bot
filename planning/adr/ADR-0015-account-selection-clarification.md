# ADR-0015: Account-selection clarification for balance/transaction_history

## Status
Accepted

## Context
Live testing (2026-09-03, after T-20's JWT introspection made real banking-service
fulfillment possible for the first time) found a real bug: a customer asking "what's
my balance?" naturally — no account number, since customers don't think in account
numbers — got back `SERVICE_UNAVAILABLE` ("That service isn't available right now").
That's false; the service works fine. Root cause: `BalanceAdapter`/
`TransactionHistoryAdapter` (`app/banking/adapters/real.py`) hard-required
`payload.accountNumber`, and raised `AdapterUnavailableError` when it was missing,
which `chat.py` mistranslates into "unavailable" instead of "we need more info."

`AccountsAdapter`'s existing `GET /polygon-bank/v1/accounts` is the source of truth
for which accounts a customer has (`data.accounts`, not the internal `data.ledgerAccounts`).

## Decision
1. **Auto-resolve when the customer has exactly 1 account** — no clarification, fully
   transparent (matches this project's existing "never ask when you don't need to"
   philosophy, FR-ROUTE-03/T-11).
2. **When 2+ accounts, return a new SSE `result.type`: `ACCOUNT_SELECTION_REQUIRED`**
   — not the existing `CLARIFICATION_REQUIRED`, which `INTEGRATION.md` documents as
   always having `category/service/subservice/payload/routing` all `null`; reusing it
   with populated fields would break that documented invariant. `category`/`service`/
   `subservice` populated (same as the request), `routing` stays `null` (consistent
   with every non-`BANKING_SERVICE` type), `payload` =
   `{"accounts": [{"accountNumber","accountName","accountType","balance"}, ...]}` —
   trimmed, no `cards`/`branchName`/etc leaking through.
3. **Resolution via the existing direct-route mechanism, no new mechanism**: the
   client picks an account from `payload.accounts` and resubmits with the same
   `category`+`service` (+`subservice`) plus `payload.accountNumber` set — this
   already works today (FR-ROUTE-04's classification-skip path).
4. **0-accounts edge case**: treated as `AdapterUnavailableError` (existing
   `SERVICE_UNAVAILABLE`) — an authenticated customer with zero accounts on record is
   anomalous, not a "pick one" case.
5. **Data exposure**: the spoken `token` reply text masks the account number to
   last-4 digits; the structured `payload.accounts` carries the full account number
   (the client needs the real value to resubmit).

New exception `AdapterAccountSelectionRequiredError` (`app/banking/adapters/base.py`)
is a sibling of `AdapterUnavailableError`/`AdapterAuthError`, not a subclass — an
existing `except AdapterUnavailableError` never accidentally swallows it.

## Scope boundary (v1)
No free-text natural-language account resolution (e.g. a customer typing "the savings
one" as a follow-up). A client must resubmit structurally with `payload.accountNumber`.
This is a deliberate, documented limitation (see `INTEGRATION.md`/`HANDOFF.md`), not an
oversight — deferred to a future task if natural multi-turn resolution is ever needed.

## Consequences
Fixes the common (1-account) case transparently and correctly. For multi-account
customers, moves the "which account" decision to the client/UI layer instead of
guessing or asking a free-text question the LLM would have to parse — safer for a
banking product than silently picking one. Adds one extra upstream API call
(`GET /polygon-bank/v1/accounts`) to `balance`/`transaction_history` whenever
`payload.accountNumber` isn't already supplied — a client that already knows the
account (e.g. a resubmit) skips this entirely. `ACCOUNT_SELECTION_REQUIRED` is bucketed
as `outcome: "failure"` in the audit log's 3-value enum (same as `CLARIFICATION_REQUIRED`)
— not a perfect semantic fit, but avoids inventing a 4th `Outcome` value for one case.

## Alternatives considered
- **Reuse `CLARIFICATION_REQUIRED`** with a text-only question and no structured
  payload — rejected: forces the client to build a free-text "which account" parser,
  and violates that type's documented all-`null` invariant.
- **Silently pick the first/default account** even with 2+ — rejected: wrong-account
  risk on a banking product is unacceptable.
- **Resolve free-text follow-ups** ("the savings one") via a second classification
  pass — explicitly deferred, not this task (see Scope boundary).

## Related
FR-ROUTE-03, FR-ROUTE-04, ADR-0007 (result SSE event), ADR-0010 (mock adapter
interface / `AdapterUnavailableError` pattern), ADR-0012 (real adapters), ADR-0014
(JWT passthrough)
