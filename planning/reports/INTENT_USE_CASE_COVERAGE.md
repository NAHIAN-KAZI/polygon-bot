# Intent use-case coverage — what the bot can and cannot do

Status as of 2026-10-07. This is the T-80 report. It covers the bank's 14 intents and every use case in `planning/input/INTENT_IMPLEMENTATION_STATUS.md` that is a real chatbot request.

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