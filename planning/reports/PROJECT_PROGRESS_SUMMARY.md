# Polygon Bot — Project Progress Summary

High-level summary of the work done on the Polygon Bank chatbot (FastAPI + Ollama `llama3.1:8b` + Qdrant),
for management reporting. Work done between Aug 25 and Oct 6, 2026.

## Delivered

1. **Knowledge-base chatbot.** Document upload and a streaming chat API that answers general bank questions from uploaded documents (RAG on Qdrant), with a demo web frontend.
2. **Service catalog and request routing.** The bot reads the bank's live service catalog (fetched and refreshed automatically) and routes each message to a general question, a banking request or a clarification; services outside the catalog are handled safely.
3. **14-intent classification and tuning.** Built the classifier for all 14 bank intents (balance, accounts, cards, transfers, fees, disputes, profile and more) and tuned it over many rounds: compared models (qwen3, qwen2.5, mistral-nemo, llama3.1:8b chosen) and a Hugging Face classifier (63–68%, rejected), fixed the root cause of early misroutes (Ollama silently truncating prompts), moved to a two-stage domain-then-service design, and rewrote prompts as plain descriptions instead of keyword lists. Measured by a 107-case classification eval (96–98 correct at its best) and a 74-case live sweep across all 14 intents (69 correct). Tuning here means prompts, routing and model choice; no model weights were trained.
4. **Customer identity and sessions.** Login-token (JWT) verification, a clear "please log in" path, and per-customer conversation memory with a 30-minute expiry.
5. **Live bank integration (read-only).** Real connections for balances, accounts, transactions, loans, FD/DPS profit, cards and card requests, disputes, complaints, profile, contacts, transfer limits and more, always using the customer's own token.
6. **Fees and transfers.** Fee quotes with the bot asking only for what is missing; transfers (own account, other bank, wallets, saved beneficiaries) gather the details and hand off to the app screen. The bot never executes a transfer.
7. **Approved account changes.** Card freeze and mobile/email change (with one-time code), beneficiary add, nickname, address, complaint submission, and lost/stolen-card guidance that redirects to the app. Every change needs an explicit confirmation first.
8. **Accuracy and security fixes.** Correct taka amounts, masked account/card numbers, no invented records, protection against injected ids, codes/PINs/passwords never stored, logged or sent to the model, and handling of abusive input. Root cause of most early classification errors (prompt truncation in Ollama) found and fixed.
9. **Natural, model-written replies.** Moved from fixed templates and keyword rules to one shared assistant voice with automatic checks on every reply (exact amounts, no invented numbers). Prompts are description-based with no keyword lists.
10. **Speed.** Streamed data answers (first words in about 1–2 seconds), two-stage routing, and reply length capped at 400 tokens.
11. **Frontend handoff.** Integration guides in Dart for all 14 intents plus a shared API contract (response types, result payloads, confirmation and verification flows).
12. **Testing.** About 1,240 automated tests, live classification and cross-intent evaluations, fee QA, live account-change tests, and a new dynamic suite that asks every row of the status tracker five different ways (94 rows, 470 questions) plus simulated multi-turn customers.
13. **Operations.** Structured audit and operational logging per request, health checks, Docker deployment, and coordination with the bank's API team (outages, API changes, blocked endpoints).

## In progress (as of 2026-10-06)

- Full live run of the dynamic test suite across all intents; findings so far are being fixed (conversation quality on vague messages, stale-context leakage, a safer yes/no step before any card-freeze code is sent).
- Multi-turn testing across all 14 intents, where a customer can ask anything at any point.
- Items not available in chat by design or blocked on the bank side are tracked in the status tracker (for example card-detail reveal, QR payment cards, FD records for the test customer).
