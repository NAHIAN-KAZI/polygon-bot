# Intent use-case coverage — what the bot can and cannot do

Status as of 2026-10-07 (English, `llama3.1:8b`); Bangla, Banglish and voice added 2026-10-12 (`gemma4`, see that section). This is the T-80 report. It covers the bank's 14 intents and every use case in `planning/input/INTENT_IMPLEMENTATION_STATUS.md` that is a real chatbot request.

## How to read this

- **What the bot does** comes from the code and the app-action registry (`app/banking/ui_actions.py`).
- **Tested** comes from the live test suite (`experiments/dynamic_suite`): every use case was asked five ways (one word, two words, casual with typos, a full sentence, a long paragraph), 465 questions in all. "Passed" means the bot routed to the expected service (or correctly declined). A question that makes the bot ask for more detail (the amount, the wallet number, which card) is counted separately as \"asked\": it is neither a pass nor a failure. The questions are written by a model and sometimes drift off their use case, so the counts are indicative, not exact.
- **Off-route counts overstate real errors.** A manual review of an earlier run found that about half of the off-route questions were valid alternatives (a limit question filed under the "cancel limit" use case, a one-word "Profile" showing the profile) rather than mistakes.
- Evidence is the best valid result per question across the runs on 2026-10-06 and 2026-10-07: 375 of the 465 come from the latest build, the other 90 from the previous build (the latest run lost them to bank outages).
- **Result** (based on how many of the five questions went to the wrong place): Works (0–1 off-route), Partly (2–3), Weak (4–5); for app actions the screen has to actually be offered, so they are judged on passes (4–5 Works, 2–3 Partly, 0–1 Weak); **Unverified** means the bot asked for more detail every time, so the use case was never seen working end to end; Bank-side error (the bank returns an error for the test customer), Not available (the bank has no backend for it).

### The four things the bot can do with a request

1. **Answered in chat**: looks the data up for the customer and explains it in plain words.
2. **Executed in chat (approved)**: the only changes the bot makes itself, each after a yes/no or a one-time code: card freeze, mobile change, email change, nickname, address, complaint, beneficiary add.
3. **Gather + redirect**: collects the details, then hands the customer to the right app screen with the fields filled in. The bot never sends money and never submits a dispute.
4. **App action**: the request is not carried out in chat; the app gets the screen to open (with any fields the customer already gave) or the information to show. No bank call.

## Summary

| Intent | Use cases | Works | Partly | Weak | Unverified | Bank-side error | Not available | Passed | Asked for detail | Off-route | Bank error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ACCOUNT_INFO | 8 | 3 | 2 | 1 | 0 | 2 | 0 | 19 | 5 | 7 | 9 |
| ATM_SUPPORT | 3 | 2 | 1 | 0 | 0 | 0 | 0 | 8 | 6 | 1 | 0 |
| CARD_ISSUE | 6 | 5 | 1 | 0 | 0 | 0 | 0 | 19 | 9 | 2 | 0 |
| CARD_MANAGEMENT | 20 | 4 | 9 | 5 | 0 | 0 | 2 | 42 | 37 | 21 | 0 |
| CARD_REPLACEMENT | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 5 | 3 | 2 | 0 |
| CHECK_BALANCE | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 6 | 1 | 2 | 1 |
| EDIT_PERSONAL_DETAILS | 13 | 9 | 1 | 2 | 1 | 0 | 0 | 28 | 28 | 9 | 0 |
| FAILED_TRANSFER | 5 | 3 | 1 | 1 | 0 | 0 | 0 | 14 | 2 | 9 | 0 |
| FALLBACK | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 1 | 0 |
| FEES | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 5 | 0 | 0 |
| GREETING | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 3 | 0 | 2 | 0 |
| LOST_OR_STOLEN_CARD | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 3 | 3 | 2 | 2 |
| MINI_STATEMENT | 3 | 0 | 1 | 0 | 0 | 2 | 0 | 2 | 1 | 5 | 7 |
| TRANSFER | 25 | 6 | 12 | 3 | 2 | 1 | 1 | 45 | 61 | 15 | 4 |
| **Total** | **92** | **36** | **32** | **12** | **4** | **5** | **3** | **198** | **161** | **78** | **23** |

## Known limits that affect many use cases

- **\"Asked for detail\" is not a failure.** The bot asks for what is missing before it can act: the amount for a fee quote, the wallet number for a transfer, which card, what the new value is, or what a one-word message means. The test records these separately from passes and from wrong routes.
- **Vague messages get a question.** A single word like "Cancel", "Card" or "Pay" now makes the bot ask what the customer wants and offer the options, instead of guessing. In the test this is counted as "asked", not as a pass.
- **FD and DPS profit history**: the bank returns an error for the test customer, so the bot says it could not fetch it. This is bank-side.
- **App actions**: the prefilled fields are sent to the app, but most target screens do not read them yet (only the card PIN reset screen reads a map). Three screens (card detail, card limit change, card close/replace) need a card object passed in, so the app shows information only for them.
- **QR payment cards and the other-banks list** have no backend; the bot says they are not available.
- **Wording varies** every time because the model writes each reply; the app must never match on reply text.
- **Complaints are misrouted in the latest build (regression, not fixed yet).** A complaint about the app or the service ("Complain", "Bad app", "this app is so slow, I'd like to complain") is routed to "raise a dispute about a transaction" and the reply even mentions a transaction. In the earlier run these asked for the complaint text or passed. This affects use cases 3.5 and 8.4 (the complaint rows) and needs a routing fix before the complaint flow can be called working.
- **Observed quality issues in the latest checks** (not fixed yet): a plain greeting can come back as "You mentioned needing help with something…"; replies take about 10–15 seconds on the current hardware; the bot occasionally adds a claim that is not in its data (for example, saying cash can be withdrawn at an ATM when asked about "cash").

## Use cases by intent

### ACCOUNT_INFO

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 1.1 | Get all accounts | Answered in chat | Looks up the customer's own data and explains it in plain words. | 5/5 passed | Works |
| 1.2 | Get account detail | Answered in chat | Looks up the customer's own data and explains it in plain words. | 3/5 passed, 2 off-route | Partly |
| 1.5 | Star account | App action | Choose which account or card to show on the home screen and switch its star on or off. Opens `CustomizeQuickViewScreen` (`/customize_quick_view`). | 1/5 passed, 2 asked, 2 off-route | Weak |
| 1.6 | My loans | Answered in chat | Looks up the customer's own data and explains it in plain words. | 5/5 passed | Works |
| 1.7 | FD profit history | Answered in chat | Looks up the customer's own data and explains it in plain words. The bank returns an error for this test customer's FD record, so the bot says it could not fetch it. | 0/5 passed, 5 bank error | Bank-side error |
| 1.8 | DPS profit history | Answered in chat | Looks up the customer's own data and explains it in plain words. The bank returns an error for this test customer's DPS records. | 0/5 passed, 1 asked, 4 bank error | Bank-side error |
| — Cards list | Cards list | Answered in chat | Looks up the customer's own data and explains it in plain words. | 4/5 passed, 1 asked | Works |
| — Account transactions | Account transactions | Answered in chat | Looks up the customer's own data and explains it in plain words. | 1/5 passed, 1 asked, 3 off-route | Partly |

