# Polygon Bot — Project Progress Summary

Task-wise summary of the work done on the Polygon Bank chatbot (FastAPI + Ollama `llama3.1:8b` + Qdrant),
for management reporting. Work period: Aug 25 – Oct 6, 2026. Dates are the real dates the work was done.

## Phase 1 — First 15 days (Aug 25 – Sep 8): foundation

1. **Knowledge-base chatbot (Aug 25).** Document upload and a streaming chat API that answers general bank questions from uploaded documents (RAG on Qdrant).
2. **Banking-request understanding (Sep 1–3).** The model classifies each message as a general question, a banking request or a clarification; unknown services are handled safely.
3. **Live service catalog (Sep 1–3).** The bank's service list is fetched, merged and refreshed automatically, with a fallback when the bank is unreachable.
4. **Customer identity and sessions (Sep 1–3).** Login-token (JWT) verification, a clear "please log in" path, and 30-minute per-customer conversation memory.
5. **Bank connection layer (Sep 1–3).** A common adapter interface, mock adapters for services not yet connected, and handling of bank failures (unavailable or not logged in).
6. **First live bank services (Sep 1–3).** Balance, transactions, accounts, devices and login history, with a "which account?" follow-up when the customer has several.
7. **Logging and tests (Sep 1–3).** Per-request audit log and regression tests for the original chat and document features.
8. **Demo frontend (Sep 1–6).** Shows the response type and data; login form against the real bank login.
9. **Reply quality (Sep 6–7).** Real, data-based replies instead of fixed text; switched the model to `llama3.1:8b`; masked account/card numbers; taka formatting; date-range filtering.
10. **Fixes and handoff (Sep 6–8).** Stale-context mix-ups, a leaked account number, and the first frontend rendering guide.

## Phase 2 — Sep 9 – Sep 29: light period

11. **Logging, beneficiaries and fees (Sep 9–29).** Full operational logging of every chat request (Sep 9), a real beneficiary adapter with the bank team, name matching for "send money to <name>", a retry safety net for unclear classification, and the new FEES intent (transaction charge quotes).

## Phase 3 — Last 7 days (Sep 30 – Oct 6): the bulk of the work

**Sep 30 — hardening the fees and chat behaviour**

12. **Fees and chat-behaviour fixes.** Fixed 14 live bugs: crashes on malformed model output, fee questions with a missing amount or phrased as general info, replies leaking internal wording, missing result events on knowledge answers, and context leaking between unrelated messages.
13. **Off-topic and abusive messages.** The bot declines non-banking and abusive messages without engaging with them.

**Oct 1 — new intents and approved account changes**

14. **Transfers.** Transfer intent that gathers the details and hands off to the app; it never executes a transfer.
15. **Card freeze.** Card freeze with a one-time code and PIN or password, verified live.
16. **More read-only services.** Loans, FD and DPS profit history, dispute list.
17. **Beneficiary add and raise-a-dispute.** Beneficiary add (confirmation first) and raising a dispute as a hand-off to the app.

**Oct 3 — accuracy, security and coverage**

18. **Root-cause fix for misrouting.** Found that Ollama was silently truncating every prompt, which caused most classification errors; fixed it.
19. **Two-stage, description-based routing.** Replaced example lists with service descriptions and a domain-then-service design, tested against several models.
20. **All remaining read-only endpoints across the 14 intents.** Cards, card requests, replacement requests, credit card summary and statement, profile, address, contacts, change requests, transfer limit, gifts, email transfers, QR history and more.
21. **Correctness fixes found by live testing.** Amounts shown 100× too high, invented records from empty lists, wrong balance, and the unresolved "which account?" follow-up.
22. **Security.** Fixed injection of ids into bank paths; codes, PINs and passwords stay out of logs and the model.
23. **Live evaluations.** Multi-turn evaluation (24 → 31 of 35) and a 74-case sweep across all 14 intents (69 correct).
24. **Frontend handoffs.** Dart integration guides for all 14 intents plus a shared API contract.
25. **Speed.** First latency pass: streamed data answers so the first words appear in about 1–2 seconds.

**Oct 4–5 — customer-requested changes and natural replies**

26. **Account changes requested by the customer.** Complaint submission, nickname, address, email and mobile change (code to the registered phone), lost/stolen-card guidance that redirects to the app, and profile-photo redirect; live-tested.
27. **Bank repo changes and "look it up, don't ask".** Followed the bank's API changes; the bot now finds the account, card, transaction or recipient itself instead of asking the customer.
28. **Model-written replies.** One shared assistant voice for every message, with automatic checks on each reply (exact amounts, no invented numbers, one currency, no markdown); no fixed templates or keyword rules; natural amounts such as "1.5 lakh" and "50k".

**Oct 6 — test suite and safety**

29. **Dynamic QA suite.** Every row of the status tracker asked five ways (one word, two words, casual, sentence, paragraph), 94 rows and 470 questions, plus simulated multi-turn customers. First full live run: 300 questions across the intents up to FEES, with every failure recorded.
30. **Safety fixes from that run.** A card-freeze code was being sent for requests that were not a freeze; the bot now asks yes/no first. Codes typed into a chat step are no longer stored or logged. Fixed a crash on follow-up questions.
31. **Management documentation.** This summary, plus a planned task (T-79) to show information in the UI or redirect customers to the right page for everything chat does not carry out.

## In progress (as of Oct 6)

- Fixing the failed cases from the first full live run (conversation quality on vague messages, old context leaking into new messages, requests chat doesn't offer being routed to a lookup), then re-running them.
- Multi-turn testing across all 14 intents, where a customer can ask anything at any point.
- Not available in chat by design or blocked on the bank side: card-detail reveal, QR payment cards, and FD records for the test customer.
