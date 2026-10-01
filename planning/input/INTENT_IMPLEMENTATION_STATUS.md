# Intent Implementation Status

Standing tracker: for each of the bank's 14 intents, which endpoints are
actually implemented in this codebase today vs not. Companion to
`INTENT_API_READONLY_MAP.md` (GET vs mutating, same 46-endpoint source) and
`API_SCREEN_MAP.md` (which real app screen calls each endpoint) — this file
is the "did we actually build it" layer. **Update this file alongside
TASKS.md whenever a task changes an intent's coverage** — don't let it go
stale.

Legend:
- ✅ **Done** — real adapter calls this live endpoint, wired end-to-end.
- ✅ **Done (gather+redirect)** — never calls the real (mutating) endpoint
  by design (ADR-0008: inform/redirect only) — the bot gathers details via
  clarification and returns a confirmation summary + navigation hint for
  the frontend instead.
- 🔶 **Approved, not yet built** — user has explicitly approved implementing
  this, work not started/landed yet.
- ❌ **Not done** — read-only (GET), available under current policy, simply
  not implemented yet.
- ⛔ **Blocked** — mutating (POST/PUT/PATCH/DELETE), blocked by the standing
  GET-only policy unless explicitly carved out as an exception (see below).
- 🚫 **No backend** — dead end per the bank's own doc, unusable regardless
  of policy.
- ➕ **Extra** — implemented, but not actually part of this intent's official
  endpoint list (built for a different real-world reason).

**Exceptions to the GET-only policy, explicitly approved by user:**
- Beneficiary **add** (14.20, POST) — approved 2026-10-01, not yet built.
- Card **freeze** (4.1 / 12.2, PATCH) — approved 2026-10-01 as a careful
  exception: list cards (GET) → ask which card if 2+ → ask reason → explicit
  re-confirmation naming the card back → only then call the real freeze
  endpoint. Queued as T-57, not yet built. **Unfreeze stays blocked** (not
  part of the exception).

## Summary

| Intent | Status | Read-only done | Notes |
|---|---|---|---|
| ACCOUNT_INFO | Partial | 2/7 | Missing: by-number lookup, by-username lookup, my loans, FD/DPS profit history |
| ATM_SUPPORT | Not started | 0/1 | Only GET is "list disputes"; core actions (cash-by-code, raise dispute) blocked |
| CARD_ISSUE | Not started | 0/2 | Only GETs are list disputes/complaints; core fixes (reset PIN, unfreeze, dispute, complaint) blocked |
| CARD_MANAGEMENT | Not started (freeze queued) | 0/6 | Freeze (T-57) is the first approved mutating exception here |
| CARD_REPLACEMENT | Not started | 0/2 | Reveal endpoint is GET but exposes real card numbers — sensitive |
| CHECK_BALANCE | Mostly done | 1/2 | Balance done (shared with ACCOUNT_INFO); credit card summary missing |
| EDIT_PERSONAL_DETAILS | Not started | 0/6 | Nothing built yet |
| FAILED_TRANSFER | Partial | 1/3 | Transaction history done (shared adapter); dispute/complaint lists missing |
| FALLBACK | Done | — | Own KB/RAG pipeline used instead of the bank's hand-off APIs (deliberate) |
| FEES | Done | 1/1 | Fully covered — only 1 endpoint in this intent |
| GREETING | Done | — | Conversational, no API needed |
| LOST_OR_STOLEN_CARD | Not started | 0/0 | 100% mutating intent; will partially benefit once T-57's freeze exception lands |
| MINI_STATEMENT | Partial | 1/4 | Transaction list done; account transactions, card statement, expense-tracker missing |
| TRANSFER | Partial + gather-only | 2/9 + 4 gather-only | Beneficiary list done; own/city/other-bank + wallet transfer covered conversationally (T-56, never executes); beneficiary add approved not built; rest not done |