### ATM_SUPPORT

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 2.1 | Cash by code | App action | Choose the account, the recipient's mobile number, the amount and how the code is delivered, then confirm with a one-time code and transaction PIN. Opens `CashByCodeScreen` (`/cash_by_code`). | 2/5 passed, 2 asked, 1 off-route | Partly |
| 2.2 | Raise dispute | Gather + redirect | Finds the account and the transaction itself, gathers the reason, hands off to the dispute screen. Never submits. | 2/5 passed, 3 asked | Works |
| 2.3 | List disputes | Answered in chat | Looks up the customer's own data and explains it in plain words. | 4/5 passed, 1 asked | Works |

### CARD_ISSUE

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 3.1 | Reset card PIN | App action | Choose the card, then confirm with a one-time code and their PIN or password. Opens `SelectCardForPinResetScreen` (`/set_reset_card_pin`). | 4/5 passed, 1 asked | Works |
| 3.2 | Unfreeze card | App action | Choose the frozen card and confirm with a one-time code and their PIN or password. Opens `FreezeCardScreen` (`/freeze_card`). | 4/5 passed, 1 asked | Works |
| 3.3 | Raise dispute | Gather + redirect | Same as 2.2. | 3/5 passed, 2 asked | Works |
| 3.4 | List disputes | Answered in chat | Looks up the customer's own data and explains it in plain words. | 5/5 passed | Works |
| 3.5 | Submit complaint | Executed in chat (approved) | Asks yes/no, then submits the complaint (it appears under My Tickets). | 0/5 passed, 3 asked, 2 off-route | Partly |
| 3.6 | My complaints | Answered in chat | Looks up the customer's own data and explains it in plain words. | 3/5 passed, 2 asked | Works |

### CARD_MANAGEMENT

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 4.1 | Freeze card | Executed in chat (approved) | Asks yes/no, sends a one-time code to the registered phone; the customer enters the code and PIN or password in the app's secure form; only then is the card frozen. | 2/5 passed, 1 asked, 2 off-route | Partly |
| 4.2 | Unfreeze card | App action | Choose the frozen card and confirm with a one-time code and their PIN or password. Opens `FreezeCardScreen` (`/freeze_card`). | 3/5 passed, 1 asked, 1 off-route | Partly |
| 4.3 | Close card | App action | Choose the card and confirm the permanent closure with a one-time code and their PIN or password. Opens `CardReplacementScreen` (`/request_card_replacement`); the app currently shows this as information because the screen needs a card passed in. | 4/5 passed, 1 asked | Works |
| 4.4 | Contactless on/off | App action | Open the card, then its settings, and switch contactless on or off. Opens `CardDetailScreen` (`/card_detail`); the app currently shows this as information because the screen needs a card passed in. | 2/5 passed, 2 asked, 1 off-route | Partly |
| 4.5 | International transaction on/off | App action | Choose the card, switch international use on or off and confirm with a one-time code and their PIN or password. Opens `SelectCardForInternationalScreen` (`/international_transaction/select_card`). | 1/5 passed, 3 asked, 1 off-route | Weak |
| 4.6 | Reset card PIN | App action | Choose the card, then confirm with a one-time code and their PIN or password. Opens `SelectCardForPinResetScreen` (`/set_reset_card_pin`). | 3/5 passed, 2 asked | Partly |
| 4.7 | Limit change — submit | App action | Choose the credit card and enter the new limit they want; the bank reviews it. Opens `CardLimitChangeScreen` (`/card_limit_change_request`); the app currently shows this as information because the screen needs a card passed in. | 3/5 passed, 2 asked | Partly |
| 4.8 | Limit change — list | Answered in chat | Looks up the customer's own data and explains it in plain words. | 1/5 passed, 2 asked, 2 off-route | Partly |
| 4.9 | Limit change — cancel | App action | Open the pending limit-change request and confirm the cancellation. Opens `CardLimitChangeScreen` (`/card_limit_change_request`); the app currently shows this as information because the screen needs a card passed in. | 2/5 passed, 1 asked, 2 off-route | Partly |
| 4.10 | Card products list | Answered in chat | Looks up the customer's own data and explains it in plain words. | 4/5 passed, 1 asked | Works |
| 4.11 | Apply for debit card | App action | Choose a card product and the account to link, enter the name for the card and confirm with a one-time code and PIN. Opens `CardProductCatalogScreen` (`/card_product_catalog`). | 0/5 passed, 4 asked, 1 off-route | Weak |
| 4.13 | Apply for prepaid card | App action | Choose a card product and the account to link, enter the name for the card and confirm with a one-time code and PIN. Opens `CardProductCatalogScreen` (`/card_product_catalog`). | 2/5 passed, 1 asked, 2 off-route | Partly |
| 4.15 | Virtual card — submit | App action | Choose a card product and the account to link, enter the name for the card and confirm with a one-time code and PIN. Opens `CardProductCatalogScreen` (`/card_product_catalog`). | 1/5 passed, 2 asked, 2 off-route | Weak |
| 4.16 | Virtual card — list | Answered in chat | Looks up the customer's own data and explains it in plain words. | 4/5 passed, 1 asked | Works |
| 4.17 | Virtual card — cancel | App action | Tells the customer: the app has no screen for cancelling a virtual card at the moment. | 4/5 passed, 1 asked | Works |
| 4.19 | Star card | App action | Choose which account or card to show on the home screen and switch its star on or off. Opens `CustomizeQuickViewScreen` (`/customize_quick_view`). | 0/5 passed, 4 asked, 1 off-route | Weak |
| 4.20 | Credit card bill payment (card service) | App action | Open the credit card, choose what to pay (total outstanding, statement due or minimum due) and the account to pay from. Opens `CardDetailScreen` (`/card_detail`); the app currently shows this as information because the screen needs a card passed in. | 1/5 passed, 2 asked, 2 off-route | Weak |
| 4.21 | Credit card bill payment (bill service) | App action | Enter the card number, the amount and the account to pay from, then a one-time code and transaction PIN. Opens `CardPaymentDetailsScreen` (`/card_payment/details/:type`); shown as information in the app (no direct route). | 2/5 passed, 1 asked, 2 off-route | Partly |
| 4.22 | QR payment cards — list | Not available (no backend) | QR payment card settings are not available at the moment. | 0/5 passed, 3 asked, 2 off-route | Not available |
| 4.23 | QR payment card — enable/disable | Not available (no backend) | QR payment card settings are not available at the moment. | 3/5 passed, 2 asked | Not available |

### CARD_REPLACEMENT

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 5.1 | List replacement requests | Answered in chat | Looks up the customer's own data and explains it in plain words. | 2/5 passed, 2 asked, 1 off-route | Works |
| 5.2 | Cancel replacement request | App action | Open the pending replacement request and confirm the cancellation. Opens `CardReplacementScreen` (`/request_card_replacement`); the app currently shows this as information because the screen needs a card passed in. | 3/5 passed, 1 asked, 1 off-route | Partly |

### CHECK_BALANCE

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 6.1 | Account balance | Answered in chat | Looks up the customer's own data and explains it in plain words. | 4/5 passed, 1 asked | Works |
| 6.2 | Credit card summary | Answered in chat | Looks up the customer's own data and explains it in plain words. | 2/5 passed, 2 off-route, 1 bank error | Partly |

