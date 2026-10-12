# Use case status at a glance

Which use case works, which lacks API information, and which has no backend. Status as of 2026-10-12.

**How sure is this:** the status comes from the live single-turn runs of 2026-10-06 and 2026-10-07 (every use case asked five ways, English) and the transfer probe of 2026-10-07. Fixes made after those runs (complaint routing, transfer wording) were checked by unit tests only. Multi-turn flows across the 14 intents have not been run live, and not every use case has been re-run on the final build.

| Status | Meaning | Use cases |
|---|---|---|
| ✅ Working | Routed correctly in the live run | 41 |
| 🟡 Partly | Works, some phrasings go elsewhere or ask a question first | 26 |
| 🟠 Needs a fix | Many phrasings misrouted; needs description tuning (bot side) | 11 |
| ⚪ Built, not verified live | Built, but live proof is missing (see the Gap column) | 9 |
| 🔴 Bank error | The bank returns an error for the test customer | 2 |
| ⛔ No backend | No backend, or the API is not wired / information missing | 6 |
| ➖ Not a chat use case | Not a chat request, or left out on purpose | 8 |

**Handled as:** *Answer in chat* = bot looks it up · *Change in chat* = bot does it after yes/no or a code · *Gather → box* = bot collects details, app shows a prefilled box · *App action → box* = bot makes no bank call, app shows a box · *Info only* = text only.