## ACCOUNT_INFO — *Partial*
| # | Endpoint | Status |
|---|---|---|
| 1.1 Get all accounts | ✅ Done |
| 1.2 Get account detail | ✅ Done |
| 1.3 Get account by account/card number | ❌ Not done |
| 1.4 Get accounts by username | ❌ Not done |
| 1.5 Star account | ⛔ Blocked |
| 1.6 My loans | ❌ Not done |
| 1.7 FD profit history | ❌ Not done |
| 1.8 DPS profit history | ❌ Not done |

## ATM_SUPPORT — *Not started*
| # | Endpoint | Status |
|---|---|---|
| 2.1 Cash by code | ⛔ Blocked |
| 2.2 Raise dispute | ⛔ Blocked |
| 2.3 List disputes | ❌ Not done |

## CARD_ISSUE — *Not started*
| # | Endpoint | Status |
|---|---|---|
| 3.1 Reset card PIN | ⛔ Blocked |
| 3.2 Unfreeze card | ⛔ Blocked |
| 3.3 Raise dispute | ⛔ Blocked |
| 3.4 List disputes | ❌ Not done |
| 3.5 Submit complaint | ⛔ Blocked |
| 3.6 My complaints | ❌ Not done |

## CARD_MANAGEMENT — *Not started (freeze queued as T-57)*
| # | Endpoint | Status |
|---|---|---|
| 4.1 Freeze card | 🔶 Approved exception, queued (T-57) |
| 4.2 Unfreeze card | ⛔ Blocked |
| 4.3 Close card | ⛔ Blocked |
| 4.4 Contactless on/off | ⛔ Blocked |
| 4.5 International transaction on/off | ⛔ Blocked |
| 4.6 Reset card PIN | ⛔ Blocked |
| 4.7 Limit change — submit | ⛔ Blocked |
| 4.8 Limit change — list | ❌ Not done |
| 4.9 Limit change — cancel | ⛔ Blocked |
| 4.10 Card products list | ❌ Not done |
| 4.11 Apply for debit card | ⛔ Blocked |
| 4.12 Reveal debit card details | ❌ Not done (sensitive — real card number) |
| 4.13 Apply for prepaid card | ⛔ Blocked |
| 4.14 Reveal prepaid card details | ❌ Not done (sensitive) |
| 4.15 Virtual card — submit | ⛔ Blocked |
| 4.16 Virtual card — list | ❌ Not done |
| 4.17 Virtual card — cancel | ⛔ Blocked |
| 4.18 Virtual card — reveal | ❌ Not done (sensitive) |
| 4.19 Star card | ⛔ Blocked |
| 4.20 Credit card bill payment (card service) | ⛔ Blocked |
| 4.21 Credit card bill payment (bill service) | ⛔ Blocked |
| 4.22 QR payment cards — list | 🚫 No backend |
| 4.23 QR payment card — enable/disable | 🚫 No backend |

## CARD_REPLACEMENT — *Not started*
| # | Endpoint | Status |
|---|---|---|
| 5.1 List replacement requests | ❌ Not done |
| 5.2 Cancel replacement request | ⛔ Blocked |
| 5.3 Reveal replacement card details | ❌ Not done (sensitive) |

## CHECK_BALANCE — *Mostly done*
| # | Endpoint | Status |
|---|---|---|
| 6.1 Account balance | ✅ Done (`balance` adapter) |
| 6.2 Credit card summary | ❌ Not done |

## EDIT_PERSONAL_DETAILS — *Not started*
| # | Endpoint | Status |
|---|---|---|
| 7.1 Get profile | ❌ Not done |
| 7.2 Update nickname | ⛔ Blocked |
| 7.3/7.4 Upload profile image | ⛔ Blocked |
| 7.5 Update mobile number | ⛔ Blocked |
| 7.6 Update email address | ⛔ Blocked |
| 7.7 Get address | ❌ Not done |
| 7.8 Update address | ⛔ Blocked |
| 7.9 Submit KYC | ⛔ Blocked |
| 7.10 My contacts | ❌ Not done |
| 7.11 Profile change — submit | ⛔ Blocked |
| 7.12 Profile change — list | ❌ Not done |
| 7.13 Contact priority — submit | ⛔ Blocked |
| 7.14 Contact priority — list | ❌ Not done |