### EDIT_PERSONAL_DETAILS

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 7.1 | Get profile | Answered in chat | Looks up the customer's own data and explains it in plain words. | 5/5 passed | Works |
| 7.2 | Update nickname | Executed in chat (approved) | Asks yes/no, then changes the nickname. | 5/5 passed | Works |
| 7.3/7.4 | Upload profile image | Gather + redirect | Redirects to the profile photo screen; photos are chosen in the app. | 1/5 passed, 3 asked, 1 off-route | Works |
| 7.5 | Update mobile number | Executed in chat (approved) | Sends a one-time code to the current registered phone, then changes the mobile number. | 0/5 passed, 5 asked | Unverified |
| 7.6 | Update email address | Executed in chat (approved) | Sends a one-time code to the registered phone, then changes the email address. | 1/5 passed, 4 asked | Works |
| 7.7 | Get address | Answered in chat | Looks up the customer's own data and explains it in plain words. | 3/5 passed, 2 asked | Works |
| 7.8 | Update address | Executed in chat (approved) | Asks yes/no, then updates the address. | 3/5 passed, 2 asked | Works |
| 7.9 | Submit KYC | App action | Photograph the NID front and back and the signature, and optionally add occupation and income details; photos are taken in the app. Opens `UpdateKycScreen` (`/profile/update_kyc`). | 4/5 passed, 1 asked | Works |
| 7.10 | My contacts | Answered in chat | Looks up the customer's own data and explains it in plain words. | 3/5 passed, 2 off-route | Partly |
| 7.11 | Profile change — submit | App action | Pick the detail to change, enter the new value and a reason, and verify with a one-time code; the bank reviews it. Opens `ProfileChangeRequestScreen` (`/profile_change_request`). | 0/5 passed, 3 asked, 2 off-route | Weak |
| 7.12 | Profile change — list | Answered in chat | Looks up the customer's own data and explains it in plain words. | 2/5 passed, 2 asked, 1 off-route | Works |
| 7.13 | Contact priority — submit | App action | Choose which registered contact becomes primary, give a reason and verify with a one-time code. Opens `ContactPriorityScreen` (`/contact_priority`). | 0/5 passed, 3 asked, 2 off-route | Weak |
| 7.14 | Contact priority — list | Answered in chat | Looks up the customer's own data and explains it in plain words. | 1/5 passed, 3 asked, 1 off-route | Works |

### FAILED_TRANSFER

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 8.1 | Transaction history | Answered in chat | Looks up the customer's own data and explains it in plain words. | 5/5 passed | Works |
| 8.2 | Raise dispute | Gather + redirect | Same as 2.2. | 4/5 passed, 1 off-route | Works |
| 8.3 | List disputes | Answered in chat | Looks up the customer's own data and explains it in plain words. | 4/5 passed, 1 off-route | Works |
| 8.4 | Submit complaint | Executed in chat (approved) | Same as 3.5. | 0/5 passed, 5 off-route | Weak |
| 8.5 | My complaints | Answered in chat | Looks up the customer's own data and explains it in plain words. | 1/5 passed, 2 asked, 2 off-route | Partly |

### FEES

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 10.1 | Transaction charge quote | Answered in chat | Looks up the customer's own data and explains it in plain words. | 0/5 passed, 5 asked | Unverified |

### LOST_OR_STOLEN_CARD

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 12.1 | Report lost/stolen card | Gather + redirect | Explains that reporting closes the card for good, offers freezing instead, and hands off to the app's report screen. The bot never calls the bank. | 3/5 passed, 2 asked | Works |
| 12.2 | Freeze card immediately | Executed in chat (approved) | Same as 4.1, when the customer explicitly asks to freeze or block the card. | 0/5 passed, 1 asked, 2 off-route, 2 bank error | Partly |

### MINI_STATEMENT

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 13.1 | Transaction list | Answered in chat | Looks up the customer's own data and explains it in plain words. | 0/5 passed, 1 asked, 1 off-route, 3 bank error | Bank-side error |
| 13.2 | Account transactions | Answered in chat | Looks up the customer's own data and explains it in plain words. | 0/5 passed, 1 off-route, 4 bank error | Bank-side error |
| 13.3 | Credit card statement | Answered in chat | Looks up the customer's own data and explains it in plain words. | 2/5 passed, 3 off-route | Partly |

### TRANSFER

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| 14.1 | Own account transfer | Gather + redirect | Gathers the details and hands off to the own-account transfer screen. Never sends money. | 4/5 passed, 1 asked | Works |
| 14.2 | City Bank transfer | Gather + redirect | Gathers the details and hands off to the Polygon Bank account transfer screen. Never sends money. | 0/5 passed, 3 asked, 2 off-route | Partly |
| 14.3 | Other bank transfer | Gather + redirect | Gathers the details and hands off to the other-bank transfer screen. Never sends money. | 0/5 passed, 5 asked | Unverified |
| 14.4 | Other banks list | Not available (no backend) | This list is not available at the moment. | 2/5 passed, 3 asked | Not available |
| 14.5 | Gift transfer | App action | Choose the recipient, a gift design, a wish message and the amount, then confirm with a one-time code and PIN. Opens `GiftScreen` (`/gift`). | 0/5 passed, 5 asked | Weak |
| 14.6 | Gifts received | Answered in chat | Looks up the customer's own data and explains it in plain words. | 3/5 passed, 2 asked | Works |
| 14.9 | Email transfer — create | App action | Enter the recipient's email, the amount and a security question and answer, then confirm with a one-time code and PIN. Opens `EmailTransferEntryScreen` (`/email_transfer/entry`). | 0/5 passed, 5 asked | Weak |
| 14.10 | Email transfer — list | Answered in chat | Looks up the customer's own data and explains it in plain words. | 2/5 passed, 3 asked | Works |
| 14.11 | Email transfer — details | Answered in chat | Looks up the customer's own data and explains it in plain words. | 2/5 passed, 3 asked | Works |
| 14.12 | Email transfer — cancel | App action | Open the email transfer and choose cancel or resend. Opens `EmailTransferListScreen` (`/email_transfer/list`). | 2/5 passed, 2 asked, 1 off-route | Partly |
| 14.13 | Email transfer — resend | App action | Open the email transfer and choose cancel or resend. Opens `EmailTransferListScreen` (`/email_transfer/list`). | 3/5 passed, 1 asked, 1 off-route | Partly |
| 14.14 | Wallet/MFS transfer | Gather + redirect | Gathers wallet provider, number and amount, then hands off to the wallet transfer screen. Never sends money. | 0/5 passed, 5 asked | Unverified |
| 14.16 | QR pay | App action | Scan the merchant's QR code with the phone camera, then confirm the amount and the account to pay from with a one-time code and PIN. Opens `QrScanScreen`; shown as information in the app (no direct route). | 3/5 passed, 2 asked | Partly |
| 14.17 | QR parse | App action | Scan the merchant's QR code with the phone camera, then confirm the amount and the account to pay from with a one-time code and PIN. Opens `QrScanScreen`; shown as information in the app (no direct route). | 2/5 passed, 2 asked, 1 off-route | Partly |
| 14.18 | QR payment history | Answered in chat | Looks up the customer's own data and explains it in plain words. | 1/5 passed, 1 asked, 3 off-route | Partly |
| 14.19 | Beneficiary — list | Answered in chat | Looks up the customer's own data and explains it in plain words. | 3/5 passed, 2 off-route | Partly |
| 14.20 | Beneficiary — add | Executed in chat (approved) | Collects the name and account number (and bank details for another bank), asks yes/no, then saves the beneficiary. | 0/5 passed, 3 asked, 2 off-route | Partly |
| 14.21 | Beneficiary — edit | App action | Open the beneficiary and change its nickname (only the nickname can be edited). Opens `BeneficiaryFormScreen` (`/beneficiary/form`). | 4/5 passed, 1 off-route | Works |
| 14.22 | Beneficiary — delete | App action | Open the saved beneficiaries, pick the one to remove and confirm. Opens `BeneficiaryScreen` (`/beneficiary`). | 2/5 passed, 3 asked | Partly |
| 14.23 | Beneficiary — upload/change photo | App action | Pick a photo from the phone's gallery or camera; photos are chosen in the app. Opens `BeneficiaryFormScreen` (`/beneficiary/form`). | 2/5 passed, 3 asked | Partly |
| 14.24 | Beneficiary — remove photo | App action | Pick a photo from the phone's gallery or camera; photos are chosen in the app. Opens `BeneficiaryFormScreen` (`/beneficiary/form`). | 1/5 passed, 3 asked, 1 off-route | Weak |
| 14.25 | Beneficiary — pin/unpin | App action | Tap the pin on the beneficiary to keep it at the top (this is list pinning, not a security PIN). Opens `BeneficiaryScreen` (`/beneficiary`). | 3/5 passed, 1 asked, 1 off-route | Partly |
| 14.27 | My transfer limit — get | Answered in chat | Looks up the customer's own data and explains it in plain words. | 0/5 passed, 1 asked, 4 bank error | Bank-side error |
| 14.28 | My transfer limit — request change | App action | Choose the account and the new limit, or open the pending request, and confirm with a one-time code and PIN. Opens `TransferLimitScreen` (`/transfer_limit`). | 2/5 passed, 3 asked | Partly |
| 14.29 | My transfer limit — cancel pending change | App action | Choose the account and the new limit, or open the pending request, and confirm with a one-time code and PIN. Opens `TransferLimitScreen` (`/transfer_limit`). | 4/5 passed, 1 asked | Works |