| Intent | # | Use case | Handled as | Status | Gap |
|---|---|---|---|---|---|
| ACCOUNT_INFO | 1.1 | Get all accounts | Answer in chat | ✅ Working |  |
| ACCOUNT_INFO | 1.2 | Get account detail | Answer in chat | 🟡 Partly | Some phrasings go elsewhere or ask first |
| ACCOUNT_INFO | 1.3 | Get account by account/card number | — | ➖ Not a chat use case | Pre-login step |
| ACCOUNT_INFO | 1.4 | Get accounts by username | — | ➖ Not a chat use case | Pre-login step |
| ACCOUNT_INFO | 1.5 | Star account | App action → box | 🟠 Needs a fix | Many phrasings misrouted: tune the description |
| ACCOUNT_INFO | 1.6 | My loans | Answer in chat | ✅ Working |  |
| ACCOUNT_INFO | 1.7 | FD profit history | Answer in chat | 🔴 Bank error | Needs API info: bank returns 404 for the test customer's FD; unknown whether data or API |
| ACCOUNT_INFO | 1.8 | DPS profit history | Answer in chat | 🔴 Bank error | Needs API info: same as 1.7 for DPS |
| ACCOUNT_INFO | — | Cards list | Answer in chat | ✅ Working |  |
| ACCOUNT_INFO | — | Account transactions | Answer in chat | ✅ Working |  |
| ATM_SUPPORT | 2.1 | Cash by code | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| ATM_SUPPORT | 2.2 | Raise dispute | Gather → box | ✅ Working |  |
| ATM_SUPPORT | 2.3 | List disputes | Answer in chat | ✅ Working |  |
| CARD_ISSUE | 3.1 | Reset card PIN | App action → box | ✅ Working |  |
| CARD_ISSUE | 3.2 | Unfreeze card | App action → box | ✅ Working |  |
| CARD_ISSUE | 3.3 | Raise dispute | Gather → box | ✅ Working |  |
| CARD_ISSUE | 3.4 | List disputes | Answer in chat | ✅ Working |  |
| CARD_ISSUE | 3.5 | Submit complaint | Change in chat | ⚪ Built, not verified live | Same as 8.4 |
| CARD_ISSUE | 3.6 | My complaints | Answer in chat | ✅ Working |  |
| CARD_MANAGEMENT | 4.1 | Freeze card | Change in chat | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_MANAGEMENT | 4.2 | Unfreeze card | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_MANAGEMENT | 4.3 | Close card | App action → box | ✅ Working |  |
| CARD_MANAGEMENT | 4.4 | Contactless on/off | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_MANAGEMENT | 4.5 | International transaction on/off | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| CARD_MANAGEMENT | 4.6 | Reset card PIN | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_MANAGEMENT | 4.7 | Limit change — submit | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_MANAGEMENT | 4.8 | Limit change — list | Answer in chat | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_MANAGEMENT | 4.9 | Limit change — cancel | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_MANAGEMENT | 4.10 | Card products list | Answer in chat | ✅ Working |  |
| CARD_MANAGEMENT | 4.11 | Apply for debit card | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| CARD_MANAGEMENT | 4.12 | Reveal debit card details | — | ➖ Not a chat use case | Not built on purpose (full card number is sensitive) |
| CARD_MANAGEMENT | 4.13 | Apply for prepaid card | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_MANAGEMENT | 4.14 | Reveal prepaid card details | — | ➖ Not a chat use case | Not built on purpose (sensitive) |
| CARD_MANAGEMENT | 4.15 | Virtual card — submit | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| CARD_MANAGEMENT | 4.16 | Virtual card — list | Answer in chat | ✅ Working |  |
| CARD_MANAGEMENT | 4.17 | Virtual card — cancel | App action → box | ✅ Working |  |
| CARD_MANAGEMENT | 4.18 | Virtual card — reveal | — | ➖ Not a chat use case | Not built on purpose (sensitive) |
| CARD_MANAGEMENT | 4.19 | Star card | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| CARD_MANAGEMENT | 4.20 | Credit card bill payment (card service) | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| CARD_MANAGEMENT | 4.21 | Credit card bill payment (bill service) | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_MANAGEMENT | 4.22 | QR payment cards — list | Not available (no backend) | ⛔ No backend | No backend |
| CARD_MANAGEMENT | 4.23 | QR payment card — enable/disable | Not available (no backend) | ⛔ No backend | No backend |
| CARD_REPLACEMENT | 5.1 | List replacement requests | Answer in chat | ✅ Working |  |
| CARD_REPLACEMENT | 5.2 | Cancel replacement request | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| CARD_REPLACEMENT | 5.3 | Reveal replacement card details | — | ➖ Not a chat use case | Not built on purpose (sensitive) |
| CHECK_BALANCE | 6.1 | Account balance | Answer in chat | ✅ Working |  |
| CHECK_BALANCE | 6.2 | Credit card summary | Answer in chat | ⚪ Built, not verified live | Needs test data: the test customer has no credit card, real payload never seen |
| EDIT_PERSONAL_DETAILS | 7.1 | Get profile | Answer in chat | ✅ Working |  |
| EDIT_PERSONAL_DETAILS | 7.2 | Update nickname | Change in chat | ✅ Working |  |
| EDIT_PERSONAL_DETAILS | 7.3/7.4 | Upload profile image | Gather → box | ✅ Working |  |
| EDIT_PERSONAL_DETAILS | 7.5 | Update mobile number | Change in chat | ⚪ Built, not verified live | Asks for details first; code step not re-verified live |
| EDIT_PERSONAL_DETAILS | 7.6 | Update email address | Change in chat | ✅ Working |  |
| EDIT_PERSONAL_DETAILS | 7.7 | Get address | Answer in chat | ✅ Working |  |
| EDIT_PERSONAL_DETAILS | 7.8 | Update address | Change in chat | ✅ Working |  |
| EDIT_PERSONAL_DETAILS | 7.9 | Submit KYC | App action → box | ✅ Working |  |
| EDIT_PERSONAL_DETAILS | 7.10 | My contacts | Answer in chat | 🟡 Partly | Some phrasings go elsewhere or ask first |
| EDIT_PERSONAL_DETAILS | 7.11 | Profile change — submit | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| EDIT_PERSONAL_DETAILS | 7.12 | Profile change — list | Answer in chat | ✅ Working |  |
| EDIT_PERSONAL_DETAILS | 7.13 | Contact priority — submit | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| EDIT_PERSONAL_DETAILS | 7.14 | Contact priority — list | Answer in chat | ✅ Working |  |
| FAILED_TRANSFER | 8.1 | Transaction history | Answer in chat | ✅ Working |  |
| FAILED_TRANSFER | 8.2 | Raise dispute | Gather → box | ✅ Working |  |
| FAILED_TRANSFER | 8.3 | List disputes | Answer in chat | ✅ Working |  |
| FAILED_TRANSFER | 8.4 | Submit complaint | Change in chat | ⚪ Built, not verified live | Complaint routing was fixed after the last live run; not re-tested |
| FAILED_TRANSFER | 8.5 | My complaints | Answer in chat | 🟡 Partly | Some phrasings go elsewhere or ask first |
| FALLBACK | — | General bank question / off-topic | Answer in chat | ✅ Working |  |
| FEES | 10.1 | Transaction charge quote | Answer in chat | ✅ Working | Live-checked on 2026-10-03 and 2026-10-05; the latest run asked for details (not a failure) |
| GREETING | — | Greeting and small talk | Answer in chat | 🟡 Partly | Greeting can come back as 'You mentioned…' (wording) |
| LOST_OR_STOLEN_CARD | 12.1 | Report lost/stolen card | Gather → box | ✅ Working |  |
| LOST_OR_STOLEN_CARD | 12.2 | Freeze card immediately | Change in chat | 🟡 Partly | Some phrasings go elsewhere or ask first |
| MINI_STATEMENT | 13.1 | Transaction list | Answer in chat | ⚪ Built, not verified live | Bank 502 outages during the run; earlier runs passed |
| MINI_STATEMENT | 13.2 | Account transactions | Answer in chat | ⚪ Built, not verified live | Bank 502 outages during the run; earlier runs passed |
| MINI_STATEMENT | 13.3 | Credit card statement | Answer in chat | ⚪ Built, not verified live | Needs test data: no credit card, real statement shape never seen |
| MINI_STATEMENT | 13.4 | Expense tracker category transactions | Answer in chat | ⛔ No backend | Needs API info: no category-list endpoint among the supplied 46 |
| TRANSFER | 14.1 | Own account transfer | Gather → box | ✅ Working | Transfer probe 2026-10-07: 51 of 52 phrasings correct. One account only: bot says no other account |
| TRANSFER | 14.2 | City Bank transfer | Gather → box | ✅ Working | Transfer probe 2026-10-07: correct, number and amount prefilled |
| TRANSFER | 14.3 | Other bank transfer | Gather → box | ✅ Working | Transfer probe 2026-10-07: correct, number and amount prefilled |
| TRANSFER | 14.4 | Other banks list | Not available (no backend) | ⛔ No backend | No backend |
| TRANSFER | 14.5 | Gift transfer | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| TRANSFER | 14.6 | Gifts received | Answer in chat | ✅ Working |  |
| TRANSFER | 14.7 | Generic transaction | — | ➖ Not a chat use case | Bank-internal, no chat ask |
| TRANSFER | 14.8 | Linked account check | — | ➖ Not a chat use case | Bank-internal, no chat ask |
| TRANSFER | 14.9 | Email transfer — create | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| TRANSFER | 14.10 | Email transfer — list | Answer in chat | ✅ Working |  |
| TRANSFER | 14.11 | Email transfer — details | Answer in chat | ✅ Working |  |
| TRANSFER | 14.12 | Email transfer — cancel | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.13 | Email transfer — resend | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.14 | Wallet/MFS transfer | Gather → box | ✅ Working | Transfer probe 2026-10-07: correct, number and amount prefilled. Plain 'send 500 taka' may be read as cash by code |
| TRANSFER | 14.15 | Wallet verify | Answer in chat | ⛔ No backend | Needs API info: wallet verify endpoint not wired |
| TRANSFER | 14.16 | QR pay | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.17 | QR parse | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.18 | QR payment history | Answer in chat | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.19 | Beneficiary — list | Answer in chat | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.20 | Beneficiary — add | Change in chat | ⚪ Built, not verified live | Needs API info: bank returns 500 on add; required fields per serviceType unknown |
| TRANSFER | 14.21 | Beneficiary — edit | App action → box | ✅ Working |  |
| TRANSFER | 14.22 | Beneficiary — delete | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.23 | Beneficiary — upload/change photo | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.24 | Beneficiary — remove photo | App action → box | 🟠 Needs a fix | Many phrasings ask or go elsewhere; bot side only, no data missing |
| TRANSFER | 14.25 | Beneficiary — pin/unpin | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.26 | Recipient lookup by account number | Answer in chat | ⛔ No backend | Needs API info: recipient lookup not wired |
| TRANSFER | 14.27 | My transfer limit — get | Answer in chat | ⚪ Built, not verified live | Bank 502 outages during the run; earlier runs passed |
| TRANSFER | 14.28 | My transfer limit — request change | App action → box | 🟡 Partly | Some phrasings go elsewhere or ask first |
| TRANSFER | 14.29 | My transfer limit — cancel pending change | App action → box | ✅ Working |  |

**Empty lists:** the test customer's lists (disputes, complaints, requests, gifts, email transfers, QR history, beneficiaries) are all empty, so the field layout of a non-empty entry has not been seen for any of them. Confirm the row fields with real data before finalising the list cards.