## FAILED_TRANSFER — *Partial*
| # | Endpoint | Status |
|---|---|---|
| 8.1 Transaction history | ✅ Done (shared `transaction_history` adapter) |
| 8.2 Raise dispute | ⛔ Blocked |
| 8.3 List disputes | ❌ Not done |
| 8.4 Submit complaint | ⛔ Blocked |
| 8.5 My complaints | ❌ Not done |

## FALLBACK — *Done (own implementation)*
All 7 endpoints in this section (Polygon AI chat/status, FAQ categories,
FAQs, submit complaint) are ➕ **unused by design** — we built our own
KB/RAG pipeline (`app/llm.py`, `KB_ANSWER` result type) instead of calling
the bank's own AI/FAQ hand-off APIs.

## FEES — *Done*
| # | Endpoint | Status |
|---|---|---|
| 10.1 Transaction charge quote | ✅ Done (`fee_quote` adapter) |

## GREETING — *Done*
No API needed — handled conversationally.

## LOST_OR_STOLEN_CARD — *Not started*
| # | Endpoint | Status |
|---|---|---|
| 12.1 Report lost/stolen card | ⛔ Blocked |
| 12.2 Freeze card immediately | ⛔ Blocked (same endpoint as 4.1 — will become available once T-57 lands, but "report lost/stolen" itself stays blocked) |

## MINI_STATEMENT — *Partial*
| # | Endpoint | Status |
|---|---|---|
| 13.1 Transaction list | ✅ Done (shared `transaction_history` adapter) |
| 13.2 Account transactions | ❌ Not done |
| 13.3 Credit card statement | ❌ Not done |
| 13.4 Expense tracker category transactions | ❌ Not done |

## TRANSFER — *Partial + gather-only conversational coverage*
| # | Endpoint | Status |
|---|---|---|
| 14.1 Own account transfer | ✅ Done (gather+redirect — T-56, never executes) |
| 14.2 City Bank transfer | ✅ Done (gather+redirect — T-56) |
| 14.3 Other bank transfer | ✅ Done (gather+redirect — T-56) |
| 14.4 Other banks list | 🚫 No backend |
| 14.5 Gift transfer | ⛔ Blocked (not covered by T-56) |
| 14.6 Gifts received | ❌ Not done |
| 14.7 Generic transaction | ⛔ Blocked |
| 14.8 Linked account check | ⛔ Blocked |
| 14.9 Email transfer — create | ⛔ Blocked |
| 14.10 Email transfer — list | ❌ Not done |
| 14.11 Email transfer — details | ❌ Not done |
| 14.12 Email transfer — cancel | ⛔ Blocked |
| 14.13 Email transfer — resend | ⛔ Blocked |
| 14.14 Wallet/MFS transfer | ✅ Done (gather+redirect — T-56, bkash/nagad/rocket/upay) |
| 14.15 Wallet verify | ❌ Not done |
| 14.16 QR pay | ⛔ Blocked |
| 14.17 QR parse | ⛔ Blocked |
| 14.18 QR payment history | ❌ Not done |
| 14.19 Beneficiary — list | ✅ Done |
| 14.20 Beneficiary — add | 🔶 Approved, not yet built |
| 14.21 Beneficiary — edit | ⛔ Blocked |
| 14.22 Beneficiary — delete | ⛔ Blocked |
| 14.23 Beneficiary — upload/change photo | ⛔ Blocked |
| 14.24 Beneficiary — remove photo | ⛔ Blocked |
| 14.25 Beneficiary — pin/unpin | ⛔ Blocked |
| 14.26 Recipient lookup by account number | ❌ Not done (same endpoint as 1.3) |
| 14.27 My transfer limit — get | ❌ Not done |
| 14.28 My transfer limit — request change | ⛔ Blocked |
| 14.29 My transfer limit — cancel pending change | ⛔ Blocked |