### GREETING

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| — | Greeting and small talk | Answered in chat | Looks up the customer's own data and explains it in plain words. | 3/5 passed, 2 off-route | Partly |

### FALLBACK

| # | Use case | Type | What the bot does | Tested | Result |
|---|---|---|---|---|---|
| — | General bank knowledge and off-topic | Answered in chat | Looks up the customer's own data and explains it in plain words. | 4/5 passed, 1 off-route | Works |

## Bangla, Banglish and voice (added 2026-10-12)

The English results above are from the 2026-10-07 runs on `llama3.1:8b`. This section is from 2026-10-12, on `gemma4` (gemma-4-12B-it, 8-bit weights, on the vLLM server) with the routing prompt tuned on 2026-10-12 (see "Changes made" below).

**How it was tested**

- **Typed:** every use case got five more customer messages, written by the model in Bangla script (short and a full sentence), Banglish, meaning Bangla written in English letters (short and a full sentence), and mixed Bangla-English (for example "আমার card টা block করেন"). That is 485 new messages, kept in `experiments/dynamic_suite/questions_multilingual.json` next to the English set. Each was routed with `route_only` (routing only: no bank calls, no replies).
- **Spoken:** the Bangla sentence, the mixed sentence and the English sentence of every use case were turned into speech with neural voices (Bangla bn-BD, English en-IN), transcribed by the app's own voice input, then routed (`voice_route.py`). That is 287 spoken messages. Banglish is not spoken separately: people who type Banglish speak Bangla.
- The same rules as above apply: "asked a question" is not a failure; some generated messages drift into a neighbouring use case, so "wrong service" overstates real errors (for example "অভিযোগ দেখুন" ("show complaints"), filed under *List disputes*, correctly opens the complaints list).
- Synthetic voices are cleaner than real customers on a phone, and a Bangla voice reading English words sounds less natural than a real bilingual speaker. Treat the spoken numbers as a first estimate; test with real recordings before relying on them.

**Before and after the 2026-10-12 prompt changes** (same messages, same model)

| Set | Messages | Routed right | Asked a question | Wrong service |
|---|---|---|---|---|
| English, typed: before | 465 | 205 (44%) | 216 | 44 |
| English, typed: after | 465 | 245 (53%) | 158 | 62 |
| Bangla / Banglish / mixed, typed: before | 485 | 327 (67%) | 100 | 58 |
| Bangla / Banglish / mixed, typed: after | 485 | 369 (76%) | 51 | 65 |
| Spoken: before | 287 | 170 (59%) | 86 | 30 |
| Spoken: after | 287 | 196 (68%) | 54 | 37 |

English one-word and two-word messages still mostly get a question (75 of 93 single words). That is by design: a single word like "Card" or "Pay" does not say what the customer wants.

**Changes made** (prompt wording only: no keyword lists, phrase matching or fixed replies)

1. **Route first, collect details later.** The model knew the right service but asked for details the service collects itself afterwards: "card harie gese" ("my card is lost") got "block it or replace it?", "bkash transfer koren" ("send money to bKash") got "how much, and to which number?", "pin change koren" ("change my PIN") got "which card?". The routing rule and the two tool descriptions now say: decide which service; ask a question only when it's unclear which service the customer wants, never for a card, amount, number or recipient. This change accounts for most of the gain.
2. **Voice transcription.** The first transcription prompt wrote spoken Bangla in Hindi (Devanagari) script ("अमरकार हरियगसे…" for "আমার কার্ড হারিয়ে গেছে"), and turned mixed Bangla-English speech into invented English sentences. The prompt now says the speaker may mix English words into Bangla, Bangla goes in Bangla script, and nothing is translated. One version also said the customer "talks about banking"; that made the model invent transfers and amounts that were never spoken ("how much is in my account?" became "transfer crores to my account"), so it was replaced by "write only words you actually hear; never add words, amounts or numbers".

**Open issues**

- **Misheard amounts in voice.** In the final run 8 of 287 transcripts contained a number that was never said, for example "৫০০ টাকা" (500 taka) heard as "50 টাকা". Transfers are never sent by the bot (the customer reviews the filled-in form and the reply states the amount), but a wrong amount can reach that form. Recommended: put the transcript in the message box for the customer to check before it is sent, rather than sending it straight away.
- **Hindi script still slips through** in a few Bangla transcripts; when it does, the message is usually routed wrongly or gets a question.
- **Newly wrong after change 1** (now routed instead of asked, but to the wrong place): "card ta star koro" ("star my card") opened card freeze; "show my full card number and CVV" opened the plain card list; "see who I registered as my contacts" opened add-beneficiary; "i got 500 taka from swadhin" opened email transfers; complaints about the service still go to "raise a dispute" (the regression listed above). Next round: sharpen those services' descriptions.
- Short Bangla messages remain the weakest typed style (62 of 97 routed right).

**Results**

Text run: `route_20261012_205054.jsonl`. Voice run: `voice_20261012_212013.jsonl`.

**Typed messages (Bangla script, Banglish, mixed)**

| Style | Questions | Routed right | Asked a question | Wrong service | Other |
|---|---|---|---|---|---|
| Bangla, short | 97 | 62 | 18 | 17 | 0 |
| Bangla, sentence | 97 | 79 | 7 | 11 | 0 |
| Banglish, short | 97 | 67 | 14 | 16 | 0 |
| Banglish, sentence | 97 | 81 | 6 | 10 | 0 |
| Mixed Bangla-English | 97 | 80 | 6 | 11 | 0 |
| **All** | **485** | **369 (76%)** | **51** | **65** | **0** |

**Spoken messages** (synthetic neural voices; transcribed by the app, then routed)

| Style | Questions | Routed right | Asked a question | Wrong service | Other |
|---|---|---|---|---|---|
| Bangla, sentence | 97 | 63 | 21 | 13 | 0 |
| Mixed Bangla-English | 97 | 58 | 26 | 13 | 0 |
| English | 93 | 75 | 7 | 11 | 0 |
| **All** | **287** | **196 (68%)** | **54** | **37** | **0** |

Per use case below: one example message per style, then the result for each style (✅ routed right, ❓ asked a question, ❌ wrong service, ⚠️ error). Typed: Bangla short, Bangla sentence, Banglish short, Banglish sentence, mixed. Spoken: Bangla, mixed, English.

#### ACCOUNT_INFO

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 1.1 | Get all accounts | আমার সবগুলো অ্যাকাউন্ট নাম্বার কি কি আছে একটু বলবেন? | sob account dekhao | আমার সব accounts এর list টা দেন। | ✅✅✅✅✅ | ✅❓✅ |
| 1.2 | Get account detail | আমার সবগুলো অ্যাকাউন্ট নম্বর দেখতে চাই। | account list koren | আমার সব accounts এর detail দেন। | ✅✅✅✅✅ | ✅✅✅ |
| 1.5 | Star account | আমি আমার সেভিংস অ্যাকাউন্টটা হোম স্ক্রিনে পিন করতে চাই। | account ta star koren | আমার account টা home screen এ favorite হিসেবে দেখাবেন। | ✅❓✅❓❓ | ✅✅❓ |
| 1.6 | My loans | আমার বর্তমানে কয়টি লোন আছে তা দেখতে চাই। | loan list dekhau | আমার loan list টা একটু দেখান। | ✅✅✅✅✅ | ✅✅✅ |
| 1.7 | FD profit history | আমার ফিক্সড ডিপোজিটের মুনাফার হিস্ট্রিটা দেখতে চাই। | FD profit koto? | আমার FD profit history টা কি চেক করা যাবে? | ✅✅✅✅✅ | ✅❌✅ |
| 1.8 | DPS profit history | আমার ডিএসএস অ্যাকাউন্টে এ পর্যন্ত কত লাভ হয়েছে তা দেখতে চাই। | dps profit history | আমার DPS scheme এর profit history দেখতে চাই। | ✅✅✅✅✅ | ✅❓✅ |
|  | — Cards list | আমার কাছে কয়টি কার্ড আছে তা দেখান। | card list dekhao | আমার সব cards এর list টা দেখান। | ✅✅✅✅✅ | ❓✅✅ |
|  | — Account transactions | গত মাসের সব ট্রানজ্যাকশন একটু দেখতে চাই। | transaction dekhao | আমার account এর statement গত ৫ দিনের জন্য চাই। | ✅✅✅✅✅ | ✅✅❌ |

#### CHECK_BALANCE

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 6.1 | Account balance | আমার অ্যাকাউন্টে এখন কত টাকা আছে জানাবেন কি? | balance koto? | আমার account balance কত জানি কি? | ✅✅✅✅✅ | ❓❓✅ |
| 6.2 | Credit card summary | আমার ক্রেডিট কার্ডের লিমিট এবং বকেয়া কত তা দেখতে চাই। | card balance koto | আমার credit card summary টা একটু দেখান। | ❌✅✅✅✅ | ✅✅✅ |

#### LOST_OR_STOLEN_CARD

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 12.1 | Report lost/stolen card | আমার ডেবিট কার্ডটা চুরি হয়েছে, আমি নতুন একটা চাই। | card harie gese | আমার card টা lost হয়ে গেছে, নতুন একটা নিয়ে দিন। | ✅✅✅✅✅ | ✅✅✅ |
| 12.2 | Freeze card immediately | আমার কার্ডটা হারিয়ে গেছে, দয়া করে এটা এখনই বন্ধ করে দিন। | card block koren | আমার card টা block করেন, হারিয়ে গেছে। | ✅❓✅✅✅ | ✅❓❓ |

#### ATM_SUPPORT

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 2.1 | Cash by code | আমি ৫০০০ টাকা ক্যাশ বাই কোড পাঠাতে চাই। | cash by code koren | আমি ৫০০০০ টাকা send করতে চাই cash by code এর মাধ্যমে। | ✅✅✅✅✅ | ✅✅✅ |
| 2.2 | Raise dispute | আমার অ্যাকাউন্ট থেকে টাকা কেটে নিয়েছে কিন্তু অন্যজনের কাছে এখনো পৌঁছায়নি। | transaction fail hoyeche | আমার বিকাশ থেকে টাকা কেটে নিয়েছে কিন্তু transaction status pending দেখাচ্ছে। | ❓✅✅✅✅ | ❓✅✅ |
| 2.3 | List disputes | আমার আগের অভিযোগগুলোর স্ট্যাটাস কী? | dispute check koren | আমার transaction dispute গুলো দেখতে চাই। | ❌❌✅✅✅ | ❓✅✅ |

#### CARD_ISSUE

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 3.1 | Reset card PIN | আমার কার্ডের পিন নম্বরটা রিসেট করে দিন। | pin change koren | আমার card এর PIN টা reset করে দিন। | ✅✅✅✅✅ | ❓❓✅ |
| 3.2 | Unfreeze card | আমার ডেবিট কার্ডটি ব্লক করা আছে, দয়া করে এটি আবার চালু করে দিন। | card unblock koren | আমার card টা block হয়ে গেছে, প্লিজ unfreeze করে দিন। | ✅✅✅✅✅ | ✅❓✅ |
| 3.3 | Raise dispute | আমার বিকাশ থেকে টাকা কেটেছে কিন্তু অন্যজনের কাছে পৌঁছায়নি। | transaction fail hoyeche | আমার ট্রানজেকশনটা failed হয়েছে, please check করুন। | ✅✅✅✅✅ | ❓✅✅ |
| 3.4 | List disputes | আমার আগের ডিসপিউটগুলোর স্ট্যাটাস কি? | dispute dekhaen | আমার গত সপ্তাহের transaction dispute status টা দেখান | ❌✅✅✅✅ | ✅✅✅ |
| 3.5 | Submit complaint | আপনার ব্রাঞ্চের স্টাফদের ব্যবহার খুবই খারাপ ছিল। | complaint korte chai | আমার ATM card টা নিয়ে অনেক problem হচ্ছে। | ✅✅✅✅❓ | ✅❓✅ |
| 3.6 | My complaints | আমি আগে যে অভিযোগগুলো দিয়েছিলাম সেগুলোর স্ট্যাটাস দেখতে চাই। | complaint dekha jacche? | আমার আগের complaint টা কি update হয়েছে? | ❓✅✅✅✅ | ✅✅✅ |

#### CARD_MANAGEMENT

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 4.1 | Freeze card | আমার কার্ডটা হারিয়ে গেছে, দয়া করে এটা এখনই ব্লক করে দিন। | card block koren | আমার card টা block করে দিন, আমি সেটা হারিয়ে ফেলেছি। | ✅❓✅❓✅ | ✅❓✅ |
| 4.2 | Unfreeze card | আমার ডেবিট কার্ডটি এখন ব্লক করা আছে, এটা কি আবার চালু করা যাবে? | card block koren | আমার card টা unblock করে দিন। | ✅✅❌✅✅ | ✅❓✅ |
| 4.3 | Close card | আমার এই কার্ডটি চিরতরে বন্ধ করে দিন। | card bond korun | আমার এই card টা cancel করে দিন। | ❌✅❌✅✅ | ❓✅✅ |
| 4.4 | Contactless on/off | আমার কার্ডের কন্ট্যাক্টলেস পেমেন্ট সুবিধাটা একটু বন্ধ করে দিন। | contactless bond korun | আমার card এর contactless payment অফ করে দিন। | ✅✅✅❓✅ | ✅❓❓ |
| 4.5 | International transaction on/off | আমার কার্ডের আন্তর্জাতিক লেনদেন বন্ধ করে দিন। | intl off koren | আমার card এর international transaction বন্ধ করতে চাই। | ✅✅❓✅✅ | ❓✅✅ |
| 4.6 | Reset card PIN | আমার কার্ডের পিন নম্বরটা আমি ভুলে গেছি, এটা কীভাবে রিসেট করবো? | card pin reset | আমার card এর PIN reset করতে চাই, please help করুন। | ✅✅✅✅✅ | ✅✅✅ |
| 4.7 | Limit change — submit | আমার ক্রেডিট কার্ডের লিমিট বাড়িয়ে দিন প্লিজ। | limit barhiye din | আমার card এর limit বাড়িয়ে দিন ২০,০০০ টাকা করে। | ❓✅✅✅✅ | ✅✅✅ |
| 4.8 | Limit change — list | আমি আগে যে লিমিট পরিবর্তনের রিকোয়েস্টগুলো দিয়েছি সেগুলো দেখতে চাই। | limit check koro | আমার limit change request এর status কি এখন? | ❌❌❌✅✅ | ❌✅✅ |
| 4.9 | Limit change — cancel | আমি যে কার্ডের লিমিট বাড়ানোর রিকোয়েস্ট দিয়েছিলাম সেটা বাতিল করে দিন। | limit change cancel koren | আমার card limit change request টি cancel করে দিন। | ✅✅✅✅✅ | ✅✅✅ |
| 4.10 | Card products list | আপনার ব্যাংকে কি কি ধরনের কার্ড আছে জানাবেন? | card list kicu? | আপনার bank এ কি কি card products আছে? | ❌✅❌✅✅ | ❓✅✅ |
| 4.11 | Apply for debit card | আমি নতুন একটি ডেবিট কার্ডের জন্য আবেদন করতে চাই। | card apply korte hobe | আমার অ্যাকাউন্টের জন্য একটা নতুন debit card apply করতে চাই। | ✅✅✅✅✅ | ✅✅✅ |
| 4.12 | Reveal debit card details | আমার ডেবিট কার্ডের কার্ড নম্বর আর সিভিভিটা একটু দেখান। | card details dekhau | আমার debit card এর details গুলো show করেন। | ❌❌❌❌❌ | ❓❌· |
| 4.13 | Apply for prepaid card | আমি একটি নতুন প্রিপেইড কার্ডের জন্য আবেদন করতে চাই। | prepaid card chai | আমি একটা নতুন prepaid card apply করতে চাই। | ✅✅✅✅✅ | ✅❓✅ |
| 4.14 | Reveal prepaid card details | আমার প্রি-পেইড কার্ডের ডিটেইলসগুলো একটু দেখাবেন কি? | card details dekhao | আমার prepaid card এর details গুলো একটু show করবেন? | ❌❌❌❌❌ | ❌❌· |
| 4.15 | Virtual card — submit | আমি একটি নতুন ভার্চুয়াল কার্ডের জন্য আবেদন করতে চাই। | virtual card lagbe | আমার জন্য একটি নতুন virtual card request করতে চাই। | ✅✅✅✅✅ | ✅✅✅ |
| 4.16 | Virtual card — list | আমার আবেদন করা ভার্চুয়াল কার্ডগুলোর স্ট্যাটাস কি? | virtual card list | আমার virtual card application এর status দেখুন। | ✅✅✅✅✅ | ✅✅❌ |
| 4.17 | Virtual card — cancel | আমার ভার্চুয়াল কার্ডটি দয়া করে বন্ধ করে দিন। | virtual card cancel koren | আমার virtual card টা cancel করে দিন। | ✅✅✅✅✅ | ✅✅✅ |
| 4.18 | Virtual card — reveal | আমার ভার্চুয়াল কার্ডের নম্বরটা একটু দেখাবেন কি? | card reveal koren | আমার virtual card এর CVV এবং expiry date দেখান। | ❌❌❌❌❌ | ❓❓· |
| 4.19 | Star card | আমার এই কার্ডটি কি হোম স্ক্রিনে পিন করা যাবে? | card ta star koro | আমার এই card টা quick view এ স্টার করুন | ❓❓❌❓❓ | ❓❓❌ |
| 4.20 | Credit card bill payment (card service) | আমার ক্রেডিট কার্ডের বকেয়া টাকা জমা দিতে চাই। | card bill pay korbo | আমার credit card এর bill payment কিভাবে করবো? | ❓✅✅✅✅ | ✅✅✅ |
| 4.21 | Credit card bill payment (bill service) | আমি অন্য ব্যাংকের ক্রেডিট কার্ডের বিল জমা দিতে চাই। | bill pay korte hobe | আমার অন্য ব্যাংকের credit card bill pay করতে চাই, card number হলো 1234। | ❌✅❓✅✅ | ✅✅✅ |
| 4.22 | QR payment cards — list | আমার কিউআর পেমেন্টের জন্য কোন কার্ডগুলো চালু আছে দেখতে চাই। | qr card list dekha | আমার QR payment cards এর list টা একটু দেখান। | ❓❌❌❌❌ | ❓❌❌ |
| 4.23 | QR payment card — enable/disable | আমার QR পেমেন্ট কার্ডের সেটিংস একটু দেখতে চাই। | QR card off koren | আমার QR payment card এর list টা দেখতে চাই। | ✅❓✅✅❌ | ❌❌✅ |

#### CARD_REPLACEMENT

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 5.1 | List replacement requests | আমি আগে যে কার্ড পরিবর্তনের রিকোয়েস্ট দিয়েছিলাম সেগুলোর অবস্থা কি? | card replacement status | আমার card replacement request গুলো check করতে চাই। | ✅✅✅✅✅ | ✅✅✅ |
| 5.2 | Cancel replacement request | আমি কার্ড পরিবর্তনের জন্য যে রিকোয়েস্ট দিয়েছিলাম সেটা বাতিল করে দিন। | replacement cancel koren | আমার card replacement request টা cancel করে দিন। | ✅✅❌✅✅ | ❌✅✅ |
| 5.3 | Reveal replacement card details | আমার নতুন রিপ্লেসমেন্ট কার্ডের ডিটেইলস একটু দেখাবেন? | card details dekhao | আমার নতুন card এর expiry date আর CVV টা দেখান। | ❌❌❌❌❌ | ❓❓· |

#### EDIT_PERSONAL_DETAILS

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 7.1 | Get profile | আমার অ্যাকাউন্টের প্রোফাইল ডিটেইলসগুলো একটু দেখাবেন কি? | profile dekhao | আমার profile details গুলো একটু চেক করে দিন। | ✅✅✅✅✅ | ❓✅✅ |
| 7.2 | Update nickname | আমার অ্যাপের ডিসপ্লে নামটা একটু বদলে দিতে চান। | nickname change koren | আমার nickname টা change করে দিন প্লিজ। | ❓✅✅✅✅ | ✅✅✅ |
| 7.3/7.4 | Upload profile image | আমি আমার প্রোফাইল পিকচারটা পরিবর্তন করতে চাই। | photo change koren | আমার profile picture টা change করার অপশন কোথায়? | ✅✅✅✅✅ | ✅✅✅ |
| 7.5 | Update mobile number | আমি আমার অ্যাকাউন্টে নতুন মোবাইল নম্বর যোগ করতে চাই। | number change koren | আমার registered mobile number change করার জন্য কী করতে হবে? | ✅✅✅✅✅ | ✅✅✅ |
| 7.6 | Update email address | আমার প্রোফাইলে থাকা ইমেইল অ্যাড্রেসটা পরিবর্তন করে দিন। | email change koren | আমার প্রোফাইলে নতুন email address আপডেট করে দিন। | ✅✅✅✅✅ | ✅✅✅ |
| 7.7 | Get address | আমার অ্যাকাউন্টে কোন ঠিকানা দেওয়া আছে সেটা একটু দেখুন তো। | amar address ki | আমার registered address টা কি আপডেট করা আছে? | ✅✅✅✅✅ | ❌✅❌ |
| 7.8 | Update address | আমার বর্তমান ঠিকানাটা পরিবর্তন করে দিতে পারবেন? | address change koren | আমার permanent address change করার জন্য process টা বলুন। | ✅✅✅✅✅ | ✅✅✅ |
| 7.9 | Submit KYC | আমার এনআইডি কার্ড এবং ছবি জমা দিতে চাই। | KYC update korbo | আমার KYC update করার জন্য NID photo জমা দিব। | ✅✅✅✅✅ | ✅❓✅ |
| 7.10 | My contacts | আমার অ্যাকাউন্টে কোন কোন ফোন নাম্বার আর ইমেইল আছে তা দেখুন। | contact list kothay | আমার registered phone number এবং email address গুলো দেখান। | ✅✅❓✅✅ | ✅✅✅ |
| 7.11 | Profile change — submit | আমার এনআইডি নম্বরটি আপডেট করে দিন। | phone number change | আমার প্রোফাইলে mobile number change করতে চাই। | ❓✅❌❌❌ | ✅❌❌ |
| 7.12 | Profile change — list | আমার আগের প্রোফাইল পরিবর্তনের রিকোয়েস্টগুলোর স্ট্যাটাস দেখতে চাই। | profile change list | আমার profile change request এর status দেখতে চাই। | ❓✅❓✅✅ | ✅✅✅ |
| 7.13 | Contact priority — submit | আমার প্রাইমারি ফোন নম্বরটা পরিবর্তন করে দিতে চাই। | number change koren | আমার registered mobile number টা change করতে চাই। | ❌✅❌✅❌ | ❓❌❓ |
| 7.14 | Contact priority — list | আমার প্রাইমারি কন্টাক্ট পরিবর্তনের রিকোয়েস্টগুলো এখন কী অবস্থা? | request status dekhan | আমার contact change request এর status কি দেখাবেন? | ❓✅❓✅✅ | ✅✅✅ |

#### FAILED_TRANSFER

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 8.1 | Transaction history | গত মাসের সব ট্রানজ্যাকশন দেখতে চাই। | statement dekhaite hobe | আমার গত সপ্তাহের transactions গুলো দেখতে চাই। | ✅✅✅✅✅ | ✅✅✅ |
| 8.2 | Raise dispute | আমি বিকাশ থেকে টাকা পাঠালাম কিন্তু এখনো টাকাটা পৌঁছায়নি। | transaction fail hoyeche | আমার account থেকে টাকা কেটে গেছে কিন্তু transaction failed দেখাচ্ছে। | ✅✅✅✅✅ | ✅✅✅ |
| 8.3 | List disputes | আমার আগের সব ট্রানজ্যাকশন ডিসপিউটগুলো দেখতে চাই। | dispute list dekhao | আমার গত সপ্তাহের transaction dispute এর status কি? | ❌✅✅✅✅ | ✅✅✅ |
| 8.4 | Submit complaint | আপনার ব্রাঞ্চের স্টাফদের ব্যবহার খুবই খারাপ ছিল। | complaint korte chai | আমার debit card টা কাজ করছে না, please check করুন। | ✅✅✅❓❓ | ✅❓❌ |
| 8.5 | My complaints | আমি আগে যে অভিযোগগুলো দিয়েছিলাম সেগুলো দেখতে চাই। | complaint status ki? | আমার আগের complaints গুলো কি status আছে? | ✅✅❓✅✅ | ✅✅✅ |

#### FEES

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 10.1 | Transaction charge quote | অন্য ব্যাংকে টাকা পাঠালে কত চার্জ কাটবে? | charge koto? | অন্য bank e transfer korle charge koto? | ❓✅❓✅✅ | ✅✅✅ |

#### MINI_STATEMENT

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 13.1 | Transaction list | আমার গত মাসের সব লেনদেনের স্টেটমেন্টটা দেখতে চাই। | transaction list dekhaon | আমার গত সপ্তাহের সব transactions দেখতে চাই। | ✅✅✅✅✅ | ✅✅✅ |
| 13.2 | Account transactions | গত মাসের সব ট্রানজেকশন লিস্টটা দেখতে চাই। | transaction dekhao | আমার account এর গত সপ্তাহের সব transaction history দিন। | ✅✅✅✅✅ | ✅✅✅ |
| 13.3 | Credit card statement | আমার গত মাসের ক্রেডিট কার্ডের স্টেটমেন্টটা দেখতে চাই। | card statement dekhau | আমার credit card statement টা দেখতে চাই জানুয়ারি মাসের। | ✅✅✅✅✅ | ✅✅✅ |

#### TRANSFER

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
| 14.1 | Own account transfer | আমার অন্য একাউন্টে ৫০০ টাকা পাঠিয়ে দিন। | transfer koren 2000 | আমার অন্য account এ 1000 টাকা transfer করে দিন। | ❓✅❓✅✅ | ✅❓✅ |
| 14.2 | City Bank transfer | আমার নিজের অন্য একাউন্টে ৫০০০ টাকা পাঠিয়ে দিন। | city bank transfer koren | আমার অন্য account এ 1000 taka transfer করেন। | ❌❌✅✅❌ | ❌❌✅ |
| 14.3 | Other bank transfer | আমি আমার বন্ধুকে ডাচ-বাংলা ব্যাংকে ৫০০০ টাকা পাঠাতে চাই। | duit pathate hobe | আমার brother এর account এ ২,০০০ টাকা transfer করে দিন। | ✅✅❓❓❓ | ✅✅❌ |
| 14.4 | Other banks list | আমি অন্য কোন কোন ব্যাংকে টাকা পাঠাতে পারি তা দেখতে চাই। | onno bank list | আমি অন্য banks এর list দেখতে চাই। | ✅✅✅✅✅ | ❓❓✅ |
| 14.5 | Gift transfer | আমার বন্ধুর জন্য একটা উইশ মেসেজসহ গিফট পাঠাতে চাই। | gift pathate hobe? | আমি আমার sister কে একটা gift transfer করতে চাই 1000 টাকা দিয়ে। | ❓✅❓✅✅ | ✅❓❌ |
| 14.6 | Gifts received | আমার অ্যাকাউন্টে এখন পর্যন্ত কী কী গিফট এসেছে তা দেখতে চাই। | gift gulo dekhau | আমার সব gifts গুলো দেখতে চাই, please help করেন। | ✅✅✅✅✅ | ✅✅✅ |
| 14.7 | Generic transaction | আমার একাউন্টে ৫০০ টাকা পাঠিয়ে দিন। | taka pathan | আমার account এ ৫০০ টাকা transfer করে দিন। | ✅❌✅❌❌ | ❌✅❌ |
| 14.9 | Email transfer — create | আমি আমার বন্ধুকে ইমেইল দিয়ে টাকা পাঠাতে চাই। | email diye pathan | আমি ইমেইল দিয়ে ১০০ টাকা transfer করবো। | ✅✅✅✅✅ | ✅✅❓ |
| 14.10 | Email transfer — list | আমি আমার আগের ইমেইল ট্রান্সফারগুলোর লিস্ট দেখতে চাই। | email transfer list dekha | আমার গত মাসের email transfer list টা দেখান। | ✅✅✅✅✅ | ✅✅✅ |
| 14.11 | Email transfer — details | আমি গত সপ্তাহে যে ইমেইল ট্রান্সফারগুলো করেছি সেগুলোর ডিটেইলস দেখতে চাই। | email transfer dekhao | আমার গত মাসের email transfers এর status দেখতে চাই। | ✅✅✅✅✅ | ✅✅✅ |
| 14.12 | Email transfer — cancel | আমার ইমেইল ট্রান্সফারটা কি বাতিল করা যাবে? | transfer cancel koren | আমার ৫০০০ টাকার email transfer টা cancel করে দিন | ❓✅❓✅✅ | ✅❓✅ |
| 14.13 | Email transfer — resend | আমার ট্র্যান্সফার কনফার্মেশন ইমেইলটা আবার পাঠাবেন কি? | email abar pathan | আমার transfer confirmation mail টা আবার পাঠান। | ❓❌❓❌❌ | ❓❓✅ |
| 14.14 | Wallet/MFS transfer | আমার বিকাশ অ্যাকাউন্টে ৫০০ টাকা পাঠিয়ে দিন। | bkash transfer koren | আমার Nagad এ ৫০০ টাকা transfer করে দিন। | ✅✅✅✅✅ | ❌✅✅ |
| 14.16 | QR pay | আমি কি কিউআর কোড স্ক্যান করে পেমেন্ট করতে পারি? | qr pay kivabe? | আমি QR code scan করে payment কিভাবে করবো? | ❓❓❓✅✅ | ❌❓✅ |
| 14.17 | QR parse | আমি কি কিউআর কোড স্ক্যান করে টাকা পাঠাতে পারি? | qr scan korbo | আমি কি QR code scan করে payment করতে পারবো? | ❓❓✅✅❓ | ❓❓❓ |
| 14.18 | QR payment history | আমি গত সপ্তাহে কতগুলো QR পেমেন্ট করেছি তা দেখতে চাই। | QR payment history | আমার গত মাসের QR payment history টা দেখতে চাই। | ✅✅✅✅✅ | ❌❌✅ |
| 14.19 | Beneficiary — list | আমার সেভ করা বেনিফিশিয়ারিদের তালিকাটা একটু দেখান। | beneficiary list dekhao | আমার saved beneficiary list টা একটু দেখাবেন? | ✅✅✅✅✅ | ❓❓✅ |
| 14.20 | Beneficiary — add | আমি নতুন একজন বেনিফিশিয়ারি সেভ করতে চাই। | beneficiary add korte hobe | আমি নতুন beneficiary add করার process টা বলতে পারেন? | ✅✅✅✅✅ | ✅✅✅ |
| 14.21 | Beneficiary — edit | আমি আমার সেভ করা বেনিফিশিয়ারির নামটা একটু এডিট করতে চাই। | beneficiary edit koren | আমার saved beneficiary এর নামটা edit করতে চাই। | ✅✅✅✅✅ | ✅❓✅ |
| 14.22 | Beneficiary — delete | আমার সেভ করা বেনিফিশিয়ারি লিস্ট থেকে নামটা বাদ দিন। | beneficiary delete koren | আমার beneficiary list থেকে বিকাশ নাম্বারটা delete করে দিন। | ✅✅✅✅✅ | ❌❓❓ |
| 14.23 | Beneficiary — upload/change photo | আমি আমার সেভ করা বেনিফিশিয়ারি এর ছবিটা পাল্টাতে চাই। | photo change koren | আমি beneficiary এর photo টা change করতে চাই। | ❌✅❌✅✅ | ❌❌✅ |
| 14.24 | Beneficiary — remove photo | আমার সেভ করা বেিনিফিচারি থেকে ছবিটা সরিয়ে দিন। | photo remove koren | বেিনিফিচারি থেকে photo টা remove করে দিন। | ❓✅❓✅✅ | ❓❌✅ |
| 14.25 | Beneficiary — pin/unpin | আমি আমার পছন্দের ব্যক্তিকে লিস্টের উপরে পিন করতে চাই। | beneficiary pin korbo | আমার favorite beneficiary টা pin করার অপশন কোথায়? | ✅✅✅❌✅ | ✅❌✅ |
| 14.27 | My transfer limit — get | আমার ট্রান্সফার লিমিট কতটুকু তা একটু জানান। | transfer limit koto? | আমার transfer limit কত সেটা একটু check করেন। | ✅✅✅✅✅ | ✅✅✅ |
| 14.28 | My transfer limit — request change | আমার ট্রান্সফার লিমিটটা একটু বাড়িয়ে দেওয়ার ব্যবস্থা করবেন কি? | limit bariye din | আমার transfer limit টা একটু increase করবেন? | ❌✅❌✅✅ | ❌✅✅ |
| 14.29 | My transfer limit — cancel pending change | আমি যে লিমিট পরিবর্তনের রিকোয়েস্ট দিয়েছিলাম সেটা বাতিল করে দিন। | limit change cancel | আমার transfer limit change request টা cancel করে দিন। | ❌❌❌✅✅ | ✅✅✅ |

#### GREETING

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
|  | Greeting and small talk | আপনার সাথে কথা বলে খুব ভালো লাগলো, ধন্যবাদ। | thanks re | আমার account check করার জন্য thanks. | ✅✅✅✅✅ | ✅✅❌ |

#### FALLBACK

| # | Use case | Bangla | Banglish | Mixed | Typed | Spoken |
|---|---|---|---|---|---|---|
|  | General bank knowledge and off-topic | আপনার এখানে কি কোনো লোন পাওয়া যাবে? | khobor ki? | আপনার এখানে কি কোনো personal loan পাওয়া যাবে? | ✅✅✅❌✅ | ✅❌✅ |

## Requests that are not covered

- **1.3 Get account by account/card number** and **1.4 Get accounts by username**: only used during sign-up and device verification, not a customer request in chat.
- **14.7 Generic transaction**, **14.8 Linked account check**: background steps of the app, not something a customer asks for.
- **14.15 Wallet verify** and **14.26 Recipient lookup by account number**: not built.
- **Card detail reveal** (4.12, 4.14, 4.18, 5.3): the bot never shows full card numbers or CVV in chat; it tells the customer to use the app.
- Everything the bank has no backend for is listed as "Not available" above.

## What would raise these numbers

1. A clean full re-run on a stable bank (the latest run lost 90 questions to bank outages).
2. Letting the target screens read the prefilled fields, so app actions open already filled in.
3. Fixing the greeting wording and reply speed noted above.

_Generated from `experiments/results/dynamic/` (single-turn suite). Multi-turn testing across the 14 intents has not been run yet, so long conversations where a customer changes topic are not covered by these numbers._