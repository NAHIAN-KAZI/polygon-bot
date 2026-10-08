# Test messages, use case by use case

What to type for every use case, and what to expect. Each use case has 5–10 messages of different types (one word, two words, slang or typos, a full sentence, a long story, with details, without details, vague, follow-up answers, and look-alikes that must **not** trigger it).

**How to read it**
- **Send** is what the tester types, or the button answer the app sends (message + payload, `handoffs/COMMON.md` §5).
- **Expect** is the gist. The bubble wording is written by the model and changes every time, so judge the bubble by meaning, and judge the UI only by `result.type`, `category`, `service`, `routing` and `payload`.
- "May ask a clarifying question first" means a short or vague message can get a question before the real step. Answer it and continue; that is not a failure.
- English only.
- Test customer `taslim_islamic`: one savings account ending 0056 (Tk 90,000), one active debit card ending 0293, no credit card, no loans, and empty lists for disputes, complaints, requests, gifts, email transfers, QR history and beneficiaries.
- Nothing here moves money. Transfers and disputes are never executed by the bot. The freeze and the nickname, address, email, mobile, complaint and beneficiary changes are the only changes the bot makes, each after a yes or a code, and they really change the account. Undo them outside the chat afterwards (unfreeze, set the old value back).
- Expectations come from the handoffs and the code, not from a fresh live run.

---

## ACCOUNT_INFO

Test customer facts used below: one savings account ending 0056 (ledger balance Tk 90,000.00), one active debit card ending 0293, no loans, 2 enrolled devices, 3 recent logins. Account numbers show masked (••••0056). Show the ledger balance, not the core record's `balance` (which is `0.00`).

### 1.1 Get all accounts
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `account_info/accounts`
**UI to show:** U3/U2 account cards, one card for savings ••••0056 with ledger balance ৳90,000.00 (`ledgerAccounts[].balanceFormatted`). No buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `accounts` | Bubble: you have one savings account, Tk 90,000. Account card. |
| 2 | two words | `my accounts` | Same answer and card. |
| 3 | casual / typos | `hey whats my accs like? how mny acount i hav` | Same answer. The heavy typo may be read as a balance ask (known gap), but the bubble still states the single account and balance. |
| 4 | full sentence | `Can you please list all of my bank accounts?` | Same answer and card. |
| 5 | long story | `I'm trying to get my finances in order for the new year. I think I might have a salary account and a savings account with this bank, plus maybe an old one. Could you help me see every account I hold with you so I get a clear picture?` | Same answer: only one account (savings ••••0056). Does not invent extra accounts. |
| 6 | with details | `show all my accounts including the savings one ending 0056` | Same list; the number is not needed and gives no extra filter. |
| 7 | vague | `what do I have with you` | May ask a clarifying question first; if it answers, it lists the account. |
| 8 | similar, different use case | `what is my balance` | NOT this one: `account_info/balance` answer (Tk 90,000), balance detail card, no account list. |

### 1.2 Get account detail
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `account_info/accounts` (with `id` when one is named)
**UI to show:** U3 detail card of the one account (ledger balance rule, masked number). No buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `details` | May ask which details (account, card, profile) first. |
| 2 | two words | `account details` | One account, so it is picked automatically: detail card for savings ••••0056, Tk 90,000. |
| 3 | casual / typos | `hey i want my acc details pls lol` | Same detail card. |
| 4 | full sentence | `Please show me the details of my savings account.` | Detail card: account type SAVINGS, branch, masked number, ledger balance. |
| 5 | long story | `I'm filling in a form and need to double check my account type, which branch it is with and the account name. Can you pull up the details of my account for me?` | Detail card with name, type, branch (banani), masked number, balance. |
| 6 | with details | `show details of account ending 0056` | Detail card for ••••0056. |
| 7 | follow-up | `which account is the Islamic one` (after 1.1) | Answered from the single account (bankingMode ISLAMIC); same detail card. |
| 8 | similar, different use case | `show my last transactions on this account` | NOT this one: transaction list (`polygon_services/transaction_history`, U4). |

### 1.3 Account by account/card number
**Outcome:** not offered  ·  **Result:** bubble only (no `account_info` service; may be a clarifying question or a polite "can't do that here")
**UI to show:** Bubble only, no box, no chips.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | two words | `find account` | Bubble only, nothing is looked up. |
| 2 | casual | `whose acc is 100126000056 lol` | Bubble only; no lookup by number, no box. |
| 3 | full sentence | `Can you look up an account using its account number?` | Bubble only: this is not available in chat. |
| 4 | with details | `Find the account that belongs to card 4001 1234 5678 0293` | Bubble only. Full card number is never echoed. |
| 5 | long story | `I'm signing up on a new phone and the app says it needs to find my account from my card number. I have the card in front of me, can you find the account linked to it?` | Bubble only; no box. |

### 1.4 Accounts by username
**Outcome:** not offered  ·  **Result:** bubble only
**UI to show:** Bubble only, no box, no chips.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | two words | `find username` | Bubble only. |
| 2 | casual | `show accs for user taslim_islamic pls` | Bubble only; no lookup by username. |
| 3 | full sentence | `Can you list the accounts linked to my username?` | Bubble only (not a chat service). It must not return the account list as if it were 1.1. |
| 4 | with details | `accounts for username taslim_islamic` | Bubble only. |
| 5 | long story | `My phone is new and the app is asking me to verify the device. I only remember my username. Can you show me the accounts attached to that username so I can pick mine?` | Bubble only; no box. |

### 1.5 Star account
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/quick_view_star` (`routing.action: "quick_view_star"`, `ui.kind: screen`, `CustomizeQuickViewScreen`, `/customize_quick_view`). No bank call by the bot.
**UI to show:** U8 box: your accounts and cards, each with a star switch; the one named in the message starts switched on (no prefill fields in the registry, so the box decides). No other buttons. The app does the call and shows a done/failed tile.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `star` | Likely the star box; may ask first what to star. |
| 2 | two words | `star account` | Bubble says you can pick what to star; star box with account ••••0056 and card ••••0293. |
| 3 | casual / typos | `pls put my savings acc on the home screen as fav lol` | Star box, account ••••0056 starred on. |
| 4 | full sentence | `Please star my savings account so it shows on my home quick view.` | Star box, ••••0056 switched on. |
| 5 | long story | `I open the app every morning just to check one account, and it is annoying that I have to scroll. Can I pin my savings account to the top of the home screen so I see the balance straight away?` | Star box with the account switch on. |
| 6 | card variant | `favourite my debit card ending 0293` | Same `quick_view_star` action (it covers cards too); card ••••0293 switched on. |
| 7 | vague | `make it a favourite` | May ask which account or card first; then the box. |
| 8 | similar, different use case | `show my accounts` | NOT this one: `accounts` list answer (1.1), account card, no star switches. |

### 1.6 My loans
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `loan_services/my_loans` (`payload.loans = []`)
**UI to show:** Bubble only: the list is empty, so no U2 card ("no loans" is the normal answer, not an error). No buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `loans` | Bubble: you have no loans. No card. |
| 2 | two words | `my loans` | Same. |
| 3 | casual / typos | `can u plz send me my loan info lol thx` | Same "no loans". |
| 4 | full sentence | `I'd like to view an overview of all my current loans, please.` | Same "no loans". |
| 5 | long story | `I took out a car loan last year and I think there is a smaller personal loan too. I want to see how much I still owe and when the next installment is due. Could you show me where I stand on my loans?` | "No loans" for this customer; does not invent any. |
| 6 | with details | `show my home loan of 2000000 taka` | Same: lists loans, none exist. Does not create or look up a specific loan. |
| 7 | vague | `do I owe you anything` | May ask a clarifying question first; if it answers, "no loans". |
| 8 | similar, different use case | `I want to apply for a personal loan` | NOT my_loans: no loan list. Expect a product answer or a clarifying question (no box). |

### 1.7 FD profit history
**Outcome:** answered in chat  ·  **Result:** for this customer `SERVICE_UNAVAILABLE` `account_info/fd_profit_history` (the bank returns 404 for the test customer's FD record; known gap). With a real FD: `BANKING_SERVICE` with profit entries.
**UI to show:** U10 retry notice on `SERVICE_UNAVAILABLE` (the handoff also says the bubble alone is the normal answer here). With a real FD: U2 FD profit list. If several FDs: `ACCOUNT_SELECTION_REQUIRED` ledger picker, send `Selected` + `{"identifier": ...}`.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `profit` | May ask FD or DPS first; then as below. |
| 2 | two words | `fd profit` | `SERVICE_UNAVAILABLE`: bubble says it could not fetch FD profit; retry notice. |
| 3 | casual / typos | `wanna see my fd intrest calc` | Same as #2. |
| 4 | full sentence | `Can you please show me the profit history of my FD?` | Same as #2. |
| 5 | long story | `I put Tk 50,000 into a fixed deposit last January and it is about to mature. Before I decide to renew, I want to see how much profit has been credited so far.` | Same as #2 (no invented figures). |
| 6 | with details | `show profit for my 50000 taka FD` | Same as #2; the amount is not used to filter. |
| 7 | vague | `how much did my deposit earn` | May ask which deposit (FD or DPS) first. |
| 8 | similar, different use case | `what is the current FD interest rate` | NOT this one: product/rate question, `KB_ANSWER`-type bubble, no profit list. |

### 1.8 DPS profit history
**Outcome:** answered in chat  ·  **Result:** `account_info/dps_profit_history`; for the test customer expect `SERVICE_UNAVAILABLE` like 1.7 (same 404 gap, not live-verified with a real DPS). With a real DPS: `BANKING_SERVICE` profit entries.
**UI to show:** U10 on `SERVICE_UNAVAILABLE`; with data U2 DPS profit list. Several DPS: ledger picker (`Selected` + `{"identifier": ...}`).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `dps` | May ask what about DPS first; then as below. |
| 2 | two words | `DPS profit` | `SERVICE_UNAVAILABLE` retry notice (same as 1.7). |
| 3 | casual / typos | `can u pls send me dps profit hstory from january?` | Same; the date range is not applied. |
| 4 | full sentence | `I need to know how much profit I earned on my DPS savings scheme.` | Same. |
| 5 | long story | `I have been paying a monthly DPS installment for about three years. I haven't checked it in a while and think I might have missed some interest. Can you show me the profit history for the past year?` | Same; no invented numbers. |
| 6 | with details | `how much profit did my 5000 taka monthly dps make` | Same; amount is not used to filter. |
| 7 | follow-up | `Retry` (the retry notice resends the last message) | Same `SERVICE_UNAVAILABLE` again for this customer. |
| 8 | similar, different use case | `how do I open a DPS` | NOT this one: product answer (`KB_ANSWER`) or app info, no profit list. |

### — Cards list
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `account_info/cards`
**UI to show:** U2 card tiles: DEBIT, ••••0293, ACTIVE (starred false). No buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `cards` | Bubble: one active debit card ending 0293. Card tile. |
| 2 | two words | `my cards` | Same. |
| 3 | casual / typos | `my crads` | Same (typo tolerated). |
| 4 | full sentence | `Can you show me all the cards linked to my account?` | Same. |
| 5 | long story | `I got a new wallet and want to know exactly which cards I should carry. How many cards do I have with the bank, and what type are they, debit or credit?` | One debit card ending 0293; no credit card. |
| 6 | with details | `do I have a credit card` | Answer: no credit card, only the debit card ending 0293. |
| 7 | vague | `what plastic do I have` | May ask a clarifying question first; otherwise the cards list. |
| 8 | similar, different use case | `block my card` | NOT this one: freeze flow, `CONFIRMATION_REQUIRED` `card_services/frezz_unfrezz` (card ending 0293), then the code sheet. |

### — One account's transactions
**Outcome:** answered in chat (direct route only; chat phrasing normally goes to MINI_STATEMENT's `transaction_history`)  ·  **Result:** `BANKING_SERVICE` `account_info/account_transactions`
**UI to show:** U4 transaction list (amounts are poisha: 500000 shows as ৳5,000). With several accounts U5 picker first; this customer has one so no picker.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | direct route | `show` with `category: account_info`, `service: account_transactions` | Transaction list for ••••0056, 3 transactions including a ৳5,000 bKash debit. |
| 2 | direct route, with details | `show` + `account_transactions` + payload `{"accountNumber": "<as received>"}` | Same list for that account. |
| 3 | typed, one word | `transactions` | Normally answered by `polygon_services/transaction_history` (MINI_STATEMENT), U4 list; this is not the `account_transactions` route. |
| 4 | typed, sentence | `show me the transactions on my savings account` | Same as #3: U4 list, the 3 transactions. |
| 5 | typed, casual | `wat did i spend lately` | Same as #3, or may ask a clarifying question first. |

### — Enrolled devices (extra, `account_info/device_history`)
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `account_info/device_history`
**UI to show:** U2 device list (name, platform, last used). No buttons. Not a row in the UI table, so a plain list is fine.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `devices` | Bubble: 2 enrolled devices (e.g. an Android phone). |
| 2 | two words | `my devices` | Same. |
| 3 | casual | `which phones r logged in on my acc` | Same list. |
| 4 | full sentence | `Can you show me which devices are registered to my account?` | Same list. |
| 5 | long story | `I lost my old phone last week and I am worried someone could still use my banking app on it. Can you show me every device that is enrolled to my account and when it was last used?` | Same list with last-used times. |

### — Login history (extra, `account_info/login_history`)
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `account_info/login_history`
**UI to show:** U2 login timeline (time, device, IP, status). No buttons, no device id needed.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `logins` | Bubble: recent logins across both devices (3 records, newest first). |
| 2 | two words | `login history` | Same. |
| 3 | casual | `who logged into my acc lately` | Same. |
| 4 | full sentence | `Where was my account logged in from recently?` | Same. |
| 5 | long story | `Hi, I got a weird notification yesterday and I'm worried someone else is using my account. Can you show me where my account was logged in from recently?` | Same: 3 logins with device and IP; none flagged as risky unless the data says so. |

## ATM_SUPPORT

### 2.1 Cash by code
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/cash_by_code` (`routing.action: "cash_by_code"`, `CashByCodeScreen`, `/cash_by_code`). No bank call by the bot.
**UI to show:** U8 box: form with account (from) ••••0056, recipient mobile, amount, code delivery (screen, SMS or email), note. Prefilled only with what was typed (`amount` in taka, `recipientMobile`). Button **Send**, then U7 (code + transaction PIN), then a done/failed tile.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Cash` | May ask a clarifying question first (short asks often do). |
| 2 | two words | `cash code` | Cash-by-code box, empty fields, or a clarifying question first. |
| 3 | casual / typos | `can i withdraw 500 taka using rocket via code` | `APP_ACTION` `cash_by_code`, box with amount 500 prefilled (live-tested). |
| 4 | full sentence | `I want to send cash by code to my brother so he can collect it.` | `cash_by_code` box, no amount or mobile prefilled; fields empty, account picker available. |
| 5 | long story | `My sister is arriving from abroad tomorrow and I want her to be able to pick up some cash locally. She has no bank account here. Can you help me set up a cash by code for 3000 taka to her mobile 01712345678?` | Box with amount 3000 and recipient mobile 01712345678 prefilled (both editable). |
| 6 | with details | `send cash code of 1500 to 01811223344` | Box with amount 1500 and mobile 01811223344. |
| 7 | vague | `I need cash but no card` | May ask a clarifying question first; if the request is understood, the cash-by-code box. |
| 8 | box validation | In the box, type mobile `1234` and amount `0` | Send stays blocked with field errors (mobile must be 11 digits starting 01; amount must be positive). |
| 9 | similar, different use case | `send 500 taka to bKash 01712345678` | NOT this one: a wallet transfer summary (`routing.action: bkash_transfer`), transfer box, not the cash-by-code box. |
| 10 | similar, different use case | `ATM took my money but no cash came out` | NOT this one: `raise_dispute` gathering (see 2.2). |

### 2.2 Raise dispute
**Outcome:** gather → inline box (the bot never submits)  ·  **Result:** while gathering `CLARIFICATION_REQUIRED` (with `payload.pending.service == "raise_dispute"`, missing `remarks`) or `TRANSACTION_SELECTION_REQUIRED`; final `BANKING_SERVICE` `service_requests/raise_dispute`, `executed: false`, `routing.action: "raise_dispute"`.
**UI to show:** U5 transaction picker if no clear match, then U8 dispute box: account ••••0056 and transaction prefilled, reason text, button **Submit dispute**, then U7 (code). Box shows when `pending.service == "raise_dispute"` or the summary arrives. One account only, so no account picker.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Problem` | Clarifying question: what happened? No box needed yet. |
| 2 | two words | `Transaction failed` | Gathering: may ask what went wrong or show the transaction picker (3 transactions). |
| 3 | casual / typos | `hey atm didnt give cash but my acc got charged, fix pls` | Gathering started: dispute box or a picker for which transaction. |
| 4 | full sentence | `ATM took my card money but no cash came out.` | Gathering: picker `TRANSACTION_SELECTION_REQUIRED` (recent transactions) or a question for what went wrong; live-tested. |
| 5 | long story | `Last night I went to an ATM to withdraw 5000 taka. The machine whirred and then said "transaction failed" but I got no cash. This morning I saw the 5,000 deducted from my account. I want to raise a dispute.` | Summary: account ••••0056, a matching transaction picked (the 5,000 debit) or picker if unclear, remarks in your words, `executed: false`; dispute box prefilled. |
| 6 | with details | `raise a dispute for the 5000 bKash debit, the money was deducted but the receiver never got it` | Matches the 5,000 bKash transaction, summary with `transactionReferenceNo` and `remarks`; dispute box prefilled. |
| 7 | without details | `i want to raise a dispute` | Gathering: asks which transaction (picker) and/or what went wrong; dispute box with empty reason. |
| 8 | vague | `something is wrong with my money` | Clarifying question first; no box. |
| 9 | follow-up (button) | After a transaction picker, tap a row: app sends `Selected` + `{"transactionId": <transactionId>}` (no `category`/`service`) | Next: asks what went wrong (`CLARIFICATION_REQUIRED`, pending `raise_dispute`) or, if remarks were already given, the summary. |
| 10 | follow-up (typed) | `the money was cut but I never got the cash` (after the question) | Final `BANKING_SERVICE` summary, `executed: false`, `remarks` = your words; dispute box prefilled; bubble says to submit it in the box. |
| 11 | similar, different use case | `show my disputes` | NOT this one: `disputes` list (2.3), "no disputes" bubble. |

### 2.3 List disputes
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `service_requests/disputes` (`payload.disputes = []`)
**UI to show:** Bubble only: "no open disputes" (empty list, no U2 card). No buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Disputes` | Bubble: you have no disputes. |
| 2 | two words | `my disputes` | Same. |
| 3 | casual / typos | `any open disputs?` | Same. |
| 4 | full sentence | `Can you please show me the status of my dispute?` | Same. |
| 5 | long story | `I made a payment through bKash on the 10th but the receiver never got it, and I contacted the bank about it. Can you list all my transaction disputes with their status so I know where it stands?` | Same "no disputes"; it does not create one. |
| 6 | with details | `status of my dispute for the 5000 taka bKash payment` | Same list answer: no disputes found. |
| 7 | vague | `any update on my problem` | May ask which problem (dispute or complaint) first. |
| 8 | similar, different use case | `i want to raise a dispute for a missing transaction` | NOT this one: `raise_dispute` gathering (2.2). |

## CARD_ISSUE

### 3.1 Reset card PIN
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_pin_reset` (`routing.action: "card_pin_reset"`, `SelectCardForPinResetScreen`, `/set_reset_card_pin`). No bank call by the bot.
**UI to show:** U8 box: card (preselected from `cardLast4`, otherwise the card picker; this customer has the debit card ••••0293) with button **Reset PIN**, then U7 (code + PIN or password), then done/failed tile.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Reset` | May ask what to reset first. |
| 2 | two words | `reset pin` | `card_pin_reset` box, card ••••0293 (single card). |
| 3 | casual / typos | `can u pls reset my card pin?` | `APP_ACTION` `card_pin_reset` (live-tested). |
| 4 | full sentence | `I forgot my card PIN, can you please help me reset it?` | Same box. |
| 5 | long story | `I've been trying to remember my debit card PIN for an hour. I need to pay a bill online and the app keeps rejecting it. I'm afraid of getting it locked. Please help me set a new PIN.` | Same box. |
| 6 | with details | `reset the pin of my card ending 0293` | Box with card ••••0293 preselected (`cardLast4: 0293`). |
| 7 | without details | `I want a new pin for my card` | Box with the card picker or only card (no `cardLast4` prefill if not typed). |
| 8 | vague | `my pin` | May ask whether you want to reset or change it first. |
| 9 | similar, different use case | `my card isnt working` | NOT this one: clarifying question asking what is happening, no service called, no box. |
| 10 | similar, different use case | `my card was stolen, block it` | NOT this one: freeze flow (`frezz_unfrezz` confirm) or report-lost redirect (`LOST_OR_STOLEN_CARD`). |

### 3.2 Unfreeze card
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_unfreeze` (`routing.action: "card_unfreeze"`, `FreezeCardScreen`, `/freeze_card`). No bank call by the bot.
**UI to show:** U8 box: frozen cards, each with **Unfreeze** (preselected from `cardLast4`), then U7 (code + PIN or password), then done/failed tile. The test card ••••0293 is ACTIVE, so the list of frozen cards may be empty; the box still appears.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Unfreeze` | `card_unfreeze` box, or a short question about which card. |
| 2 | two words | `unblock card` | `card_unfreeze` box. |
| 3 | casual / typos | `hey unfreeze my card pls its still not working` | `APP_ACTION` `card_unfreeze`. |
| 4 | full sentence | `Can you please unfreeze my card? It has been blocked since last night.` | Same (live-tested). |
| 5 | long story | `My debit card got frozen last week after the bank flagged some suspicious activity. I know the purchases were mine, a few small bKash payments. Please unfreeze my card so I can use it again.` | Same box. |
| 6 | with details | `unfreeze my card ending 0293` | Box with `cardLast4: 0293` preselected. |
| 7 | vague | `my card is blocked` | May ask what you want (unfreeze or something else) first. |
| 8 | similar, different use case | `freeze my card` | NOT this one: freeze flow, `CONFIRMATION_REQUIRED` `card_services/frezz_unfrezz` (Yes/No, `cardLast4: 0293`), then code + PIN or password. |
| 9 | similar, different use case | `reset my pin` | NOT this one: `card_pin_reset` (3.1). |

### 3.3 Raise dispute
**Outcome:** gather → inline box (never submitted by the bot)  ·  **Result:** same as 2.2: gathering `CLARIFICATION_REQUIRED` (pending `raise_dispute`) / `TRANSACTION_SELECTION_REQUIRED`, final `BANKING_SERVICE` `service_requests/raise_dispute`, `executed: false`, `routing.action: "raise_dispute"`.
**UI to show:** Same as 2.2: U5 transaction picker if needed, then U8 dispute box (account ••••0056 and transaction prefilled, reason text, **Submit dispute**, then U7 code).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Problem` | Clarifying question (what happened?). No box. |
| 2 | two words | `charge problem` | Gathering: asks which charge, or transaction picker. |
| 3 | casual / typos | `hey my card got charged twice for the same thing wtf` | Gathering: transaction picker or what-went-wrong question. |
| 4 | full sentence | `I was charged for a purchase I didn't make on my card.` | Gathering toward `raise_dispute` (picker, then remarks). |
| 5 | long story | `Yesterday I paid 5,000 taka by bKash for a delivery that never arrived. The money was taken from my account but the seller says they received nothing. I'd like to dispute this transaction and get my money back.` | Summary with the 5,000 bKash transaction matched, remarks in your words, `executed: false`; dispute box prefilled. |
| 6 | with details | `dispute the 5000 taka bKash debit, the money left my account but never arrived` | Summary right away, box prefilled with ••••0056 and the matched transaction. |
| 7 | without details | `I want to raise a dispute about my card` | Gathering: picker or question. |
| 8 | vague | `my card thing is wrong` | Clarifying question first, no box. |
| 9 | follow-up (button) | Tap a transaction in the picker: `Selected` + `{"transactionId": ...}` | Asks for the reason (if missing) or returns the summary. |
| 10 | similar, different use case | `show my disputes` | NOT this one: `disputes` list (3.4), "no disputes". |

### 3.4 List disputes
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `service_requests/disputes` (`payload.disputes = []`)
**UI to show:** Bubble only: no disputes (empty list). No buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `disputes` | Bubble: no disputes. |
| 2 | two words | `show disputes` | Same. |
| 3 | casual / typos | `whats up with my dispute lol` | Same (may be read as status ask; "no open disputes"). |
| 4 | full sentence | `Can you please show me a list of all the disputes I have with this bank?` | Same. |
| 5 | long story | `On the 15th I tried to pay a friend with my card and it got stuck. I filed something about it afterwards. Can you list all my disputes so I can see which are still open?` | Same "no disputes". |
| 6 | with details | `status of the dispute for my 500 taka card payment` | Same list answer, none found. |
| 7 | similar, different use case | `show my complaints` | NOT this one: `my_tickets` (3.6), "no complaints". |
| 8 | similar, different use case | `raise a dispute` | NOT this one: dispute gathering (3.3). |

### 3.5 Submit complaint
**Outcome:** executed in chat after yes/no  ·  **Result:** `CLARIFICATION_REQUIRED` (when the description is missing, `payload.pending.service == "submit_complaint"`) → `CONFIRMATION_REQUIRED` `support/submit_complaint` (`payload.category`, `payload.description`) → on Yes `BANKING_SERVICE` `support/submit_complaint`, `executed: true`, `routing.action: "redirect"`; on No `executed: false`, `cancelled: true`. Bank failure: `SERVICE_UNAVAILABLE`.
**UI to show:** U1 asks what the complaint is, with the complaint text box (type + details, **Send**) when `pending.service == "submit_complaint"`; then U6 confirm card (category, description) with **Yes / No**; then a done notice that it appears under My Tickets. Often a clarifying question comes first (live run: 1 of 5 phrasings went straight to the confirm card).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `complaint` | Asks what the complaint is about; complaint box. |
| 2 | two words | `poor service` | Asks for details, or goes to the confirm card with the category SERVICE_QUALITY; may ask first. |
| 3 | casual / typos | `bank sucks lol my atm card didnt work yesterday` | May ask a clarifying question first; if it proceeds, confirm card with category CARD and the description. |
| 4 | full sentence | `I'm extremely dissatisfied with your app and would like to file a complaint.` | Asks what happened (complaint box), or the confirm card (category MOBILE_APP_TECHNICAL). |
| 5 | long story | `I tried to pay a bill in the app on Eid day but it kept freezing, and my card was declined twice last week as well. I contacted customer support but only got a reference number. I want to file a complaint about the app hanging when I pay a bill.` | Confirm card: `category` (e.g. MOBILE_APP_TECHNICAL) and a `description` in your words; **Yes / No**. |
| 6 | with details | `file a complaint: my debit card ending 0293 was declined at a shop although I have money` | Confirm card, category CARD, description includes the shop decline. |
| 7 | without details | `i want to file a complaint` | Asks what it is about; complaint box (`CLARIFICATION_REQUIRED` with `pending`). |
| 8 | vague | `i am not happy` | Asks what the issue is first; complaint box may appear. |
| 9 | follow-up (typed answer) | `The app hangs when I pay a bill` (after the question) | `CONFIRMATION_REQUIRED` with that description; **Yes / No**. |
| 10 | follow-up (box) | Type details in the complaint box and Send: app sends a direct request `support`/`submit_complaint` with `{"description", "category"}` | Confirm card with those values. |
| 11 | follow-up Yes | Tap **Yes**: `Yes` + `{"confirm": true}` (no `category`/`service`) | `BANKING_SERVICE`, `executed: true`; bubble says it was submitted; it shows under My Tickets (3.6 then lists it). |
| 12 | follow-up No | Tap **No**: `No` + `{"confirm": false}` | `BANKING_SERVICE`, `executed: false`, `cancelled: true`; nothing submitted. |
| 13 | similar, different use case | `my card isnt working` | NOT this one: clarifying question about what is happening; no complaint is started. |
| 14 | similar, different use case | `show my complaints` | NOT this one: `my_tickets` (3.6). |

### 3.6 My complaints
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `polygon_services/my_tickets` (`payload.complaints = []`)
**UI to show:** Bubble only: no complaints (empty list, no U2 card). No buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Complaints` | Bubble: no complaints. |
| 2 | two words | `my tickets` | Same. |
| 3 | casual / typos | `any update on my tickts?` | Same. |
| 4 | full sentence | `I need to see the status of my outstanding complaints with the bank.` | Same. |
| 5 | long story | `My ATM card was declined twice last week and once this Tuesday. I contacted customer support and they just gave me a reference number. I want to see all my existing complaints and their status in one place.` | Same "no complaints"; does not open a new one. |
| 6 | with details | `status of ticket TKT-12345` | Same list answer; none found. |
| 7 | vague | `any news on my issue` | May ask which issue (complaint or dispute) first; otherwise "no complaints". |
| 8 | similar, different use case | `I want to complain about the app` | NOT this one: `submit_complaint` (3.5). |
| 9 | similar, different use case | `show my disputes` | NOT this one: `disputes` (3.4). |

## CARD_MANAGEMENT

Test customer has one active debit card ending 0293 (id 45), no credit card. Every `APP_ACTION` below means: no bank call by the bot, `payload.ui.prefill` holds only what the customer typed, the box finishes in chat and shows its own done/failed tile. Boxes that need a credit card, a frozen card or a pending request will show an empty list for this customer.

### — My cards
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `account_info/cards`
**UI to show:** U1 bubble + U2 card tiles (type, masked number, status). One tile: debit ending 0293, active. No buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `cards` | Bubble lists the debit card ending 0293; one card tile |
| 2 | two words | `my cards` | Same card list |
| 3 | casual / typos | `my crads` | Same card list despite typo |
| 4 | full sentence | `Can you show me all the cards I have with the bank?` | One debit card ending 0293, active; no credit card |
| 5 | long story | `I am getting ready for a trip next month and want to be sure everything is in order. Before I travel I would like to see which cards I currently hold, whether they are active, and what type each one is.` | Same card list with type and status |
| 6 | with details | `is my debit card ending 0293 still active?` | Card list/answer shows 0293 as active |
| 7 | without details | `what cards do I have` | Same card list; nothing asked back |
| 8 | vague | `my plastic` | Either the card list or a short clarifying question; no box |
| 9 | follow-up | after `cards` send `and do I have a credit one?` | Bubble says no credit card on the list; only the debit card exists |
| 10 | different use case | `which cards does the bank offer` | NOT this one: `card_info/card_products` (4.10) |

### 4.1 Freeze card
**Outcome:** executed in chat after yes/no and then a code  ·  **Result:** `CLARIFICATION_REQUIRED` (reason) → `CONFIRMATION_REQUIRED` → `OTP_REQUIRED` → `BANKING_SERVICE` `card_services/frezz_unfrezz`
**UI to show:** U1 asks the reason; U6 confirm card (card ending 0293, reason; Yes / No); U7 secure sheet (code + card PIN or login password; Verify / Cancel); U1 done notice. Card picker U5 only if several cards (not for this customer). Warning: finishing the flow really freezes card 0293; answer No or Cancel to avoid that.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `freeze` | May ask which card or why (`CLARIFICATION_REQUIRED`); nothing is frozen yet |
| 2 | two words | `block card` | Single card is used automatically; bubble asks why; no code sent |
| 3 | casual / typos | `plz freeze my card coz its lost!!` | Reason already given: goes straight to `CONFIRMATION_REQUIRED` with card 0293 and reason; no code yet |
| 4 | full sentence | `I need to block my card because it was stolen.` | `CONFIRMATION_REQUIRED`, payload card 0293 + reason in the customer's words; Yes/No card |
| 5 | long story | `I travelled to Chattogram last week and I think someone took my wallet at the bus station. My debit card was inside. I do not want anyone using it until I get a new one, so please freeze it right away.` | `CONFIRMATION_REQUIRED` with the story as reason; Yes/No card; no code yet |
| 6 | with details | `freeze my debit card ending 0293, someone used it without me` | `CONFIRMATION_REQUIRED`, `cardLast4` 0293, reason given |
| 7 | without details | `block my card` | `CLARIFICATION_REQUIRED` asking why; nothing frozen |
| 8 | vague | `my card isn't working` | A question, never a freeze (the bot freezes only when asked to block or told what happened) |
| 9 | follow-up | after #7, send `it was stolen at the market` | `CONFIRMATION_REQUIRED` for card 0293 with that reason |
| 10 | different use case | `unfreeze my card` | NOT a freeze: `APP_ACTION` `card_unfreeze` (4.2) |

Second table, finish the flow (stop at any step to avoid freezing):

| Step | Send (message + payload) | Expect |
|---|---|---|
| Yes button | `Yes` + `{"confirm": true}` | `OTP_REQUIRED` `card_services/frezz_unfrezz`, `otpRequired: true`, `credentialOptions` pin/password, `OTP_SENT`; U7 sheet |
| No button | `No` + `{"confirm": false}` | `BANKING_SERVICE` `executed: false, cancelled: true`; no code sent |
| Verify | `Verify` + `{"otp": <code from the sheet>, "pin": <card PIN>}` (or `password`) | `BANKING_SERVICE` `executed: true`, `cardLast4` 0293, `status` blocked; U1 done notice |
| Cancel sheet | `cancel` + `{"confirm": false}` | `BANKING_SERVICE` `executed: false, cancelled: true` |
| Typed yes | `yes go ahead` | Also works (model reads it); same as Yes button |
| Typed other request | `what's my balance?` | Pending freeze dropped, nothing frozen, balance answered |

### 4.2 Unfreeze card
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_unfreeze` (`routing.action` `card_unfreeze`)
**UI to show:** U8 box "Frozen cards" with each frozen card and an **Unfreeze** button, card preselected from `prefill.cardLast4`; after the button U7 (code + PIN or password). Card 0293 is active, so the list is empty for this customer.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `unfreeze` | `APP_ACTION` `card_unfreeze`; box with Unfreeze; no prefill |
| 2 | two words | `unblock card` | `card_unfreeze` box |
| 3 | casual / typos | `hey i got my card frozen by mistake yesterday pls unfreeze it tia` | `card_unfreeze` box |
| 4 | full sentence | `Can you please unfreeze my card? It has been blocked since last night.` | `card_unfreeze` box; no bank call |
| 5 | long story | `I tried to buy groceries this morning and my card got declined. I remember freezing it last week when I could not find it, but I found it at home yesterday. I would like to start using it again, so please unfreeze it.` | `card_unfreeze` box; bubble says finish in chat |
| 6 | with details | `unfreeze my card ending 0293` | `card_unfreeze`, `prefill.cardLast4` = `0293`; card preselected in box |
| 7 | without details | `reactivate my card` | `card_unfreeze` box with empty prefill; picker of frozen cards |
| 8 | vague | `free my card` | Should be `card_unfreeze`; known gap: short/odd wording may be misread as freeze, which only shows the freeze Yes/No (answer No) |
| 9 | follow-up | after `cards`, send `unfreeze it` | `card_unfreeze` box (card may be resolved from context) |
| 10 | different use case | `freeze my card, it was stolen` | NOT this: 4.1 freeze yes/no flow |

### 4.3 Close card
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_close` (`routing.action` `card_close`)
**UI to show:** U8 box: the card (preselected from `cardLast4`) with a warning that closing is permanent; buttons **Close card** / **Keep**; after Close card, U7 (code + PIN or password). No close happens in chat.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `close` | `card_close` box (may ask a clarifying question first) |
| 2 | two words | `close card` | `card_close` box |
| 3 | casual / typos | `cncl my card pls` | `card_close` box |
| 4 | full sentence | `I need to close my bank card, can you help me do that?` | `card_close` box with permanence warning |
| 5 | long story | `I have not used my debit card for months and I keep worrying about it being misused. I decided I would rather not keep it. Please help me close it permanently so no one can use it.` | `card_close` box |
| 6 | with details | `close my debit card ending 0293` | `card_close`, `prefill.cardLast4` = `0293`; card preselected |
| 7 | without details | `I want to cancel one of my cards` | `card_close` box, empty prefill, card picker |
| 8 | vague | `get rid of my card` | `card_close` box, or a short clarifying question; never closed in chat |
| 9 | follow-up | after `cards`, send `close that one` | `card_close` box (card may be resolved from context) |
| 10 | different use case | `I lost my card, block it` | NOT this: lost/freeze flow (4.1 / 12.2) |

### 4.4 Contactless on/off
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_contactless` (`routing.action` `card_contactless`)
**UI to show:** U8 box: card tile with a contactless on/off switch and optional limit field; button **Save**; no code step.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `contactless` | `card_contactless` box |
| 2 | two words | `contactless off` | `card_contactless` box |
| 3 | casual / typos | `hey can u turn contactles on/off pls?` | `card_contactless` box |
| 4 | full sentence | `Can you switch off the tap-to-pay feature on my card?` | `card_contactless` box |
| 5 | long story | `I read a news story about people being charged by someone tapping a reader near a wallet. Even though it is unlikely, I would feel safer if tap payments were disabled on my debit card for now. How can I do that?` | `card_contactless` box |
| 6 | with details | `turn off contactless for my card ending 0293` | `card_contactless`, `prefill.cardLast4` = `0293`; switch ready |
| 7 | without details | `enable contactless` | `card_contactless` box, empty prefill |
| 8 | vague | `tap payment` | `card_contactless` box or a clarifying question |
| 9 | follow-up | after `cards`, send `turn contactless off on it` | `card_contactless` box |
| 10 | different use case | `turn off international transactions` | NOT this: `card_international` (4.5) |

### 4.5 International transaction on/off
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_international` (`routing.action` `card_international`)
**UI to show:** U8 box: card (preselected from `cardLast4`) with an international-use on/off switch; button **Save**; then U7 (code + PIN or password).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `international` | `card_international` box (may ask a clarifying question first) |
| 2 | two words | `overseas usage` | `card_international` box |
| 3 | casual / typos | `can u enable intl transactions on my card pls` | `card_international` box |
| 4 | full sentence | `Can you turn international transactions on for my card?` | `card_international` box |
| 5 | long story | `I am travelling to Dubai next week for work and I will need to pay with my card at hotels and shops there. Last time my card was declined abroad because overseas use was off. Please help me switch international use on.` | `card_international` box |
| 6 | with details | `enable international use on card ending 0293` | `card_international`, `prefill.cardLast4` = `0293` |
| 7 | without details | `switch off international` | `card_international` box, empty prefill |
| 8 | vague | `use my card abroad` | `card_international` box or a clarifying question |
| 9 | follow-up | after `cards`, send `turn it on for international` | `card_international` box |
| 10 | different use case | `what are the international charges on my card` | NOT this: a knowledge-base question (bubble only) |

### 4.6 Reset card PIN
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_pin_reset` (`routing.action` `card_pin_reset`)
**UI to show:** U8 box: card (preselected from `cardLast4`, else card picker) and **Reset PIN** button; then U7 (code + PIN or password).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `PIN` | `card_pin_reset` box or a clarifying question |
| 2 | two words | `reset PIN` | `card_pin_reset` box |
| 3 | casual / typos | `cant remembr my pin lol help!` | `card_pin_reset` box |
| 4 | full sentence | `I want to reset the PIN of my debit card.` | `card_pin_reset` box |
| 5 | long story | `I went to an ATM yesterday and the machine rejected my PIN three times. I am worried it will be blocked. I think I have forgotten it after not using the card for a long time. I need a new PIN, please help.` | `card_pin_reset` box |
| 6 | with details | `reset the pin for my card ending 0293` | `card_pin_reset`, `prefill.cardLast4` = `0293`; card preselected |
| 7 | without details | `change my card pin` | `card_pin_reset` box, empty prefill, card picker |
| 8 | vague | `card pin problem` | `card_pin_reset` box or a clarifying question; never a freeze |
| 9 | follow-up | after `cards`, send `reset the pin of that card` | `card_pin_reset` box |
| 10 | different use case | `change my login password` | NOT this: a different intent (profile/security), not `card_pin_reset` |

### 4.7 Limit change — submit
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_limit_change` (`routing.action` `card_limit_change`)
**UI to show:** U8 form: credit card (preselected), new limit in taka, optional reason; button **Submit request**; no code step. This customer has no credit card, so the card picker is empty.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `limit` | `card_limit_change` box or a clarifying question |
| 2 | two words | `change limit` | `card_limit_change` box |
| 3 | casual / typos | `can i cnage my lmit pls thx` | `card_limit_change` box |
| 4 | full sentence | `I would like to raise the spending limit on my credit card.` | `card_limit_change` box, empty prefill |
| 5 | long story | `My salary was increased this month and I now spend more on my credit card for family expenses, so the current limit gets used up halfway through the month. I would like to apply for a higher limit so I can stop worrying about declines.` | `card_limit_change` box |
| 6 | with details | `increase my credit card limit to 150000 on the card ending 0251` | `card_limit_change`, `prefill.cardLast4` = `0251`, `prefill.requestedLimit` = `150000` (taka) |
| 7 | without details | `I want a higher card limit` | `card_limit_change` box, empty prefill |
| 8 | vague | `bigger limit` | `card_limit_change` box or a clarifying question |
| 9 | follow-up | after `change limit`, send `make it 80000` | `card_limit_change` with `requestedLimit` 80000, or a box asking for the amount |
| 10 | different use case | `show my limit change requests` | NOT this: `card_info/card_limit_requests` (4.8) |

### 4.8 Limit change — list
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `card_info/card_limit_requests`
**UI to show:** U1 bubble + U2 requests list (status). Empty for this customer: bubble only, says there are none; no buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `limit requests` | `card_limit_requests`; bubble says none |
| 2 | two words | `limit status` | Same; none |
| 3 | casual / typos | `did my card limit chnage go thru` | Same; none found |
| 4 | full sentence | `Can you tell me what happened to my card limit change request?` | `card_limit_requests`; none, bubble says so |
| 5 | long story | `Two weeks ago I applied to increase my card limit because I have a big purchase coming up. I have not heard back from the bank. Could you check whether my request is still pending, approved or rejected?` | `card_limit_requests`; none; bubble never invents a request |
| 6 | with details | `status of my limit request for the card ending 0251` | `card_limit_requests`; none found |
| 7 | without details | `my limit change requests` | `card_limit_requests`; none |
| 8 | vague | `any news on my limit?` | `card_limit_requests` or a clarifying question |
| 9 | follow-up | after #4, send `ok and can I cancel it?` | Nothing pending: `card_limit_cancel` box (4.9) or bubble saying none to cancel |
| 10 | different use case | `raise my card limit to 200000` | NOT this: `card_limit_change` (4.7) |

### 4.9 Limit change — cancel
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_limit_cancel` (`routing.action` `card_limit_cancel`)
**UI to show:** U8 box: the customer's pending limit-change requests, each with **Cancel request** (asks to confirm); no code step. No pending requests for this customer, so the list is empty.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `cancel` | Vague; likely a clarifying question, not this box |
| 2 | two words | `cancel limit` | `card_limit_cancel` box |
| 3 | casual / typos | `pls cancl limit change lol` | `card_limit_cancel` box |
| 4 | full sentence | `I want to cancel the card limit change request I submitted.` | `card_limit_cancel` box |
| 5 | long story | `Last week I asked for a higher limit on my credit card, but then I realised the old limit is enough and I do not want the bank to process it. Please withdraw that limit change request.` | `card_limit_cancel` box |
| 6 | with details | `cancel my limit increase request for the card ending 0251` | `card_limit_cancel` box (no prefill fields defined) |
| 7 | without details | `withdraw my limit request` | `card_limit_cancel` box |
| 8 | vague | `undo the limit thing` | `card_limit_cancel` box or a clarifying question |
| 9 | follow-up | after `limit requests` (4.8), send `cancel it` | `card_limit_cancel` box |
| 10 | different use case | `change my card limit to 50000` | NOT this: `card_limit_change` (4.7) |

### 4.10 Card products list
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `card_info/card_products`
**UI to show:** U1 bubble + U2 products (name, category, scheme; active only). Optional **Apply** button that sends the message `Apply for a card` (opens the apply box, 4.11). Expect products such as Classic Debit and GOLD credit; bubble wording may mix debit and credit, so judge by the card list.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `products` | `card_products` list (or a question if too bare) |
| 2 | two words | `card types` | `card_products` list |
| 3 | casual / typos | `hey wht cards r available?` | `card_products` list |
| 4 | full sentence | `Can you tell me what kinds of credit cards this bank offers?` | `card_products` list; may include debit entries too |
| 5 | long story | `I currently only use a debit card for shopping, but I am thinking of getting something with better benefits. Before I walk into a branch, I would like to see what card products the bank offers and which scheme each runs on.` | `card_products` list with name, category, scheme |
| 6 | with details | `show me the VISA debit cards you offer` | `card_products`; optional filter (`cardCategory`, `scheme`) narrows the list |
| 7 | without details | `what cards can I apply for` | `card_products` list, or the apply box (4.11); not an error |
| 8 | vague | `anything better than my card?` | `card_products` list or a clarifying question |
| 9 | follow-up | after #3, tap Apply (message `Apply for a card`) | `APP_ACTION` `card_apply` box (4.11) |
| 10 | different use case | `show my cards` | NOT this: `account_info/cards` (own cards) |

### 4.11 Apply for debit card
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_apply` (`routing.action` `card_apply`)
**UI to show:** U8 form: card type (debit / prepaid / virtual, preselected from `prefill.cardType`), product picker, account to link (0056), name on the card; button **Apply**; debit and prepaid then U7 (code + PIN or password), virtual none.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `card` | Vague: a clarifying question or the apply box |
| 2 | two words | `debit card` | `card_apply` box; `cardType` debit may be prefilled |
| 3 | casual / typos | `can i get a debt card plz?` | `card_apply` box |
| 4 | full sentence | `I would like to apply for a new debit card.` | `card_apply`, `prefill.cardType` debit |
| 5 | long story | `My current debit card is almost worn out and I also want a second one to keep at home for my spouse to use. I would like to apply for another debit card linked to my savings account. What do I need to do?` | `card_apply` box; account 0056 selectable |
| 6 | with details | `apply for a debit card in the name Taslim Islam on my savings account 0056` | `card_apply`, `prefill.cardType` debit; other fields chosen in the box |
| 7 | without details | `I want a new card` | `card_apply` box with no card type chosen |
| 8 | vague | `need another card` | `card_apply` box or a clarifying question |
| 9 | follow-up | after `card products` (4.10), send `apply for the classic one` | `card_apply` box |
| 10 | different use case | `replace my lost debit card` | NOT this: lost/stolen flow (12.1) |

### 4.12 Reveal debit card details
**Outcome:** info only  ·  **Result:** `APP_ACTION` `app_actions/card_details_reveal` (kind `info`)
**UI to show:** U9 info card, no button. The full number, expiry and CVV are never shown in chat.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `CVV` | `card_details_reveal` info; no number shown |
| 2 | two words | `card number` | Info card; bot refuses to show it in chat |
| 3 | casual / typos | `whats my full card numbr` | Info card; no number |
| 4 | full sentence | `Can you show me the full number of my debit card?` | Info card; details only inside the app |
| 5 | long story | `I am shopping online and the website asks for my card number, expiry date and CVV. I do not have my card with me. Could you read out the full details of my debit card here in the chat?` | Info card; bubble says details are never shown in chat |
| 6 | with details | `show the expiry and CVV of my card ending 0293` | Info card; no expiry or CVV |
| 7 | without details | `reveal my card details` | Info card; no box, no button |
| 8 | vague | `my card info` | Either the card list (`cards`, masked) or the info card; never the full number |
| 9 | follow-up | after `cards`, send `now show me the whole number` | Info card; refused in chat |
| 10 | different use case | `show my cards` | NOT this: `account_info/cards` (masked list) |

### 4.13 Apply for prepaid card
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_apply` (`routing.action` `card_apply`)
**UI to show:** U8 apply form as 4.11, `cardType` prepaid preselected, plus the load amount; button **Apply**; then U7 (code + PIN or password).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `prepaid` | `card_apply` box (may ask a question) |
| 2 | two words | `prepaid card` | `card_apply`, `prefill.cardType` prepaid |
| 3 | casual / typos | `hey can i get a prepade card pls` | `card_apply` box |
| 4 | full sentence | `I would like to apply for a prepaid card.` | `card_apply`, `cardType` prepaid |
| 5 | long story | `My teenage son wants to start shopping online but I do not want to give him my main card. A prepaid card that I top up with a fixed amount would be perfect. Can I apply for one for him?` | `card_apply` box, prepaid |
| 6 | with details | `apply for a prepaid card and load 5000 taka on it` | `card_apply`, `prefill.cardType` prepaid; load amount entered in the box |
| 7 | without details | `I want a card I can top up` | `card_apply` box or a clarifying question |
| 8 | vague | `a card for online shopping` | `card_apply` box or a clarifying question; type may be left to the customer |
| 9 | follow-up | after `card` (bot asks which kind), send `prepaid` | `card_apply`, `cardType` prepaid |
| 10 | different use case | `top up my existing prepaid card` | NOT this: a different request, not `card_apply` |

### 4.14 Reveal prepaid card details
**Outcome:** info only  ·  **Result:** `APP_ACTION` `app_actions/card_details_reveal` (kind `info`)
**UI to show:** U9 info card, no button; full details never shown in chat.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `prepaid` | Likely `card_apply` or a question; not a reveal (ambiguous) |
| 2 | two words | `prepaid CVV` | `card_details_reveal` info card |
| 3 | casual / typos | `show me my prepade card numbr` | Info card; no number |
| 4 | full sentence | `Can you show me the full details of my prepaid card?` | Info card; details only in the app |
| 5 | long story | `I topped up my prepaid card last week to pay for a subscription and now the site wants the card number and CVV. I left the card at home. Please read out the complete details here.` | Info card; refused in chat |
| 6 | with details | `show the expiry of my prepaid card ending 4410` | Info card; no expiry shown (customer has no prepaid card) |
| 7 | without details | `reveal my prepaid card details` | Info card; no box |
| 8 | vague | `prepaid card info` | Info card, or a clarifying question |
| 9 | follow-up | after #4, send `just the CVV then` | Info card again; never the CVV |
| 10 | different use case | `apply for a prepaid card` | NOT this: `card_apply` (4.13) |

### 4.15 Virtual card — submit
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/card_apply` (`routing.action` `card_apply`)
**UI to show:** U8 apply form as 4.11, `cardType` virtual preselected; button **Apply**; virtual needs no code step.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `virtual` | `card_apply` box (may ask a question) |
| 2 | two words | `virtual card` | `card_apply`, `prefill.cardType` virtual |
| 3 | casual / typos | `can i get a vcard pls? lol` | `card_apply` box |
| 4 | full sentence | `Can you please create a virtual card for me?` | `card_apply`, `cardType` virtual; the bot only opens the box, it does not issue the card |
| 5 | long story | `I want to buy something from an overseas website but I do not want to type my real card number into it. I heard banks can give a virtual card just for online use. Can I get one?` | `card_apply` box, virtual |
| 6 | with details | `apply for a virtual card linked to my account 0056` | `card_apply`, `prefill.cardType` virtual; account chosen in the box |
| 7 | without details | `I need a card only for online use` | `card_apply` box or a clarifying question |
| 8 | vague | `digital card` | `card_apply` box or a clarifying question |
| 9 | follow-up | after `card` (bot asks which kind), send `virtual` | `card_apply`, `cardType` virtual |
| 10 | different use case | `status of my virtual card request` | NOT this: `card_info/virtual_card_requests` (4.16) |

### 4.16 Virtual card — list
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `card_info/virtual_card_requests`
**UI to show:** U1 bubble + U2 requests list with status. Empty for this customer: bubble says none, no box.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `virtual` | Ambiguous: a question or `card_apply`; not necessarily the list |
| 2 | two words | `virtual requests` | `virtual_card_requests`; none |
| 3 | casual / typos | `hey wot abt my virtul card request??` | `virtual_card_requests`; none |
| 4 | full sentence | `Can you show me the status of my virtual card requests?` | `virtual_card_requests`; "there are none" |
| 5 | long story | `Some time ago I applied for a virtual card so I could pay for online subscriptions. I never received a confirmation. Could you check what happened to that request, and whether it was approved or is still pending?` | `virtual_card_requests`; none, no invented request |
| 6 | with details | `has my virtual card request from last Monday been approved?` | `virtual_card_requests`; none |
| 7 | without details | `my virtual card requests` | `virtual_card_requests`; none |
| 8 | vague | `any update on my virtual card?` | `virtual_card_requests` or a clarifying question |
| 9 | follow-up | after #4, send `ok then apply for one` | `APP_ACTION` `card_apply`, virtual (4.15) |
| 10 | different use case | `cancel my virtual card` | NOT this: info card `card_virtual_cancel` (4.17) |

### 4.17 Virtual card — cancel
**Outcome:** info only  ·  **Result:** `APP_ACTION` `app_actions/card_virtual_cancel` (kind `info`)
**UI to show:** U9 info card "Cancel virtual card"; the app has no screen for it. No button.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `cancel` | Vague; likely a question, not this |
| 2 | two words | `cancel vcard` | `card_virtual_cancel` info card |
| 3 | casual / typos | `can u pls cancl my virtul card? ty!` | `card_virtual_cancel` info card |
| 4 | full sentence | `I want to cancel my virtual card.` | Info card; says no app screen for this now |
| 5 | long story | `I created a virtual card for a free trial and forgot about it. Now I see a monthly fee notification and I would like it cancelled right away so nothing else is charged.` | Info card; no box, no button |
| 6 | with details | `cancel my virtual card request from yesterday` | Info card |
| 7 | without details | `delete virtual card` | Info card |
| 8 | vague | `stop the online card` | Info card or a clarifying question |
| 9 | follow-up | after #4, send `why not?` | Bubble only; no box |
| 10 | different use case | `close my debit card` | NOT this: `card_close` (4.3) |

### 4.18 Virtual card — reveal
**Outcome:** info only  ·  **Result:** `APP_ACTION` `app_actions/card_details_reveal` (kind `info`)
**UI to show:** U9 info card, no button; full details never shown in chat.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `vcard` | Ambiguous; a question or another virtual-card answer |
| 2 | two words | `virtual CVV` | `card_details_reveal` info card |
| 3 | casual / typos | `show my virtul card numbr` | Info card; no number |
| 4 | full sentence | `Can you show me the number and CVV of my virtual card?` | Info card; details only in the app |
| 5 | long story | `I am at checkout on a shopping site and it needs my virtual card number, expiry and CVV. I do not have time to open the app. Please paste all the details of my virtual card here.` | Info card; refused in chat |
| 6 | with details | `reveal the details of my virtual card ending 7788` | Info card; no details (customer has no virtual card) |
| 7 | without details | `see virtual card details` | Info card |
| 8 | vague | `virtual card info` | Info card, or a list/question; never full details |
| 9 | follow-up | after `virtual card requests` (none), send `show me its number` | Info card; no number |
| 10 | different use case | `apply for a virtual card` | NOT this: `card_apply` (4.15) |

### 4.19 Star card
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/quick_view_star` (`routing.action` `quick_view_star`)
**UI to show:** U8 box: accounts and cards, each with a star switch; the one named starts switched on; no code step. Box shows account 0056 and card 0293.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `star` | `quick_view_star` box |
| 2 | two words | `star card` | `quick_view_star` box |
| 3 | casual / typos | `hey pin my card to home screen plz` | `quick_view_star` box |
| 4 | full sentence | `Can you add my debit card to my favourites on the home screen?` | `quick_view_star` box |
| 5 | long story | `I mostly use only one of my cards and I keep scrolling past the rest to find it. I would like it to show up first on the home quick view so I can check it quickly. How can I do that?` | `quick_view_star` box |
| 6 | with details | `star my card ending 0293` | `quick_view_star`; card 0293 starts switched on |
| 7 | without details | `favourite a card` | `quick_view_star` box, nothing preselected |
| 8 | vague | `make my card appear first` | `quick_view_star` box or a clarifying question |
| 9 | follow-up | after `cards`, send `star that one` | `quick_view_star` box |
| 10 | different use case | `I want a new card` | NOT this: `card_apply` (4.11) |

### 4.20 Credit card bill payment (card service)
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/credit_card_pay` (`routing.action` `credit_card_pay`)
**UI to show:** U8 box: credit card (preselected), what to pay (total outstanding / statement due / minimum due), account to pay from; button **Pay**; no code step. Customer has no credit card, so the card picker is empty.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `pay` | Vague: a question or another pay intent; not necessarily this |
| 2 | two words | `card bill` | `credit_card_pay` box (may ask whether own card or another bank's) |
| 3 | casual / typos | `plz pay my card bill thx lol` | `credit_card_pay` box |
| 4 | full sentence | `I want to pay my credit card bill.` | `credit_card_pay` box |
| 5 | long story | `I paid my credit card late last month and got charged a fee, so this time I want to be early. I do not need to clear everything, I just want to cover what is due this statement. Please help me pay it from my savings account.` | `credit_card_pay` box; `prefill.paymentType` statement due |
| 6 | with details | `pay the minimum due on my credit card ending 0251` | `credit_card_pay`, `prefill.cardLast4` = `0251`, `paymentType` minimum due |
| 7 | without details | `pay my credit card` | `credit_card_pay` box, empty prefill |
| 8 | vague | `clear my dues` | `credit_card_pay` box or a clarifying question |
| 9 | follow-up | after `card bill`, send `total outstanding` | `credit_card_pay` with `paymentType` total outstanding |
| 10 | different use case | `pay my Standard Chartered card bill` | NOT this: `other_card_pay` (4.21) |

### 4.21 Credit card bill payment (bill service)
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/other_card_pay` (`routing.action` `other_card_pay`)
**UI to show:** U8 form: card number to pay (last digits prefilled), amount, account to pay from, note; button **Pay**; then U7 (code + transaction PIN).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `pay` | Vague; a question or another pay intent |
| 2 | two words | `CC bill` | `credit_card_pay` or `other_card_pay`, or a question asking whose card |
| 3 | casual / typos | `hey pay my other bank credit card bill pls thnx!!` | `other_card_pay` box |
| 4 | full sentence | `I need to make a payment for my Standard Chartered credit card.` | `other_card_pay` box |
| 5 | long story | `My wife has a Visa credit card from another bank and the due date is tomorrow. She is travelling, so I will pay it for her from my account. The card number ends in 4455 and I want to pay five thousand taka.` | `other_card_pay`, `prefill.cardNumberLast4` = `4455`, `amount` = `5000` |
| 6 | with details | `pay 3000 to my other bank credit card ending 9012` | `other_card_pay`, `cardNumberLast4` = `9012`, `amount` = `3000` (taka) |
| 7 | without details | `pay a credit card of another bank` | `other_card_pay` box, empty prefill |
| 8 | vague | `settle my card at the other bank` | `other_card_pay` box or a clarifying question |
| 9 | follow-up | after `CC bill` (bot asks which), send `another bank's card` | `other_card_pay` box |
| 10 | different use case | `pay my own credit card due` | NOT this: `credit_card_pay` (4.20) |

### 4.22 QR payment cards — list
**Outcome:** not offered  ·  **Result:** `APP_ACTION` `app_actions/qr_payment_cards` (kind `unavailable`)
**UI to show:** Bubble only (U9 at most); the bot says it isn't available. No box, no button.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `QR` | Likely a question or QR-pay answer; not necessarily this |
| 2 | two words | `QR cards` | `qr_payment_cards` unavailable; bubble only |
| 3 | casual / typos | `can u pls list my qr paymnt cards? thx` | Unavailable; bubble only |
| 4 | full sentence | `Can you show me which cards are set up for QR payments?` | Unavailable; no box |
| 5 | long story | `I tried scanning a QR code at a shop yesterday and it did not work. I want to check which of my cards are linked for QR payments, because I think the wrong one is selected.` | Unavailable; bubble only |
| 6 | with details | `list the QR payment cards on my account 0056` | Unavailable; bubble only |
| 7 | without details | `QR payment settings` | Unavailable; bubble only |
| 8 | vague | `my qr thing` | Unavailable or a clarifying question |
| 9 | follow-up | after #4, send `ok when will it be available?` | Bubble only; no box |
| 10 | different use case | `I want to pay with a QR code` | NOT this: `qr_payment` info/screen action (14.16), not `qr_payment_cards` |

### 4.23 QR payment card — enable/disable
**Outcome:** not offered  ·  **Result:** `APP_ACTION` `app_actions/qr_payment_cards` (kind `unavailable`)
**UI to show:** Bubble only (U9 at most); the bot says it isn't available. No box, no button.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `disable` | Vague; a question, not this |
| 2 | two words | `turn off QR` | `qr_payment_cards` unavailable; bubble only |
| 3 | casual / typos | `hey can u turn qr card on/off pls? thx` | Unavailable; bubble only |
| 4 | full sentence | `I want to disable my card for QR payments.` | Unavailable; no box |
| 5 | long story | `Someone told me that my card can be used for QR payments by default. I am worried about misuse, so I would like to switch QR payments off for my debit card until I need it again.` | Unavailable; bubble only |
| 6 | with details | `enable QR payments on my card ending 0293` | Unavailable; bubble only, nothing changes |
| 7 | without details | `enable QR card` | Unavailable; bubble only |
| 8 | vague | `qr on off` | Unavailable or a clarifying question |
| 9 | follow-up | after #4, send `can you do it any other way?` | Bubble only; no box |
| 10 | different use case | `turn off contactless` | NOT this: `card_contactless` (4.4) |

## CARD_REPLACEMENT

### 5.1 List replacement requests
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `card_info/replacement_requests`
**UI to show:** U1 bubble + U2 requests list (requested date, card ending, status). Empty for this customer: bubble says there are currently no replacement requests; no box.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `replacement` | `replacement_requests`; none (or a short question) |
| 2 | two words | `replacement status` | `replacement_requests`; none |
| 3 | casual / typos | `replacemnt req` | `replacement_requests`; none |
| 4 | full sentence | `Can you check the status of my card replacement request?` | `replacement_requests`; "no replacement requests" |
| 5 | long story | `I lost my debit card on a bus a while ago and I asked for a replacement at the branch. Nobody has called me since. Could you check whether the replacement request is still being processed or has already been approved?` | `replacement_requests`; none, no invented request |
| 6 | with details | `has the replacement for my card ending 0293 been issued yet?` | `replacement_requests`; none |
| 7 | without details | `my card replacement requests` | `replacement_requests`; none |
| 8 | vague | `where is my new card?` | `replacement_requests` or a clarifying question |
| 9 | follow-up | after #4, send `ok cancel it` | `APP_ACTION` `replacement_cancel` box (5.2) or a bubble saying nothing to cancel |
| 10 | different use case | `I lost my card, replace it` | NOT this: lost/stolen flow (12.1) |

### 5.2 Cancel replacement request
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/replacement_cancel` (`routing.action` `replacement_cancel`)
**UI to show:** U8 box: the customer's pending replacement requests, each with **Cancel request** (asks to confirm); no code step. No pending requests for this customer, so the list is empty.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `cancel` | Vague; likely a question, not this |
| 2 | two words | `cancel replacement` | `replacement_cancel` box |
| 3 | casual / typos | `cncl replcement pls i asked by mistake thx` | `replacement_cancel` box |
| 4 | full sentence | `I want to cancel my card replacement request.` | `replacement_cancel` box |
| 5 | long story | `Last week I requested a replacement card because I could not find mine. Yesterday I found it in a coat pocket, so I do not need a new one anymore. Please cancel the replacement before the bank issues it.` | `replacement_cancel` box |
| 6 | with details | `cancel the replacement request for my card ending 0293` | `replacement_cancel` box (no prefill fields defined) |
| 7 | without details | `withdraw my replacement request` | `replacement_cancel` box |
| 8 | vague | `never mind the new card` | `replacement_cancel` box or a clarifying question |
| 9 | follow-up | after `replacement status` (5.1), send `cancel it` | `replacement_cancel` box |
| 10 | different use case | `close my card` | NOT this: `card_close` (4.3) |

### 5.3 Reveal replacement card details
**Outcome:** info only  ·  **Result:** `APP_ACTION` `app_actions/card_details_reveal` (kind `info`)
**UI to show:** U9 info card, no button; full details never shown in chat.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `replacement` | Likely 5.1 list, not a reveal (ambiguous) |
| 2 | two words | `new card number` | `card_details_reveal` info card |
| 3 | casual / typos | `show my replacment card numbr pls` | Info card; no number |
| 4 | full sentence | `Can you show me the full details of my replacement card?` | Info card; details only in the app |
| 5 | long story | `The bank sent me a replacement card last week and I want to use it online right away, but I have not collected it from the branch yet. Please tell me the complete number, expiry and CVV of the new card.` | Info card; refused in chat |
| 6 | with details | `reveal the CVV of the replacement card for the card ending 0293` | Info card; no CVV |
| 7 | without details | `show replacement card details` | Info card; no box |
| 8 | vague | `my new card info` | Info card or a clarifying question; never full details |
| 9 | follow-up | after `replacement status`, send `show me its number` | Info card; no number |
| 10 | different use case | `status of my replacement request` | NOT this: `replacement_requests` (5.1) |

## CHECK_BALANCE

Test customer has one savings account (0056, Tk 90,000) and no credit card, so the account picker (U5) never appears. Nothing here changes data.

### 6.1 Account balance
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `account_info/balance`
**UI to show:** U3 detail card: balance prominent (৳90,000.00), account ending 0056 below. No buttons. (U5 picker first only if the customer had several accounts.)

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `balance` | Bubble gives Tk 90,000; `balance` result; U3 card |
| 2 | two words | `my balance` | Same |
| 3 | casual / typos | `blance pls` | Same, typo understood |
| 4 | full sentence | `How much money do I have in my account right now?` | Same |
| 5 | long story | `I just got paid yesterday and I want to buy a phone tomorrow, but I'm not sure my salary arrived. Before I go to the shop can you tell me how much money is left in my account?` | Same; one answer, no extra question |
| 6 | with details | `what is the balance of my account ending 0056` | Same; account 0056 used |
| 7 | without details | `how much do I have` | Same; one account, so no picker, answered straight away |
| 8 | vague | `am I broke?` | Either the balance answer or a clarifying question (`CLARIFICATION_REQUIRED`, bubble only) |
| 9 | follow-up | first `balance`, then `and my credit card?` | Second turn: no-credit-card answer (see 6.2), bubble only |
| 10 | different use case | `show my last transactions` | Must NOT be `balance`: `polygon_services/transaction_history`, U4 list (see 8.1) |

### 6.2 Credit card summary
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `card_info/credit_card_summary`
**UI to show:** customer with a card: U3 card (limit, outstanding or due, available credit). This test customer has no credit card: `payload` is `{"creditCard": null, "answer": ...}`, bubble says "you don't have a credit card with Polygon Bank"; bubble only, no card, no buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `credit` | `credit_card_summary` or a clarifying question; if answered: no credit card, bubble only |
| 2 | two words | `credit limit` | No credit card, bubble only |
| 3 | casual / typos | `how much credit card limit left?` | No credit card, bubble only |
| 4 | full sentence | `Can you show me my credit card summary?` | No credit card, bubble only |
| 5 | long story | `I made a lot of purchases online last week with my credit card and I'm worried I'm close to the limit. Can you tell me my available credit and how much I need to pay this month?` | No credit card, bubble only |
| 6 | with details | `what is my credit card due amount this month` | No credit card, bubble only |
| 7 | without details | `card summary` | May ask a clarifying question first (credit or debit?); if answered: no credit card |
| 8 | vague | `how am I doing on my card` | Clarifying question or no-credit-card answer; bubble only |
| 9 | follow-up | `card summary`, then (if asked which card) `credit card` | Second turn: no-credit-card answer, bubble only |
| 10 | different use case | `increase my credit card limit to 50000` | Must NOT be 6.2: `APP_ACTION` `app_actions/card_limit_change`, info only (U8/U9 per COMMON.md) |

## EDIT_PERSONAL_DETAILS

Gather-style asks (mobile, email, address) often get a clarifying question first; that is expected. Nothing is changed until the customer answers Yes or enters a code. Never type real codes; enter the code in the secure sheet.

### 7.1 Get profile
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `profile/profile`
**UI to show:** U3 profile card: name, nickname, email, masked phone. No buttons. Bubble never shows CIF or NID.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `profile` | Bubble with name, email, masked phone; U3 card |
| 2 | two words | `my profile` | Same |
| 3 | casual / typos | `hey show me my pofile plz` | Same |
| 4 | full sentence | `Can you please show me my profile details?` | Same |
| 5 | long story | `I'm filling in a form for my landlord and I forgot what name and email the bank has on file for me. Can you show me my profile with my contact details?` | Same |
| 6 | with details | `show my profile, I mainly need my registered email` | Same profile answer; email visible |
| 7 | without details | `my details` | Profile answer, or may ask a clarifying question (which details?) |
| 8 | vague | `what do you know about me` | Profile answer or clarifying question |
| 9 | follow-up | `profile`, then `and my address?` | Second turn: address answer (see 7.7) |
| 10 | different use case | `change my nickname` | Must NOT be 7.1: goes to nickname flow (7.2) |

### 7.2 Update nickname
**Outcome:** executed in chat after yes-no  ·  **Result:** `CONFIRMATION_REQUIRED` `profile_update/update_nickname` (`payload.nickName`); after Yes `BANKING_SERVICE` with `executed: true`, `routing.action: "redirect"`
**UI to show:** U6 confirm card with the new nickname, buttons Yes / No; then done notice. Refresh the cached profile nickname after Yes.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `rename` | Clarifying question: what nickname? (bubble only) |
| 2 | two words | `change nickname` | Clarifying question: what nickname? |
| 3 | casual / typos | `plz chnge my nick name 2 Tas` | `CONFIRMATION_REQUIRED`, `nickName` "Tas"; U6 |
| 4 | full sentence | `Please change my nickname to Tas.` | Same |
| 5 | long story | `I've had this account for a while and the nickname on it is boring. I want something friendlier because my family also uses my phone. Please set my nickname to Tas.` | Same; `nickName` "Tas" |
| 6 | with details | `change my nickname to DhakaDreamer` | U6 shows "DhakaDreamer" |
| 7 | without details | `I want to change my display name` | Asks what the new nickname should be |
| 8 | vague | `give me a cooler name` | Clarifying question |
| 9 | follow-up | `change nickname`, then `Tas` | Second turn: U6 with "Tas" |
| 9b | follow-up (buttons) | on U6 tap Yes: send `Yes` + `{"confirm": true}` | `BANKING_SERVICE`, `executed: true`; done notice. Tap No: `No` + `{"confirm": false}` gives `{"executed": false, "cancelled": true}`, "cancelled" notice |
| 10 | different use case | `show my profile` | Must NOT change anything: 7.1 profile answer |

Also: a nickname over 50 characters is dropped and asked for again (`CLARIFICATION_REQUIRED`), no U6.

### 7.3/7.4 Upload / change profile image
**Outcome:** gather → inline box (redirect, no bank call by the bot)  ·  **Result:** `BANKING_SERVICE` `profile_update/update_profile_image`, `payload: {"executed": false}`, `routing.action: "update_profile_image"`
**UI to show:** U8 photo box: choose photo (camera or gallery), Upload button. The app calls `PATCH auth/v1/user/profile/image`; no photo is sent in chat.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `photo` | Photo flow or clarifying question; if routed: U8 photo box |
| 2 | two words | `profile picture` | May ask a clarifying question first (view or change?); if routed: photo box |
| 3 | casual / typos | `wanna chnge my pfp` | `update_profile_image`, photo box |
| 4 | full sentence | `I want to upload a new profile picture.` | `update_profile_image`, `executed: false`; U8 photo box |
| 5 | long story | `My profile picture is still the old one from when I opened the account and it doesn't even look like me any more. I took a good photo yesterday, can you help me put it on my profile?` | Same; photo box |
| 6 | with details | `change my profile photo, I'll use the one I took today` | Same (no file handled in chat; box picks it) |
| 7 | without details | `change my picture` | Same photo box |
| 8 | vague | `update my photo` | Photo box or clarifying question (profile photo or card photo?) |
| 9 | follow-up | `profile picture`, then `change it` | Second turn: photo box |
| 10 | different use case | `change my profile info` | Must NOT be the photo flow: 7.11 profile change request or a clarifying question |

### 7.5 Update mobile number
**Outcome:** executed after code  ·  **Result:** `OTP_REQUIRED` `profile_update/update_mobile` (`payload.newPhone`, `credentialOptions: []`, `verificationStatus: "OTP_SENT"`); after the code `BANKING_SERVICE` `{"executed": true, "newPhone"}`
**UI to show:** U7 verification sheet: code only, shows the new number, Verify / Cancel. After success: done notice and send the customer to login (the bank signs the session out).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `mobile` | Clarifying question: what new number? |
| 2 | two words | `new number` | Clarifying question |
| 3 | casual / typos | `hey chnge my mobile num to 01711223344 thx` | `OTP_REQUIRED`, new number shown; U7 (code only). May ask first |
| 4 | full sentence | `I want to change my registered mobile number.` | Asks for the new number (bubble only) |
| 5 | long story | `I lost my old SIM last week and got a new one with a new number. I need the bank to use my new phone for messages. My new number is 01711223344.` | `OTP_REQUIRED` with `newPhone` 01711223344; U7 (may ask first) |
| 6 | with details | `change my mobile number to 01711223344` | `OTP_REQUIRED`; code goes to the current registered phone |
| 7 | without details | `update my phone number` | Asks for the new number |
| 8 | invalid detail | `change my mobile to 12345` | Number dropped, asked again (`CLARIFICATION_REQUIRED`); no code sheet |
| 9 | follow-up | `change my mobile number`, then `01711223344` | Second turn: U7. Enter the code in the secure sheet; app sends `Verify` + `{"otp": ...}` (done: `executed: true`, then sign out). Cancel: `cancel` + `{"confirm": false}` gives `{"executed": false, "cancelled": true}` |
| 10 | different use case | `show my registered phone numbers` | Must NOT start a change: 7.10 contacts answer |

### 7.6 Update email address
**Outcome:** executed after code  ·  **Result:** `OTP_REQUIRED` `profile_update/update_email` (`payload.newEmail`, `credentialOptions: []`); after the code `BANKING_SERVICE` `{"executed": true, "newEmail"}`
**UI to show:** U7 verification sheet: code only (sent to the current registered phone), shows the new email, Verify / Cancel; then done notice.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `email` | Clarifying question (view or change?) |
| 2 | two words | `change email` | Asks for the new email |
| 3 | casual / typos | `plz updte my emial to new@example.com` | `OTP_REQUIRED` with `newEmail`; U7 (may ask first) |
| 4 | full sentence | `I would like to update my email address.` | Asks for the new email |
| 5 | long story | `I stopped using my old email provider and I'm not getting any bank notifications any more. Please change the email on my account to new@example.com so I get the statements.` | `OTP_REQUIRED`, U7 |
| 6 | with details | `change my email to new@example.com` | `OTP_REQUIRED` (`newEmail` new@example.com); U7 |
| 7 | without details | `I need a new email on my account` | Asks for the new email |
| 8 | invalid detail | `change my email to john.example.com` | No `@`: dropped and asked again; no code sheet |
| 9 | follow-up | `update email`, then `new@example.com` | Second turn: U7. Enter the code in the secure sheet: app sends `Verify` + `{"otp": ...}`; done gives `executed: true`. Cancel as in 7.5 |
| 10 | different use case | `what email do you have for me` | Must NOT start a change: 7.1 profile answer |

### 7.7 Get address
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `profile/address`
**UI to show:** U3 address card (present and permanent address, KYC status). Test customer: addresses are not set, KYC pending; bubble says "your present address is not set".

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `address` | Address answer: not set |
| 2 | two words | `my address` | Same |
| 3 | casual / typos | `cmon whats my addr` | Same |
| 4 | full sentence | `What address does the bank have registered for me?` | Same |
| 5 | long story | `I'm filling out a loan form and need to copy my present and permanent address exactly as the bank has them, and I also want to know where my KYC stands. Can you read them out to me?` | Same; KYC pending may be mentioned |
| 6 | with details | `show my permanent address` | Same address answer |
| 7 | without details | `where do I live according to you` | Address answer |
| 8 | vague | `is my address correct` | Address answer or clarifying question |
| 9 | follow-up | `address`, then `change it` | Second turn: starts 7.8 (asks the new address) |
| 10 | different use case | `update my address to House 5, Road 2, Banani` | Must NOT be 7.7: 7.8 change flow |

### 7.8 Update address
**Outcome:** executed in chat after yes-no  ·  **Result:** `CONFIRMATION_REQUIRED` `profile_update/update_address` (`payload` has any of `presentAddress`, `permanentAddress`, `district`, `division`); after Yes `BANKING_SERVICE` `executed: true`, `routing.action: "redirect"`
**UI to show:** U6 confirm card listing the address fields that will change, Yes / No; then done notice (re-read the address from the bank to show the saved value).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `relocated` | Clarifying question: what new address? |
| 2 | two words | `change address` | Asks for the new address and which one (present or permanent) |
| 3 | casual / typos | `hey i moved, pls updte my adress to Flat 4B, Uttara` | May ask first; then U6 with the address |
| 4 | full sentence | `Please update my present address to House 5, Road 2, Banani.` | `CONFIRMATION_REQUIRED`, `presentAddress` set; U6 |
| 5 | long story | `I moved to a new flat in Uttara last month and my old address is still on file. My present address should be House 12, Road 7, Sector 4, Uttara, and my permanent address stays the same. Can you update it?` | `CONFIRMATION_REQUIRED` with `presentAddress`; U6 (may ask first) |
| 6 | with details | `change my permanent address to Village Rampur, Khulna` | U6 with `permanentAddress`; may include district |
| 7 | without details | `update my address` | Asks for the new address |
| 8 | vague | `my address is wrong` | Clarifying question |
| 9 | follow-up | `update my address`, then `House 5, Road 2, Banani` | Second turn: U6. Yes: `Yes` + `{"confirm": true}` gives `executed: true`. No: `No` + `{"confirm": false}` gives cancelled |
| 10 | different use case | `what is my address` | Must NOT change anything: 7.7 answer |

### 7.9 Submit KYC
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/kyc_submit` (prefill `occupation` only if typed)
**UI to show:** U8 KYC box: three photo slots (NID front, NID back, signature, camera or gallery), optional occupation and income fields, Submit button; `occupation` prefilled from `ui.prefill`. App calls `POST customer/v1/me/kyc`; local done/failed tile.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `KYC` | `APP_ACTION` `kyc_submit`; U8 KYC box (or a clarifying question first) |
| 2 | two words | `submit KYC` | `kyc_submit`, KYC box |
| 3 | casual / typos | `hey cud u help me do my kyc` | `kyc_submit`, KYC box |
| 4 | full sentence | `I need to submit my KYC documents.` | `kyc_submit`; no bank call; KYC box |
| 5 | long story | `My account says KYC pending and I can't use some features. I have my NID and signature ready and I want to upload them now. Can you help me finish my KYC?` | `kyc_submit`; KYC box |
| 6 | with details | `submit my KYC, my occupation is teacher` | `kyc_submit`; box with occupation "teacher" prefilled |
| 7 | without details | `verify my identity` | `kyc_submit` or a clarifying question; photo slots empty |
| 8 | vague | `my account needs documents` | Clarifying question or KYC box |
| 9 | follow-up | `KYC`, then (if asked) `yes upload documents` | Second turn: KYC box |
| 10 | different use case | `is my KYC approved` | Must NOT open the submit box: 7.7 address answer (shows KYC status PENDING) |

### 7.10 My contacts
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `profile/contacts`
**UI to show:** U2 contacts list (registered phones and emails). Test customer has none (`{"data": []}`), so bubble only, no list.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `contacts` | Contacts answer: none registered; bubble only |
| 2 | two words | `my contacts` | Same |
| 3 | casual / typos | `which phone nos r registerd` | Same |
| 4 | full sentence | `Which phone numbers and emails are registered on my account?` | Same |
| 5 | long story | `The bank keeps sending my codes to a number I don't recognise. Before I call anyone, can you list every phone number and email you have registered for me?` | Same |
| 6 | with details | `show my registered email and phone` | Same (may show profile data if routed to 7.1) |
| 7 | without details | `list my numbers` | Same |
| 8 | vague | `where do you contact me` | Contacts answer or clarifying question |
| 9 | follow-up | `contacts`, then `make the second one primary` | Second turn: starts 7.13 (app action `contact_priority_change`) |
| 10 | different use case | `add my friend as a beneficiary` | Must NOT be 7.10 (it is the customer's own contacts): beneficiary flow |

### 7.11 Profile change — submit
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/profile_change_request` (prefill `fieldName`, `requestedValue`, `reason` only for what was typed)
**UI to show:** U8 form box: detail to change (mobile, email, NID, legal name, date of birth), new value, reason, Submit request. After the button: U7 code. App calls `POST service-request/v1/profile-changes`; local done/failed tile.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `rename` | Ambiguous (nickname or legal name): may ask a clarifying question first |
| 2 | two words | `legal name` | Clarifying question or `profile_change_request` box |
| 3 | casual / typos | `i got married need 2 chnge my legal name pls` | `profile_change_request`; box with `fieldName` legal name |
| 4 | full sentence | `I want to request a change to my date of birth.` | `profile_change_request`; box with `fieldName` date of birth |
| 5 | long story | `My legal name on the account was misspelled when I opened it, it says Taslim but my NID says Tasleem. I have been having trouble with forms because of this. Please raise a request to correct my name to Tasleem.` | `profile_change_request`; prefill `fieldName` legal name, `requestedValue` Tasleem, `reason` the misspelling |
| 6 | with details | `request to change my date of birth to 12 March 1990, it was entered wrong` | Box prefilled: date of birth, the new value, reason |
| 7 | without details | `I want to change a detail on my profile that is locked` | `profile_change_request` or a clarifying question; fields empty |
| 8 | vague | `fix my details` | Clarifying question (which detail?) |
| 9 | follow-up | `request a profile change`, then `my NID number` | Second turn: box with `fieldName` NID |
| 10 | different use case | `change my nickname to Tas` | Must NOT be 7.11: 7.2 nickname yes/no |

### 7.12 Profile change — list
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `profile/profile_change_requests`
**UI to show:** U2 requests list with status. Test customer has none (`{"requests": []}`): bubble only.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `requests` | May ask a clarifying question first; if answered: no profile-change requests |
| 2 | two words | `profile requests` | No requests found; bubble only |
| 3 | casual / typos | `did my profile chnge get aproved` | Same |
| 4 | full sentence | `Has my profile change request been processed yet?` | Same |
| 5 | long story | `Two weeks ago I asked the bank to correct my legal name because of a spelling mistake. Nobody has told me anything since then. Can you check if the request was approved or is still pending?` | Same |
| 6 | with details | `status of my name change request` | Same |
| 7 | without details | `any update on my request` | May ask which request; if answered: none |
| 8 | vague | `what happened to my profile thing` | Clarifying question or none found |
| 9 | follow-up | `any update on my request`, then `the profile one` | Second turn: no profile-change requests |
| 10 | different use case | `request a change to my legal name` | Must NOT be a list: 7.11 box |

### 7.13 Contact priority — submit
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/contact_priority_change` (prefill `reason` only if typed)
**UI to show:** U8 box: the registered phones and emails to choose the primary one (filled from the app's data), reason field, Submit request. After the button: U7 code. App calls `POST service-request/v1/contact-priority`; local done/failed tile.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `primary` | May ask a clarifying question first; if routed: box |
| 2 | two words | `primary contact` | `contact_priority_change`, box |
| 3 | casual / typos | `plz mak my 2nd num the primery` | `contact_priority_change`, box |
| 4 | full sentence | `I want to change my primary contact number.` | `contact_priority_change`; U8 box with picker |
| 5 | long story | `I have two phone numbers registered, an old one and my new one. The bank keeps calling the old one that I don't use any more. Please make my new number the primary contact so notifications go there.` | `contact_priority_change`; `reason` prefilled |
| 6 | with details | `change my primary contact because I lost my old SIM` | Box with `reason` prefilled |
| 7 | without details | `change which phone you contact me on` | `contact_priority_change` or clarifying question |
| 8 | vague | `use my other number` | Clarifying question or box |
| 9 | follow-up | `primary contact`, then `because my old number is closed` | Second turn: box with `reason` |
| 10 | different use case | `show my primary contact change requests` | Must NOT open the box: 7.14 list |

### 7.14 Contact priority — list
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `profile/contact_priority_requests`
**UI to show:** U2 requests list with status. Test customer has none (`{"requests": []}`): bubble only.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `status` | Likely a clarifying question (status of what?); bubble only |
| 2 | two words | `contact requests` | No primary-contact requests; bubble only |
| 3 | casual / typos | `did my primery contact chnge go thru` | Same |
| 4 | full sentence | `Can you show me the status of my primary-contact change requests?` | Same |
| 5 | long story | `Last week I asked to make my new phone number my primary contact, but I haven't heard anything and the codes still go to my old number. Could you check whether that request is pending or approved?` | Same |
| 6 | with details | `status of my request to change primary phone` | Same |
| 7 | without details | `any update on my contact change` | Same, or asks which request |
| 8 | vague | `what happened with my number change` | Clarifying question or none found |
| 9 | follow-up | `any update on my request`, then `the primary contact one` | Second turn: no requests |
| 10 | different use case | `make my second number primary` | Must NOT be a list: 7.13 box |

## FAILED_TRANSFER

Test customer has 3 transactions (one is a 5,000 bKash debit), no disputes, no complaints. The bot never submits a dispute itself.

### 8.1 Transaction history
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `polygon_services/transaction_history`
**UI to show:** U4 transaction list: date, description, amount (poisha ÷ 100), direction. Includes the 5,000 bKash debit. One account, so no picker.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `history` | Transaction list (3 rows); U4 |
| 2 | two words | `my transactions` | Same |
| 3 | casual / typos | `show me wat i spent recntly` | Same |
| 4 | full sentence | `Can you show me my recent transactions?` | Same |
| 5 | long story | `I'm trying to find out where my money went this month. I think I sent about 5000 taka through bKash last week but I'm not sure. Can you show me my recent transactions so I can check?` | Same; the 5,000 bKash debit in the list |
| 6 | with details | `show my transactions from 1 September to 30 September` | List filtered by date (`dateFiltered: true`); may be fewer rows or empty |
| 7 | without details | `statement` | Same list (default recent), or asks which period |
| 8 | vague | `what happened to my money` | Transaction list or clarifying question |
| 9 | follow-up | `show my transactions`, then `only the bKash one` | Second turn: list or a bubble answer about the bKash transaction |
| 10 | different use case | `the 5000 I sent to bKash never reached, raise a dispute` | Must NOT be 8.1: 8.2 dispute |

### 8.2 Raise dispute
**Outcome:** gather → inline box  ·  **Result:** `BANKING_SERVICE` `service_requests/raise_dispute`, `payload.executed: false`, `routing.action: "raise_dispute"`. While gathering: `CLARIFICATION_REQUIRED` (`payload.pending.service == "raise_dispute"`, missing `remarks`) or `TRANSACTION_SELECTION_REQUIRED` (up to 8 transactions)
**UI to show:** U5 transaction picker when asked (send `Selected` + `{"transactionId": ...}`, no `category`/`service`); U8 dispute box prefilled with `accountNumber`, `transactionReferenceNo`, `remarks`, button Submit dispute, then U7 code. The bot never POSTs; the app does (`POST service-request/v1/disputes`).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `dispute` | Asks what went wrong (`CLARIFICATION_REQUIRED`, pending `raise_dispute`); optional dispute box |
| 2 | two words | `transaction issue` | Asks what the issue is, or transaction picker |
| 3 | casual / typos | `my money got cut but he didnt get it pls help` | Picker or a question; later summary |
| 4 | full sentence | `I want to raise a dispute for a payment that failed.` | Account auto-picked (one account); asks which transaction (picker) or what went wrong |
| 5 | long story | `On Sunday I sent 5000 taka to my brother through bKash. The money was deducted from my account but he says he never received it. I've waited three days and nothing. Please raise a dispute for it.` | Matches the 5,000 bKash debit; summary with `remarks` and `transactionSummary`, `executed: false`, `routing.action: "raise_dispute"`; U8 box prefilled (may ask a question first) |
| 6 | with details | `raise a dispute for my 5000 taka bKash transaction, money deducted but not received` | Summary as above; box prefilled (`accountNumber` 0056, reference, `remarks`) |
| 7 | without details | `i want to raise a dispute` | Asks for the transaction (picker with the 3 transactions) and/or what went wrong |
| 8 | vague | `something is wrong with a payment I made` | Clarifying question or transaction picker |
| 9 | follow-up | `raise a dispute`, then in the picker tap the 5,000 bKash row: `Selected` + `{"transactionId": ...}`, then (if asked) `money was deducted but never received` | Final: dispute summary, `executed: false`; U8 dispute box prefilled; Submit dispute then code in secure sheet |
| 10 | different use case | `show my disputes` | Must NOT raise one: 8.3 list, "no disputes" |

### 8.3 List disputes
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `service_requests/disputes`
**UI to show:** U2 disputes list (reference, status, date). Test customer has none (`{"disputes": []}`): bubble says there are no open disputes; bubble only.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `disputes` | No disputes; bubble only |
| 2 | two words | `my disputes` | Same |
| 3 | casual / typos | `any open dispuites` | Same |
| 4 | full sentence | `Can you show me the list of disputes I have raised?` | Same |
| 5 | long story | `A while ago I reported a payment that never reached my friend, and I can't remember if the bank ever opened a case. Can you check if I have any disputes and what their status is?` | Same |
| 6 | with details | `status of my dispute for the 5000 taka bKash payment` | Same: no disputes |
| 7 | without details | `dispute status` | Same |
| 8 | vague | `what happened to my case` | Disputes answer or clarifying question |
| 9 | follow-up | `any disputes?`, then `and my complaints?` | Second turn: 8.5 answer, no complaints |
| 10 | different use case | `I want to dispute a transaction` | Must NOT be a list: 8.2 gather |

### 8.4 Submit complaint
**Outcome:** executed in chat after yes-no  ·  **Result:** `CONFIRMATION_REQUIRED` `support/submit_complaint` (`payload.category`, `payload.description`); after Yes `BANKING_SERVICE` with `executed: true`, `routing.action: "redirect"`. If the text is missing: `CLARIFICATION_REQUIRED` with `payload.pending.service == "submit_complaint"` (missing `description`)
**UI to show:** U8 complaint box (type, details, Send) when pending; U6 confirm card (complaint type and text) with Yes / No; done notice that it appears under My Tickets. Complaint box sends a direct `support/submit_complaint` with `{"description", "category"}`.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `complain` | Asks what the complaint is (pending `submit_complaint`); complaint box |
| 2 | two words | `bad service` | Asks for details, or U6 with a short description |
| 3 | casual / typos | `ur app is soo slow wanna complain` | U6 with category `MOBILE_APP_TECHNICAL` likely (may ask first) |
| 4 | full sentence | `I would like to file a complaint about the mobile app.` | Asks what happened, or U6 |
| 5 | long story | `For two weeks the mobile app has hung every time I try to pay a bill. Yesterday it froze in the middle of a payment and I wasn't sure if the money went. I want this recorded as a complaint.` | `CONFIRMATION_REQUIRED` with app-related category (e.g. `MOBILE_APP_TECHNICAL`) and a description; U6 |
| 6 | with details | `submit a complaint: the app hangs when I pay a bill` | `CONFIRMATION_REQUIRED`; description from the message; U6 |
| 7 | without details | `I want to complain about something` | Asks what it is about; complaint box shown (pending) |
| 8 | vague | `I'm not happy` | Clarifying question (bubble only, `payload` null) or asks what the complaint is |
| 9 | follow-up | `I want to make a complaint`, then `the ATM did not give me cash but charged my account` | Second turn: U6 with category (e.g. `TRANSACTION` or `CARD`) and description. Yes: `Yes` + `{"confirm": true}` gives `executed: true`. No: `No` + `{"confirm": false}` gives cancelled |
| 10 | different use case | `show my complaints` | Must NOT file one: 8.5 list, "no complaints" |

### 8.5 My complaints
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `polygon_services/my_tickets`
**UI to show:** U2 tickets list (reference, status, date). Test customer has none (`{"complaints": []}`): bubble only.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `complaints` | No complaints; bubble only |
| 2 | two words | `my tickets` | Same |
| 3 | casual / typos | `any update on my complaint pls` | Same |
| 4 | full sentence | `I want to check the status of my complaint.` | Same |
| 5 | long story | `Last week I complained to the bank that my ATM card didn't work and the machine kept my money. I was given no reference and I haven't heard back. Can you show me my complaints and where they stand?` | Same |
| 6 | with details | `status of my complaint about the ATM card` | Same |
| 7 | without details | `ticket status` | Same |
| 8 | vague | `did anyone look at my problem` | Complaints answer or clarifying question |
| 9 | follow-up | `my complaints`, then `file a new one about slow app` | Second turn: starts 8.4 (U6 or asks for details) |
| 10 | different use case | `I want to file a complaint` | Must NOT be a list: 8.4 flow |

## FEES

Test customer notes: dev environment returns Tk 0 charge / Tk 0 VAT for every type, so the total equals the amount. Valid transfer types: bKash, Nagad, Rocket, Upay, own account, City Bank account, other bank. The quote is read-only: nothing is sent.

### 10.1 Transaction charge quote
**Outcome:** answered in chat (asks for missing type and/or amount first)  ·  **Result:** `BANKING_SERVICE` `fees/fee_quote` (+ `routing.action: "start_transfer"` with `routing.transfer.prefill.amount` when the type maps to a transfer; otherwise `redirect`). Missing details: `CLARIFICATION_REQUIRED` (category/service null)
**UI to show:** Fee quote card (U3): principal, charge, VAT, total in taka (payload is poisha, divide by 100). With `start_transfer`: a **Continue to send** button that opens the transfer box (U8) for the type in `routing.transfer`, amount prefilled. Clarification: bubble only (U1), no box (`payload.pending` is not a complaint/dispute).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `fees` | Asks which transfer type and what amount (may list the types). Bubble only |
| 2 | two words | `bkash charge` | Type known (bKash), asks for the amount. Bubble only |
| 3 | casual / slang | `hw much to send 5k thru nagad lol` | Quote for Nagad, Tk 5,000 (k understood): charge 0, total 5,000. Continue to send, amount 5,000 |
| 4 | full sentence | `What is the fee for a bank transfer of 20000 taka to another bank?` | Maps to other bank. Quote card for Tk 20,000, Continue to send (other-bank transfer box, amount 20,000) |
| 5 | long story | `I'm sending money to my brother next week for his tuition. He banks with another bank, so I will use NPSB. I want to send 1 lakh taka and need to know what it will cost me before I decide.` | Quote for other bank, Tk 100,000 (lakh understood). Card plus Continue to send with amount 100,000 |
| 6 | with details | `how much does it cost to send 500 taka via bKash` | Quote card: principal 500, charge 0, VAT 0, total 500. Continue to send (bKash box, amount 500) |
| 7 | without details | `what are your fees` | Asks for transfer type and amount. No card, no button |
| 8 | vague | `is there any charge` | Asks for type and amount (may list the options). No card |
| 9 | follow-up, answering the question | send `what are your fees`, then `nagad`, then `1500` | Turn 2: asks for the amount. Turn 3: quote card for Nagad, Tk 1,500 + Continue to send |
| 9b | follow-up, change a detail | after a bKash 500 quote send `and for nagad?` | New quote for Nagad, Tk 500 (same amount kept) |
| 9c | follow-up, go ahead | after a quote send `ok send it` | Moves into the transfer flow for that type and amount (asks for missing details such as recipient, or shows the transfer box, per TRANSFER.md). No money moves in chat |
| 10 | different use case | `I was charged 25 taka extra on my last transfer` | NOT a fee quote: a charge already taken is a dispute/complaint flow (may ask which transaction or show the dispute box). No fee card |
| 10b | different use case | `send 500 taka to bkash` | NOT a fee quote: a transfer request (asks for the number, then transfer box/summary) |

---

## LOST_OR_STOLEN_CARD

Test customer has one debit card ending 0293 (id 45), so it is used automatically (no card picker). Warning: completing the freeze flow with a real code really blocks the card; restore it outside chat afterwards. Rule: if the customer says it was lost/stolen WITHOUT asking to block, the bot goes to 12.1 (report + replace box); if they ask to block/freeze, it goes to 12.2.

### 12.1 Report lost/stolen card
**Outcome:** gather → inline box (no bank call by the bot)  ·  **Result:** `BANKING_SERVICE` `card_requests/report_lost_card`, `payload {cardId, cardLast4, reasonCode, executed: false}`, `routing.action: "report_lost_card"`
**UI to show:** Caution box (U8): card preselected (0293), reason picker (lost, stolen, damaged, expired, other; preselected from `reasonCode` when said), warning that the card is closed for good and a replacement issued. Buttons **Report and replace** (then U7: code + PIN or password; app calls the replacement request) and **Freeze instead** (sends the message `Freeze my card`). Card picker (U5) first only if several cards.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `stolen` | Most likely the caution box with reason Stolen; may ask a clarifying question first |
| 2 | two words | `card lost` | Caution box, card 0293, reason Lost preselected |
| 3 | casual / typos | `omg i lst my card at the mall!!` | Caution box, reason Lost. Not a freeze (no block asked) |
| 4 | full sentence | `My debit card was stolen yesterday and I want to report it.` | Caution box, reason Stolen preselected, Report and replace / Freeze instead |
| 5 | long story | `I went to Gulshan market yesterday evening and my wallet was stolen with my debit card inside. I only noticed this morning. I don't think anyone used it yet, but I don't want to take the risk, and I would like to get a replacement card.` | Caution box, card 0293, reason Stolen, same buttons. Bubble explains closure is permanent and offers freezing as the gentler option |
| 6 | with details | `report my debit card ending 0293 as lost` | Box with card 0293 and reason Lost prefilled |
| 7 | without details | `I want to report a lost card` | Box with the only card preselected; reason picker empty (customer picks) |
| 8 | vague | `my card isn't working` | NOT a report and NOT a freeze: asks what is happening with the card (may list: lost/stolen, freezing, card details). `CLARIFICATION_REQUIRED`, no box |
| 9 | follow-up, button | tap **Freeze instead** (app sends `Freeze my card`) | Switches to the freeze flow (12.2): may ask why first, or goes to the Yes/No card |
| 9b | follow-up, button | tap **Report and replace** | App shows the secure sheet (code + PIN or password); the app makes the call, the bot is not told. Enter the code in the secure sheet, never in the chat |
| 10 | different use case | `reset my card PIN` | NOT lost/stolen: `APP_ACTION` `card_pin_reset` (Reset PIN box, card 0293 preselected) |
| 10b | different use case | `close my card` | NOT lost/stolen: `APP_ACTION` `card_close` (close-card box with a permanent-closure warning) |

### 12.2 Freeze card immediately
**Outcome:** executed in chat after yes/no, then a code  ·  **Result:** `CONFIRMATION_REQUIRED` → `OTP_REQUIRED` → `BANKING_SERVICE`, all `card_services/frezz_unfrezz` (final payload `executed: true, cardLast4 0293, status BLOCKED`, `routing.action: "redirect"`)
**UI to show:** U1 asks the reason if missing → Confirm card U6 (card ending 0293 + reason; Yes / No; no code sent yet) → Verification sheet U7 (code + PIN or password; Verify / Cancel) → done notice "card ending 0293 is frozen". Card picker (U5) only if several cards.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `freeze` | Block asked but no reason: asks why (`CLARIFICATION_REQUIRED`), no code sent |
| 2 | two words | `block card` | Same: asks why |
| 3 | casual / slang | `plz freeze my card its stolen!!` | Reason given, so straight to Yes/No card (card 0293, reason in the customer's words) |
| 4 | full sentence | `I need you to block my debit card immediately as I lost it yesterday.` | `CONFIRMATION_REQUIRED`, card ending 0293, reason "lost it yesterday" |
| 5 | long story | `Hello, I was at a restaurant last night and when I got home I saw an SMS that my debit card was used for a purchase I did not make. Someone must have copied it. Please block it right now before they use it again.` | `CONFIRMATION_REQUIRED` with the misuse story as the reason. No code yet |
| 6 | with details | `Freeze my card ending 0293, I lost it at the airport` | Yes/No card for 0293 with reason "lost it at the airport" |
| 7 | without details | `Freeze my card` | Asks why; then send `it was stolen` → Yes/No card with that reason |
| 8 | vague | `my card isn't working` | No freeze: asks what is wrong (never a block just from a vague problem). `CLARIFICATION_REQUIRED` |
| 10 | different use case | `unfreeze my card` | NOT a freeze: `APP_ACTION` `card_unfreeze` (see "Unfreeze" below) |
| 10b | different use case | `what's my balance` (while the code sheet is open) | Leaves the freeze step, nothing frozen, answers the balance |

Full flow (the follow-up turns, type 9):

| # | Step | The app sends | Expect |
|---|---|---|---|
| 9a | tap Yes | `Yes` + `{"confirm": true}` | `OTP_REQUIRED`, `verificationStatus: OTP_SENT`, `credentialOptions [pin, password]`. Verification sheet opens |
| 9b | submit sheet | `Verify` + `{"otp": "<code>", "pin": "<PIN>"}` (or `password`, only one of them). Type them only in the secure sheet | `BANKING_SERVICE` `executed: true`, `status: BLOCKED`, card ending 0293. Done notice |
| 9c | tap No (instead of Yes) | `No` + `{"confirm": false}` | `BANKING_SERVICE` `executed: false, cancelled: true`. Nothing frozen |
| 9d | tap Cancel on the sheet | `cancel` + `{"confirm": false}` | `executed: false, cancelled: true`. Nothing frozen |
| 9e | wrong code | `Verify` with a wrong code | `OTP_REQUIRED`, `OTP_INCORRECT`, `attemptsRemaining`; sheet shows an error, stays open |
| 9f | wrong PIN/password | `Verify` with a right code, wrong PIN | `OTP_REQUIRED`, `INVALID_CREDENTIALS` (code still valid; code field hidden) |
| 9g | typed yes | type `yes go ahead` instead of tapping | Same as tapping Yes |

### — Unfreeze (not a freeze)
**Outcome:** app action → inline box (never turned into a freeze)  ·  **Result:** `APP_ACTION` `app_actions/card_unfreeze`, `routing.action: "card_unfreeze"`
**UI to show:** Inline box (U8): frozen cards, the one in `ui.prefill.cardLast4` preselected, each with **Unfreeze**; then U7 (code + PIN or password). If the card is not frozen the list may be empty.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `unfreeze` | Unfreeze box (may ask which card first) |
| 2 | two words | `unblock card` | Unfreeze box |
| 3 | casual | `pls reactivate my card` | Unfreeze box |
| 4 | with details | `Please unfreeze my debit card ending 0293` | Unfreeze box with card 0293 preselected (`cardLast4` prefill) |
| 5 | different use case | `freeze my card` | Not unfreeze: the freeze flow (12.2) |

---

## MINI_STATEMENT

Test customer has one savings account (0056, no picker needed) and 3 transactions (one is a 5,000 bKash debit, shown as ৳5,000.00, with date and direction). No credit card. A date range with no transactions gives an "nothing found" bubble and no list.

### 13.1 Transaction list
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `polygon_services/transaction_history` (date range adds `dateFiltered: true`)
**UI to show:** Transaction list U4 (date, title, ± amount, icon; poisha divided by 100). Account picker U5 first only if several accounts. Empty result: bubble only. Do not show a row's running balance as the account balance.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `statement` | Transaction list with the 3 transactions |
| 2 | two words | `last transactions` | Same list |
| 3 | casual / typos | `trnsactions pls` | Same list |
| 4 | full sentence | `Please show me my recent transactions.` | List incl. the ৳5,000 bKash debit |
| 5 | long story | `Hello team, I am reconciling my monthly expenses and I think there may be a mistake in my account. Could you please show my latest transactions so I can check each one?` | List of the 3 transactions |
| 6 | with details | `show my transactions from 1 September to 30 September` | List filtered to that range (`dateFiltered: true`); the bKash debit of late September should appear |
| 6b | with details | `show my transactions for last week` | Date-filtered list; may be empty depending on dates ("nothing found" bubble) |
| 7 | without details | `show transactions` | Single account is auto-picked, list shown directly (no question) |
| 8 | vague | `what happened with my money` | May show the list or ask what to see (balance or transactions); never a made-up answer |
| 9 | follow-up | after the list send `and for last month?` | May show a date-filtered list for last month (or a "nothing found" bubble) |
| 9b | combined ask | `whats my balance and also show my last transactions` | Bubble says balance Tk 90,000.00 and the list follows (balance comes from the account, not a row) |
| 10 | different use case | `what's my balance` | NOT a list: `account_info/balance` detail card |
| 10b | different use case | `the 5000 bkash transaction failed, raise a dispute` | NOT a list: dispute flow (`raise_dispute`) |

### 13.2 Account transactions
**Outcome:** answered in chat (chat uses the same service as 13.1)  ·  **Result:** `BANKING_SERVICE` `polygon_services/transaction_history`
**UI to show:** Transaction list U4, same as 13.1.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Transactions` | List of the 3 transactions |
| 2 | two words | `account activity` | Same list |
| 3 | casual | `hey whats my account transactions for today?` | List (or "nothing found" if none today); date-filtered |
| 4 | full sentence | `I want to check all the transactions in my savings account.` | List for account 0056 |
| 5 | long story | `I'm tracking my expenses for the month. I paid a few bills with my bKash wallet and I'd like to see everything that went through my account, so I can match it with my own notes.` | List incl. the bKash debit |
| 6 | with details | `show transactions of my account ending 0056` | List for 0056 (account matched, no picker) |
| 7 | without details | `show my account transactions` | Auto-picks the only account, list shown |
| 8 | vague | `my account history` | List, or a short question on what to show |
| 9 | follow-up | after the list send `only bKash ones` | May answer from the list or ask what to show; no new box |
| 10 | different use case | `how many accounts do I have` | NOT a list: accounts list (`account_info`) |

### 13.3 Credit card statement
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `card_info/credit_card_statement`
**UI to show:** Statement card (U3/U2) only when `payload.creditCard` is not null. This customer has NO credit card: payload `creditCard: null`, bubble says "You don't have a credit card with Polygon Bank", no statement card, bubble only.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Statement` | Ambiguous with 13.1: may show the transaction list or ask which statement; no error |
| 2 | two words | `credit statement` | Bubble: no credit card. No card shown |
| 3 | casual / typos | `i wanna see my credet card statment plz` | Bubble: no credit card |
| 4 | full sentence | `Can you please provide my credit card statement for last month?` | Bubble: no credit card (month prefilled as last month) |
| 5 | long story | `I'm trying to keep track of my spending for the month and I want to check whether any transactions on my credit card are still unbilled before I pay. Could you show me the statement for this month?` | Bubble: no credit card |
| 6 | with details | `unbilled statement of my credit card for October` | Bubble: no credit card (would use month 2026-10, unbilled) |
| 6b | with details | `billed statement for my credit card, September` | Bubble: no credit card |
| 7 | without details | `show my credit card statement` | Same, no questions (month defaults to current, unbilled) |
| 8 | vague | `my card statement` | May treat it as card statement (no credit card) or transactions, or ask which card; never a made-up statement |
| 9 | follow-up | after the answer send `what about last month?` | Same answer (no credit card) |
| 10 | different use case | `pay my credit card bill` | NOT a statement: `APP_ACTION` `credit_card_pay` |
| 10b | different use case | `show my recent transactions` | NOT a card statement: 13.1 transaction list |

### 13.4 Expense tracker by category
**Outcome:** not offered (no backend)  ·  **Result:** no category breakdown is ever returned; usually `CLARIFICATION_REQUIRED` (may instead fall back to the plain transaction list)
**UI to show:** Bubble only (U1). No box, no chart, no buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `expenses` | Bubble only; may ask what they want (transactions or balance). No breakdown |
| 2 | two words | `spending breakdown` | Bubble only, no category chart |
| 3 | casual | `where is all my money going lol` | Bubble only; may offer the transaction list |
| 4 | full sentence | `Show me my spending by category for this month.` | Bubble says it can't do category breakdown (or asks what else); no card |
| 5 | long story | `I want to cut my monthly costs. Can you split my spending into food, transport, bills and shopping so I can see where I overspend?` | Bubble only, no category split; may suggest looking at recent transactions |
| 6 | with details | `how much did I spend on food in September` | No category total invented; bubble only (or a plain transaction list) |
| 7 | without details | `expense tracker` | Bubble only |
| 9 | follow-up | after the bubble send `ok then show my transactions` | 13.1 transaction list (U4) |
| 10 | different use case | `show my transactions` | That is 13.1: a plain list, not the tracker |

---

## GREETING

### — Greeting and small talk
**Outcome:** answered in chat (no bank call; nothing executed)  ·  **Result:** greeting/help: `CLARIFICATION_REQUIRED` (`category`/`service` null, `payload` null); thanks: `KB_ANSWER`, `payload {grounded: false, hitCount: 0, sources: null}`
**UI to show:** U1 text bubble only. No box, no buttons, no source line. The only optional extra is the app's first-turn suggestion chips (Balance, My cards, Recent transactions, Transfer money, Fees), which just send their label as a normal message.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `hi` | Greeting plus "what can I help you with?" (may list what it can do). `CLARIFICATION_REQUIRED` |
| 2 | two words | `good morning` | Greeting back and asks what they need. Bubble only |
| 3 | casual / slang | `yo wassup` | Friendly greeting and asks what they need. Bubble only |
| 4 | full sentence | `Hello, how are you today?` | Polite greeting, asks how it can help. English reply |
| 5 | long story | `Hi there, I hope you're doing well. I just joined Polygon Bank last month and I'm still learning how things work, so I may ask a few questions today.` | Welcomes them and asks what they want to do. No bank call |
| 6 | thanks | `thank you so much` | Polite "you're welcome, I'm here to help" closing. `KB_ANSWER`, ungrounded |
| 6b | thanks, short | `thx` | Same polite closing |
| 7 | help, no details | `help` | Asks what exactly they need; may list what the bot can do. `CLARIFICATION_REQUIRED` |
| 8 | vague | `can you help me with something?` | Asks what the something is. Bubble only |
| 9 | follow-up | send `hi`, then tap the Balance chip (sends `Balance`) or type `balance` | Second turn is a normal balance answer (Tk 90,000 detail card) |
| 9b | follow-up | after a balance answer send `thanks` | Polite closing, no new card |
| 10 | different use case | `hi, what's my balance?` | NOT small talk: the balance answer (detail card), maybe with a greeting |
| 10b | different use case | `hello I lost my card` | NOT small talk: lost-card flow (12.1) |

---

## FALLBACK

### — General bank knowledge and off-topic
**Outcome:** answered in chat  ·  **Result:** bank product/policy questions: `KB_ANSWER` grounded (`payload {grounded: true, hitCount, sources}`); off-topic, maths, jokes: `KB_ANSWER` polite decline (`grounded: false`, `sources: null`); abuse, gibberish, vague: `CLARIFICATION_REQUIRED` (payload null)
**UI to show:** U1 text bubble only for all of them: no boxes, buttons or chips. A grounded answer may show an optional small "Source: ..." line. After two clarifying questions in a row the app may offer "Talk to an agent" (counted by `result.type`).

General bank knowledge (grounded answers from the uploaded knowledge base):

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Help` | Asks what exactly they need (clarification); no answer from documents |
| 2 | two words | `savings account` | Likely explains savings accounts from the knowledge base, or asks what they want to know |
| 3 | casual | `whats a dps lol` | Short explanation from the knowledge base (`KB_ANSWER`, grounded) |
| 4 | full sentence | `What is a savings account?` | Grounded answer; sources list (e.g. the knowledge base PDF) |
| 5 | long story | `I am thinking of starting a small business and want to keep my savings safe and earn some profit. Can you explain what fixed deposits are and how they differ from a regular savings account?` | Grounded explanation of both. Bubble only |
| 6 | question with specifics | `What are the requirements to open a savings account?` | Grounded answer with the documents/eligibility from the knowledge base (known gap: may sometimes ask a clarifying question instead) |
| 7 | vague | `tell me about your cards` | General card information from the knowledge base, or asks what they want to know; not the customer's own card list |
| 8 | follow-up | after an answer send `and what about a current account?` | Another grounded or clarifying answer; stays text only |
| 10 | different use case | `show me my savings account balance` | NOT general knowledge: the balance answer for this customer (detail card) |

Off-topic, maths, jokes, slang, abuse, gibberish, thanks and different-use-case checks (all bubble only, no boxes):

| # | Type | Send | Expect |
|---|---|---|---|
| 11 | off-topic | `who is the prime minister of japan` | Polite decline: only helps with Polygon Bank account and services. `KB_ANSWER`, `grounded: false` |
| 12 | maths | `what is 12 * 12` | Same polite decline (no answer to the sum) |
| 13 | maths, long | `Can you help me with my homework? What is the square root of 144 plus 30 percent of 500?` | Polite decline, no calculation |
| 14 | unrelated | `what's the weather in Dhaka today` | Polite decline |
| 15 | unrelated | `recommend a good movie for tonight` | Polite decline |
| 16 | joke request | `tell me a joke` | No joke: decline or asks what they need from the bank. Bubble only |
| 17 | slang | `sup bro gimme something cool` | Does not play along: friendly redirect / asks what they need. Bubble only |
| 18 | slang | `lol` | Asks what they need (or short friendly reply). Bubble only |
| 19 | abuse | `you are the worst bot ever` | Does not engage with the insult; asks what they need, may list what it can help with. `CLARIFICATION_REQUIRED` |
| 20 | abuse | `you are useless, shut up` | Same: calm "what do you need help with?" |
| 21 | gibberish | `asdfgh` | "What exactly do you need help with?" `CLARIFICATION_REQUIRED` |
| 22 | gibberish | `??? qwe zxc` | Asks what they need. No box |
| 23 | thanks | `thanks a lot` | Polite closing (`KB_ANSWER`, ungrounded). No card |
| 24 | different use case | `file a complaint about your service` | NOT fallback: complaint flow (asks for details; complaint box, then Yes/No card) |
| 25 | different use case | `reset my card PIN` | NOT fallback: `APP_ACTION` `card_pin_reset` box |
| 26 | different use case | `what are the fees to send 500 taka via bkash` | NOT fallback: fee quote card (10.1) |
| 27 | different use case | `freeze my card, it was stolen` | NOT fallback: freeze flow (12.2) |

## TRANSFER

Sources: `handoffs/TRANSFER.md`, `COMMON.md` §3–§11, `app/banking/ui_actions.py`. The bot NEVER moves money: transfers end in a summary (`executed: false`) and the app's own transfer box does the rest (customer taps Send, enters code and transaction PIN in the secure sheet; the bot is not told the outcome).

Shared rules for the transfer rows 14.1, 14.2, 14.3, 14.14:
- Missing detail: the bot asks in chat: `CLARIFICATION_REQUIRED` with `payload.pending` (`category`, `service`, `subservice`, `missingFields`); UI is the text bubble only (U1), no box yet. The customer answers by typing a plain message (no `category`/`service`, no button).
- Complete (destination type + number + amount): `BANKING_SERVICE` `transfer/<service>/<subservice>`, `payload` = `{accountNumber | walletNumber, amount, formattedAmount, executed: false}`, `routing.action` = `<subservice>_transfer` → app opens the U8 transfer box prefilled from `payload`. Amount is taka as a plain number string: `500` → 500, `1,250` → 1250, `5k` → 5000, `2 lakh` → 200000 (box shows ৳5,000 etc.). The bot does not check balance or limits; the app does. Numbers are passed as the customer wrote them.
- A destination TYPE must come from the customer's own words (own account, Polygon account, a bank name, a wallet name) or from a number they typed; otherwise the bot asks where to send.
- Bank name, branch, transfer type (BEFTN/NPSB/RTGS), from-account and note are never prefilled; the customer fills them in the box.

### 14.1 Own account transfer
**Outcome:** gather → inline box (the bot never executes)  ·  **Result:** `BANKING_SERVICE` `transfer/bank_transfer/own_account` (+ `routing.action: own_account_transfer`)
**UI to show:** U8 transfer box: from-account picker, to-account (customer's other accounts), amount (prefilled from `payload.amount`), note; button Send. NOTE: the test customer has ONE account (0056), so the bot answers that moving money between own accounts is not possible (`BANKING_SERVICE`, `executed: false`, no `routing.action`): bubble only, no box. With two or more accounts it asks which account should receive the money (`ACCOUNT_SELECTION_REQUIRED`, U5 picker) before the box (handoff gap 2 says it may also ask even with one account; either way no box for this customer).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `transfer` | Asks where to send the money (destination type not said); `CLARIFICATION_REQUIRED`, bubble only, no box |
| 2 | two words | `own transfer` | Understood as own-account transfer; may ask for the amount first; for taslim ends with "only one account" bubble, no box |
| 3 | casual / typos | `move 5k btwn my own accnts` | Own-account transfer, amount 5000 read; taslim: "only one account" bubble (`executed: false`), no box |
| 4 | normal sentence | `I want to move 1,250 taka to my other account.` | Own-account, amount 1250; taslim: bubble says no other account to move to; no box |
| 5 | long story | `Salary came into my savings account this morning but I keep my rent money in my other account. Could you please move 2 lakh taka between my own accounts today? I'll pay the landlord tomorrow.` | Own-account, amount 200000 read; taslim: "only one account" bubble, nothing executed. (Customer with 2+ accounts: picker, then box with 200000 prefilled) |
| 6 | with details | `transfer 500 taka from my savings to my other account` | amount 500 captured; own-account answer as above (box prefilled with `amount: 500` for a customer with 2+ accounts) |
| 7 | without details (tricky) | `send 500 taka` | No destination said: bot asks where to send it (own account, Polygon account, other bank, bKash/Nagad/Rocket/Upay); `CLARIFICATION_REQUIRED`, `pending.missingFields` includes the transfer type; amount 500 is remembered; no box, nothing executed |
| 8 | follow-up | after #7 type `to my own account` | Own-account branch continues (same outcome as #4 for taslim) |
| 9 | follow-up with picker (2+ accounts only) | tap an account row in the picker | App sends `Selected` + `{"accountNumber": <as received>}` → summary `own_account_transfer` + U8 box |
| 10 | similar, different use case | `how much can I transfer per day?` | Must NOT start a transfer: `transfer_info/transfer_limit` bars (see 14.27) |

### 14.2 City (Polygon) Bank transfer
**Outcome:** gather → inline box (the bot never executes)  ·  **Result:** `BANKING_SERVICE` `transfer/bank_transfer/city_account` + `routing.action: city_account_transfer`
**UI to show:** U8 transfer box: from-account picker, recipient (account or mobile) prefilled from `payload.accountNumber`, amount prefilled from `payload.amount` (taka), note; button Send. Missing number or amount: bubble only until the customer answers.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `Polygon` | Vague: may ask what they want to do / where to send; no box |
| 2 | two words | `Polygon transfer` | Polygon account transfer; asks for the recipient account number and amount (`missingFields` accountNumber, amount); no box |
| 3 | casual / typos | `plz send 1,250 to a polygn bank acc 4829173650281` | Summary: `city_account_transfer`; `accountNumber: "4829173650281"`, `amount: "1250"`, `formattedAmount` ৳1,250; box prefilled with both |
| 4 | normal, number + amount | `Send 500 taka to Polygon Bank account number 7305518294063.` | `city_account_transfer`; `accountNumber: "7305518294063"`, `amount: "500"`; U8 box, button Send, `executed: false` |
| 5 | amount as 5k | `transfer 5k to my friend's Polygon account 2160947385120` | `amount: "5000"` (formatted ৳5,000), `accountNumber: "2160947385120"`; box prefilled |
| 6 | amount as 2 lakh | `I need to pay 2 lakh to a Polygon Bank account, 9081264537719, for the plot booking.` | `amount: "200000"` (formatted ৳200,000), `accountNumber: "9081264537719"`; box; limit/balance check is the app's job |
| 7 | mobile number as recipient | `send 1,250 taka to the Polygon account with mobile number 01712458093` | Summary `city_account_transfer` with the 11-digit mobile as the recipient (`accountNumber: "01712458093"`), `amount: "1250"`; box recipient field prefilled (recipient may be account or mobile) |
| 8 | long story | `My cousin Sohel opened a Polygon Bank account last month and his rent is due on the fifth. I have the money ready in my savings and I would like to send him 5k today. His account number is 5517380294468, please set it up for me and I will confirm it in the app.` | `city_account_transfer`, `accountNumber: "5517380294468"`, `amount: "5000"`; box prefilled; bubble says finish in the box; nothing sent |
| 9 | without number | `send 500 taka to a Polygon Bank account` | Asks for the account number (amount 500 kept); `CLARIFICATION_REQUIRED`, `missingFields: ["accountNumber"]`; no box |
| 10 | without amount | `transfer to Polygon account 3846092715534` | Asks how much (taka); `missingFields: ["amount"]`, no box |
| 11 | follow-up to #9 | type `3846092715534` | Summary with that number and amount 500 → U8 box prefilled |
| 12 | follow-up to #10 | type `2 lakh` | `amount: "200000"` → summary + box |
| 13 | tricky: no destination | `send 500 taka` | Asks where (own account / Polygon account / other bank / bKash, Nagad, Rocket, Upay); no box |
| 14 | similar, different use case | `what is the fee for sending 5k to a Polygon account?` | Must NOT start the transfer: fee quote (`fees/fee_quote`), see FEES |

### 14.3 Other bank transfer
**Outcome:** gather → inline box (the bot never executes)  ·  **Result:** `BANKING_SERVICE` `transfer/bank_transfer/other_bank` + `routing.action: other_bank_transfer`
**UI to show:** U8 transfer box: from-account, transfer type (BEFTN / NPSB / RTGS), beneficiary name, account (prefilled from `payload.accountNumber`), bank, branch, amount (prefilled from `payload.amount`); button Send. A bank name in the message selects "other bank" but the bank, branch and type are chosen in the box (not in `payload`).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `BEFTN` | Vague; may ask what they want or where to send; no box |
| 2 | two words | `other bank` | Other-bank transfer; asks for the account number and amount; no box |
| 3 | casual / typos | `pls tranfer 5k to brac bnk acc 4829173650281` | `other_bank_transfer`; `accountNumber: "4829173650281"`, `amount: "5000"`; box prefilled |
| 4 | normal, bank + number + amount | `Send 1,250 taka to my friend's Dutch-Bangla Bank account 7305518294063.` | `other_bank_transfer`; `accountNumber: "7305518294063"`, `amount: "1250"` (formatted ৳1,250); box; bank name not prefilled |
| 5 | another bank + 2 lakh | `Transfer 2 lakh taka to my Islami Bank account 2160947385120 please.` | `amount: "200000"`, `accountNumber: "2160947385120"`; box |
| 6 | amount 500, abbreviation | `send 500 to my city bank account number 9081264537719` | A bank name is given, so other-bank type (not Polygon); `amount: "500"`, `accountNumber: "9081264537719"`; box |
| 7 | long story | `I am going on a trip with friends and I owe my friend Arif his share of the hotel. He banks with Eastern Bank, his account is 5517380294468, and the share is 5k. I can't do it from the app right now, so can you set up the transfer?` | `other_bank_transfer`, `accountNumber: "5517380294468"`, `amount: "5000"`; box prefilled; bubble tells them to finish with Send in the box |
| 8 | without number | `send 1,250 taka to a Sonali Bank account` | Asks for the account number (amount kept); `missingFields: ["accountNumber"]` |
| 9 | without amount | `transfer to my Prime Bank account 3846092715534` | Asks how much; `missingFields: ["amount"]` |
| 10 | follow-up to #8 | type `7305518294063` | Summary with number + amount 1250 → box |
| 11 | follow-up to #9 | type `500` | `amount: "500"` → summary + box |
| 12 | tricky: no destination | `send 500 taka` | Asks where to send; no box; not executed |
| 13 | without bank/number/amount | `send money to another bank` | Other-bank intent; asks for account number and amount; no box |
| 14 | similar, different use case | `list of banks I can send to` | Must NOT start a transfer: see 14.4 (info card, "not available") |

### 14.4 Other banks list
**Outcome:** not offered (no backend)  ·  **Result:** `APP_ACTION` `app_actions/other_banks_list` (`ui.kind: "unavailable"`)
**UI to show:** U9 info card with `ui.title` ("List of other banks") and the bubble; no button, no box.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `banks` | May ask a clarifying question; bubble only |
| 2 | two words | `other banks` | Bubble says the list isn't available now; U9 card, no button |
| 3 | casual | `which banks can i send money to lol` | Same: not available, info card |
| 4 | normal | `Can you show me the list of other banks I can transfer to?` | Same |
| 5 | long | `I want to send money to a friend but I'm not sure which banks are supported through this app. Can you give me the full list of other banks so I can check whether his bank is on it?` | Same: not available, no box |
| 6 | similar, different use case | `send 1,250 taka to Brac Bank account 4829173650281` | Must NOT show the info card: this is 14.3 (box) |

### 14.5 Gift transfer
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/gift_transfer` (`ui.kind: "screen"`, `GiftScreen`, `/gift`)
**UI to show:** U8 gift box: recipient (account or mobile), gift design, wish message, amount; button Send gift, then U7 code + transaction PIN. Prefill `amount`, `recipient` (only what the customer wrote; taka).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `gift` | `gift_transfer` box with empty fields (prefill null), or may ask a clarifying question |
| 2 | two words | `send gift` | Gift box, nothing prefilled |
| 3 | casual | `wanna send my sis a bday gift lol` | Gift box; `recipient` may be prefilled ("sis"); no amount |
| 4 | normal | `I want to send a gift of 1,250 taka to my friend.` | Gift box; prefill `amount: 1250` |
| 5 | long story | `It's my mother's birthday tomorrow and I'd love to surprise her with a gift and a nice wish message. Please set it up so I can send her 5k with a birthday card.` | Gift box; prefill `amount: 5000`, `recipient` maybe "mother" |
| 6 | with details | `send a gift of 2 lakh to 01712458093` | Gift box; `amount: 200000`, `recipient: "01712458093"` |
| 7 | similar, different use case | `show me gifts I received` | Must NOT open the gift box: see 14.6 (list) |
| 8 | similar, different use case | `send 500 taka to my bkash 01836290417` | Must NOT be a gift: 14.14 bKash summary |

### 14.6 Gifts received
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `transfer_info/gifts_received`
**UI to show:** U2 list card "Gifts received". Test customer has no gifts: the bubble says none received, no card/rows, no buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `gifts` | Answers: no gifts received yet (or asks whether sending or receiving) |
| 2 | two words | `gifts received` | "No gifts received"; `payload.items: []`; bubble only |
| 3 | casual | `did i get any gifts lol` | Same, empty list |
| 4 | normal | `Can you show me the gifts I have received?` | Same |
| 5 | long | `My relatives said they would send me eid gifts through the app last week. Can you check whether any gifts have arrived on my account and tell me who sent them?` | `gifts_received`, none found; bubble only |
| 6 | similar, different use case | `send a gift to my brother` | Must NOT list: 14.5 gift box |
| 7 | similar, different use case | `show my transactions` | Not gifts: transaction history (rows 13.x) |

### 14.7 Generic transaction
**Outcome:** not offered (not a customer ask, bank-internal; no chat use case)  ·  **Result:** none for this row; generic "pay/send" wording falls to 14.1–14.3 / 14.14 clarification
**UI to show:** bubble only, no box, no card.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `pay` | Bubble only; asks what they want to pay or where to send; no box |
| 2 | two words | `pay cash` | Same |
| 3 | casual | `hey can i pay some money thx` | Asks where to send / what to pay; no box |
| 4 | normal | `I want to make a transaction.` | Asks which kind (own account, Polygon account, other bank, wallet); `CLARIFICATION_REQUIRED`, no box |
| 5 | long | `I'm trying to order food online but the payment gateway keeps failing. Can you help me pay for this transaction some other way?` | Bubble only; no payment is made and no box |

### 14.8 Linked account check
**Outcome:** not offered (not a customer ask, bank-internal; no chat use case)  ·  **Result:** none for this row (may route to account info or ask a clarifying question)
**UI to show:** bubble only, no box.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `linked` | Bubble only; may ask what they mean |
| 2 | two words | `linked accounts` | May answer with the customer's account list (account_info, see ACCOUNTS) or ask; no transfer box |
| 3 | casual | `is my acc linked to bkash lol` | Bubble only; no wallet-link feature, no box |
| 4 | normal | `Can you check whether my account is linked to another account?` | Bubble only; no box |
| 5 | long | `Before I send money I want to make sure my savings account is properly linked with my other accounts at the bank. Can you check the link status for me?` | Bubble only; no transfer is started |

### 14.9 Email transfer — create
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/email_transfer_create` (`EmailTransferEntryScreen`, `/email_transfer/entry`)
**UI to show:** U8 box: recipient email, amount, security question and answer; button Send, then U7 code + PIN. Prefill `recipientEmail`, `amount` (taka).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `email` | Likely asks what they want (create or list); no box until clear |
| 2 | two words | `email transfer` | May ask: send one or see existing ones |
| 3 | casual | `send money 2 my frnd by email` | Email-transfer box, prefill empty |
| 4 | normal | `I want to send money by email.` | Box with empty fields |
| 5 | with details | `send 1,250 taka by email to rahim.karim@example.com` | Box; `recipientEmail: "rahim.karim@example.com"`, `amount: 1250` |
| 6 | with 5k | `email transfer 5k to sara@example.com` | `amount: 5000`, `recipientEmail: "sara@example.com"` |
| 7 | long story | `My cousin abroad doesn't have a bank account here but has an email. Can I send him 2 lakh taka using only his email address, with a security question? His email is arif.h@example.com.` | Box; `recipientEmail: "arif.h@example.com"`, `amount: 200000` |
| 8 | similar, different use case | `show my email transfers` | Must NOT open the box: 14.10 list |
| 9 | similar, different use case | `send 500 to bkash 01711223344` | 14.14, not an email transfer |

### 14.10 Email transfer — list
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `transfer_info/email_transfers`
**UI to show:** U2 list card "Email transfers with status". Test customer has none: bubble "none found", no rows, no buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `emailtransfers` | May ask, or answers with the (empty) list |
| 2 | two words | `email transfers` | "No email transfers"; `items: []`; bubble only |
| 3 | casual | `any email transfers i sent` | Same |
| 4 | normal | `Can you show me a list of the email transfers I have made?` | Same |
| 5 | long | `I sent some money by email to my sister a while back and she says it never arrived. Can you list all my email transfers with their status so I can check?` | Same: none found; bubble only |
| 6 | similar, different use case | `send 1,250 taka by email` | Not a list: 14.9 box |

### 14.11 Email transfer — details
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `transfer_info/email_transfers` (one transfer)
**UI to show:** U3 detail card "email transfer" for one transfer. Test customer has none: bubble "no email transfer found"; no card.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `status` | May ask which transfer/what status; bubble only |
| 2 | two words | `transfer status` | Email-transfer lookup or clarifying question; none found |
| 3 | casual | `wheres my email transfer` | None found; bubble only |
| 4 | normal | `What is the status of my email transfer from yesterday?` | None found for taslim; bubble only |
| 5 | long | `Last week I sent 50,000 taka by email transfer to a relative. I can't find the details anywhere. Could you pull up that email transfer and tell me its status and expiry?` | None found; no U3 card |
| 6 | similar, different use case | `what is the status of my money sent to bkash 01711223344` | Must NOT be this row: 14.14 summary (or transaction history) |

### 14.12 Email transfer — cancel
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/email_transfer_manage` (`EmailTransferListScreen`, `/email_transfer/list`)
**UI to show:** U8 box listing the customer's email transfers, each with Cancel (asks to confirm) and Resend; prefill `action: "cancel"`. The bot makes no call. Taslim has no email transfers, so the box may be empty.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `cancel` | May ask what to cancel; no box until clear |
| 2 | two words | `cancel email transfer` | `email_transfer_manage`, prefill `action: "cancel"` |
| 3 | casual | `cncl my email transfer plz` | Same |
| 4 | normal | `I would like to cancel the email transfer I made yesterday.` | Same |
| 5 | long | `I sent 10,000 taka by email transfer on the 23rd to my cousin but I typed the wrong address. Please help me cancel it before he claims it.` | Same; prefill `action: "cancel"` |
| 6 | similar, different use case | `cancel my pending transfer limit change` | Must NOT open this box: 14.29 |
| 7 | similar, different use case | `cancel my card` | Not a transfer: card close (4.x), app action |

### 14.13 Email transfer — resend
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/email_transfer_manage`
**UI to show:** same U8 box as 14.12 (Cancel · Resend per transfer); prefill `action: "resend"`.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `resend` | May ask what to resend; no box until clear |
| 2 | two words | `resend notification` | `email_transfer_manage`, `action: "resend"` |
| 3 | casual | `pls resend my email transfer mail, she didnt get it` | Same |
| 4 | normal | `Can you resend the notification for my email transfer?` | Same |
| 5 | long | `I sent money by email to my friend on Wednesday, but the email never reached her inbox. Please resend the notification so she can claim the money.` | Same; `action: "resend"` |
| 6 | similar, different use case | `send 1,250 taka again to 01711223344` | Not a resend: a new 14.14 transfer summary (the bot asks the wallet provider/type if not said) |

### 14.14 Wallet / MFS transfer
**Outcome:** gather → inline box (the bot never executes)  ·  **Result:** `BANKING_SERVICE` `transfer/wallet_transfer/<bkash|nagad|rocket|upay>` + `routing.action: bkash_transfer | nagad_transfer | rocket_transfer | upay_transfer`
**UI to show:** U8 wallet box: from-account, wallet provider (from `subservice`) and number prefilled from `payload.walletNumber`, transfer type (direct or NPSB), amount prefilled from `payload.amount` (taka), note; button Send (then U7 code + PIN inside the app). Missing number or amount: bubble only until answered. The wallet number must be 11 digits starting 01 (the app validates).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `bkash` | Vague; may ask what they want or how much and which number; no box |
| 2 | two words | `Nagad transfer` | Nagad chosen; asks for the wallet number and amount; `missingFields` walletNumber, amount; no box |
| 3 | casual | `send 5k to bkash 01712458093 asap` | Summary `bkash_transfer`, `walletNumber: "01712458093"`, `amount: "5000"`, ৳5,000; box |
| 4 | bKash, normal | `Send 500 taka to my bKash number 01836290417.` | `bkash_transfer`; `walletNumber: "01836290417"`, `amount: "500"`, `formattedAmount` ৳500; U8 box, Send; `executed: false` |
| 5 | Nagad, 1,250 | `transfer 1,250 taka to Nagad 01521670384` | `nagad_transfer`; `walletNumber: "01521670384"`, `amount: "1250"` (৳1,250) |
| 6 | Rocket, 2 lakh | `I need to send 2 lakh to my Rocket account 01947203865.` | `rocket_transfer`; `amount: "200000"`, `walletNumber: "01947203865"`; box (balance 90,000 is the app's concern, not the bot's) |
| 7 | Upay, 5k | `send 5k to upay 01619384725` | `upay_transfer`; `amount: "5000"`, `walletNumber: "01619384725"` |
| 8 | Rocket, typos | `plz trnsfer 500 to rokect 01311872046` | `rocket_transfer`, `amount: "500"`, `walletNumber: "01311872046"` (a misspelled provider may instead be asked about) |
| 9 | long story | `My little brother is studying in Chittagong and his hostel fee is due. He only uses Nagad, and his number is 01836290417. Could you please send 5k from my savings to his Nagad today? I'll finish it in the app.` | `nagad_transfer`, `walletNumber: "01836290417"`, `amount: "5000"`; box prefilled |
| 10 | without number | `send 1,250 taka to bkash` | Asks for the bKash number (amount 1250 kept); `missingFields: ["walletNumber"]`; no box |
| 11 | without amount | `transfer to nagad 01521670384` | Asks how much; `missingFields: ["amount"]`; no box |
| 12 | without both | `send money to my rocket` | Asks the Rocket number and the amount; no box |
| 13 | follow-up to #10 | type `01712458093` | Summary `bkash_transfer` with that number + amount 1250 → box |
| 14 | follow-up to #11 | type `2 lakh` | `amount: "200000"` → summary + box |
| 15 | tricky: no destination | `send 500 taka` | Asks where to send (own account, Polygon account, other bank, bKash, Nagad, Rocket, Upay); `CLARIFICATION_REQUIRED`; no box |
| 16 | follow-up to #15 | type `to my bkash` | bKash chosen; asks for the number (amount 500 kept) |
| 17 | follow-up to #16 | type `01947203865` | `bkash_transfer` summary: `walletNumber: "01947203865"`, `amount: "500"` → box |
| 18 | similar, different use case | `how much will sending 5000 to nagad cost?` | Must NOT start the transfer: fee quote `fees/fee_quote` (see FEES) |
| 19 | similar, different use case | `my bkash daily limit` | Must NOT start a transfer: 14.27 limit bars |

### 14.15 Wallet verify
**Outcome:** not offered (not built)  ·  **Result:** none for this row
**UI to show:** bubble only, no box.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `verify` | Bubble only; may ask what to verify |
| 2 | two words | `verify wallet` | Bubble only; says it can't do this / asks what they need |
| 3 | casual | `is this a valid bkash num` | Bubble only |
| 4 | normal | `Can you check whether the wallet number 01712458093 is registered and active?` | No verification offered. Caution: a number in the message may be read as 14.14; if the bot asks "how much and which wallet", that is the transfer flow, still nothing executed |
| 5 | long | `Before I send money I want to be sure the nagad number my friend gave me is real and belongs to him. Can you look the number up and tell me the holder's name?` | Bubble only; no holder lookup, no box |

### 14.16 QR pay
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/qr_payment` (`QrScanScreen`, route `null`)
**UI to show:** U8 box: camera scan area that shows merchant and amount once read; buttons Scan · Pay, then U7 code + PIN. No prefill (`ui.prefill` null).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `QR` | `qr_payment` box (or a short clarifying question) |
| 2 | two words | `QR pay` | Box with Scan / Pay |
| 3 | casual | `wanna pay thru qr lol` | Same |
| 4 | normal | `I would like to pay a merchant by scanning a QR code.` | Same |
| 5 | with details | `pay 500 taka by QR` | Same box; no prefill (amount comes from the QR) |
| 6 | long | `I'm at a shop and they have a QR code at the counter. I want to pay the bill of about 1,250 taka from my savings account. How do I do this here in the chat?` | Same box |
| 7 | similar, different use case | `show my QR payment history` | Must NOT open the scanner: 14.18 list |
| 8 | similar, different use case | `QR payment cards` | Not this: `qr_payment_cards` (info card, not available; row 4.22) |

### 14.17 QR parse
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/qr_payment`
**UI to show:** same as 14.16 (scan area; Scan · Pay; U7 after Pay).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `scan` | `qr_payment` box |
| 2 | two words | `scan QR` | Same |
| 3 | casual | `can u read this qr for me` | Same: the bot cannot read an image in chat; it opens the scan box |
| 4 | normal | `Can you help me read this QR code to see who I'm paying?` | Same |
| 5 | long | `I got a QR code from a shopkeeper and the other app couldn't read it. Can I scan it with your app and see the merchant name and the amount before I pay?` | Same; Scan then shows merchant/amount, Pay needs code + PIN |
| 6 | similar, different use case | `QR payments I made last week` | Must NOT open the scanner: 14.18 |

### 14.18 QR payment history
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `transfer_info/qr_payment_history`
**UI to show:** U2 list card "QR payments" (amounts already taka). Test customer has none: bubble "none", `data: []`, no rows.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `history` | Ambiguous: may ask which history (transactions vs QR); bubble only |
| 2 | two words | `QR history` | "No QR payments"; empty list |
| 3 | casual | `qr payments i made` | Same |
| 4 | normal | `Can you show me my QR payment history?` | Same |
| 5 | long | `I scanned a QR code at a restaurant last Friday and paid, but I'm not sure whether it went through. Can you show my recent QR payments?` | Same: none found; bubble only |
| 6 | similar, different use case | `pay with QR` | Must NOT list: 14.16 scanner box |
| 7 | similar, different use case | `show my transactions` | Not QR: transaction history (13.1), 3 transactions incl. a 5,000 bKash debit |

### 14.19 Beneficiary — list / send to a saved name
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `polygon_services/beneficiary` (list: `payload.beneficiaries: []`); a name match gives `BENEFICIARY_MATCH`; several give `BENEFICIARY_SELECTION_REQUIRED`
**UI to show:** beneficiary cards list (existing). Test customer has none: bubble "no saved beneficiaries", no cards. A name that matches: one card with Send → U8 transfer box for `payload.destination` (`own_bank_transfer`, `other_bank_transfer`, `wallet_transfer`+provider, or manual); several: U5 picker, tap sends `Selected` + `{"beneficiaryId": <id>}`.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `beneficiaries` | Answers with the list: none saved; bubble only |
| 2 | two words | `saved recipients` | Same |
| 3 | casual | `who are my saved ppl` | Same |
| 4 | normal | `Can you show me my saved beneficiaries?` | Same; `beneficiaries: []` |
| 5 | long | `I want to send money to someone I've sent to before but I can't remember who is saved in the app. Could you list all the beneficiaries I have saved so I can pick one?` | Same: none saved |
| 6 | with a name | `send 500 taka to Rahim` | No saved match: `CLARIFICATION_REQUIRED` saying no saved beneficiary named Rahim; no box. (With a saved Rahim: `BENEFICIARY_MATCH` card + Send) |
| 7 | with a name, 5k | `pay 5k to my saved beneficiary Sohel` | Same: none found, bubble only |
| 8 | similar, different use case | `add a new beneficiary` | Must NOT list: 14.20 add flow |
| 9 | similar, different use case | `delete my beneficiary Sohel` | Must NOT list: 14.22 app action |

### 14.20 Beneficiary — add
**Outcome:** executed in chat after yes-no  ·  **Result:** `CONFIRMATION_REQUIRED` `beneficiary_management/beneficiary_add`, then `BANKING_SERVICE` with `executed`
**UI to show:** U1 asks for the name and account number (an other-bank beneficiary also asks bank name, branch, routing number) → U6 confirm card (name, account ending, bank) with Yes / No. KNOWN GAP: after Yes the bank returns 500, so the customer sees the retry notice (`SERVICE_UNAVAILABLE`, U10) instead of a done notice.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `beneficiary` | Ambiguous (list vs add); may ask |
| 2 | two words | `add beneficiary` | Asks for the name to save it under and the account number; `CLARIFICATION_REQUIRED`; bubble only |
| 3 | casual | `save my frnd as a bene pls` | Asks for the name and account number |
| 4 | normal | `I'd like to add a new beneficiary.` | Same |
| 5 | with details | `add beneficiary Sohel, account 4829173650281` | Own-bank vs other-bank may be asked; then (for other bank) asks bank, branch and routing number; then confirm card |
| 6 | long | `My friend Arif keeps getting money from me every month for his rent, so I'd like to save him as a beneficiary. His account is 7305518294063 at Eastern Bank, so please add him as Arif Rent.` | Asks missing bank details (branch, routing number); then U6 confirm with name "Arif Rent" and account ending 4063 |
| 7 | then send (button) | tap Yes | App sends `Yes` + `{"confirm": true}` → bank call is made; today a bank 500 shows the retry notice; if it worked: "saved" notice |
| 8 | then send (button) | tap No | App sends `No` + `{"confirm": false}` → `BANKING_SERVICE` `{"executed": false, "cancelled": true}`; nothing saved |
| 9 | similar, different use case | `show my beneficiaries` | Must NOT start the add flow: 14.19 list |

### 14.21 Beneficiary — edit
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/beneficiary_edit` (`BeneficiaryFormScreen`, `/beneficiary/form`)
**UI to show:** U8 box: beneficiary (preselected by name), nickname field (only the nickname is editable); button Save. Prefill `nickname` (the new name, only if the customer gave it).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `edit` | May ask what to edit; no box until clear |
| 2 | two words | `edit beneficiary` | `beneficiary_edit` box, no prefill |
| 3 | casual | `change my benificiary name pls` | Same |
| 4 | normal | `I want to rename a saved beneficiary.` | Same |
| 5 | with details | `rename my beneficiary Sohel to Sohel Rent` | Box; `nickname: "Sohel Rent"` |
| 6 | long | `I saved my brother with a nickname that is just his first name, but I now have two brothers with similar names. Can I change his nickname to Big Brother so I can tell them apart?` | Box; `nickname: "Big Brother"` |
| 7 | similar, different use case | `change my own nickname` | Must NOT open this: profile nickname change (`profile_update/update_nickname`, yes/no) |

### 14.22 Beneficiary — delete
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/beneficiary_delete` (`BeneficiaryScreen`, `/beneficiary`)
**UI to show:** U8 confirm card with the beneficiary's name and masked account; buttons Delete · Keep. No prefill.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `delete` | May ask what to delete |
| 2 | two words | `remove beneficiary` | `beneficiary_delete` box |
| 3 | casual | `cud u plz del my benificiary` | Same |
| 4 | normal | `I need to remove a saved beneficiary.` | Same |
| 5 | long | `I saved my old landlord as a beneficiary last year, but I moved out and don't want to send him money by mistake. Please remove him from my saved list.` | Same box (beneficiary picked in the box) |
| 6 | similar, different use case | `delete my card` | Not this: card services (close card) |

### 14.23 Beneficiary — upload / change photo
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/beneficiary_photo` (`BeneficiaryFormScreen`, `/beneficiary/form`)
**UI to show:** U8 box: beneficiary (preselected) with a photo area; buttons Choose photo · Remove photo · Save. No prefill. Photos are chosen in the app (gallery or camera).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `photo` | `beneficiary_photo` box or a short clarifying question |
| 2 | two words | `beneficiary photo` | Box |
| 3 | casual | `can i add a pic to my benficiary` | Box |
| 4 | normal | `I want to upload a photo for one of my saved beneficiaries.` | Box |
| 5 | long | `I have a lot of saved recipients and they all look the same in the list. I would like to put a picture on my sister's entry so I can find her faster. How do I upload one?` | Box |
| 6 | similar, different use case | `change my profile picture` | Must NOT open this: profile, not beneficiary |

### 14.24 Beneficiary — remove photo
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/beneficiary_photo`
**UI to show:** same box as 14.23 (Choose photo · Remove photo · Save).

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `remove photo` | Box (or asks which photo) |
| 2 | two words | `photo gone` | Box or short clarifying question |
| 3 | casual | `pls take off the pic from my benificiary` | Box |
| 4 | normal | `I want to remove the photo from a saved beneficiary.` | Box |
| 5 | long | `I added my cousin's picture to her beneficiary entry some time ago but I'd rather keep the list plain. Please help me delete just the photo and keep her details.` | Box; Remove photo is a button inside it |
| 6 | similar, different use case | `delete the beneficiary` | Must NOT open this photo box: 14.22 delete confirm card |

### 14.25 Beneficiary — pin / unpin
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/beneficiary_pin` (`BeneficiaryScreen`, `/beneficiary`)
**UI to show:** U8 box: beneficiary list with a pin switch each (list pinning, not a security PIN). No prefill.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `pin` | Ambiguous (card PIN vs beneficiary pin); may ask |
| 2 | two words | `pin beneficiary` | `beneficiary_pin` box |
| 3 | casual | `unpin my benificiary pls` | Same |
| 4 | normal | `I want to pin a saved beneficiary to the top of my list.` | Same |
| 5 | long | `I send money to my mother every week and I'd like her to always appear at the top of my saved recipients. Can I pin her entry so I don't have to scroll?` | Same |
| 6 | similar, different use case | `change my card PIN` | Must NOT open this: card PIN change (card services, app action) |

### 14.26 Recipient lookup by account number
**Outcome:** not offered (not built)  ·  **Result:** none for this row
**UI to show:** bubble only, no box.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `lookup` | Bubble only; may ask what to look up |
| 2 | two words | `account lookup` | Bubble only; can't do |
| 3 | casual | `whos acc is 4829173650281` | Bubble only; no holder name shown. A bare number may be read as a transfer: if it asks how much/where, that is 14.2/14.3 and nothing is executed |
| 4 | normal | `Can you tell me the name of the holder of account number 7305518294063?` | Same: not offered |
| 5 | long | `A seller gave me his account number 2160947385120 and I want to be sure the name matches before I send him 5k. Can you look up who owns the account?` | Not offered, no lookup; may fall into the 14.2/14.3 questions about where to send, no box without a destination |

### 14.27 My transfer limit — get
**Outcome:** answered in chat  ·  **Result:** `BANKING_SERVICE` `transfer_info/transfer_limit`
**UI to show:** U3 limits: daily, weekly and per-transaction bars; values are poisha (÷100) and a `null` value shows "Not set". No buttons.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `limits` | Transfer limits shown (daily/weekly/per transaction) |
| 2 | two words | `transfer limit` | Same |
| 3 | casual | `whats my daily limit lol` | Same; daily may be "Not set" |
| 4 | normal | `Can you tell me my current transfer limit?` | Same |
| 5 | long | `Eid is coming up and I need to send quite a bit to family. Before I do, could you tell me what my daily and weekly transfer limits are and how much of them I've already used?` | Same, with used amounts in the bars |
| 6 | similar, different use case | `raise my transfer limit to 2 lakh` | Must NOT show the bars: 14.28 app action |
| 7 | similar, different use case | `what is my card limit` | Not transfer limit: card limits (CARDS) |

### 14.28 My transfer limit — request change
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/transfer_limit_change` (`TransferLimitScreen`, `/transfer_limit`)
**UI to show:** U8 box: account picker and new limit (prefilled from `newLimit`, taka); buttons Submit · Cancel pending request; then U7 code + PIN.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `raise` | May ask what to raise; no box until clear |
| 2 | two words | `increase limit` | Box; may ask which limit (card vs transfer) |
| 3 | casual | `pls raise my tranfer limit` | Box, no `newLimit` |
| 4 | normal | `I want to change my transfer limit because it's too low.` | Box, no `newLimit` |
| 5 | with details | `change my daily transfer limit to 2 lakh` | Box; `newLimit: 200000` |
| 6 | with 5k | `set my transfer limit to 5k` | `newLimit: 5000` (a lower limit; still goes to the box) |
| 7 | long | `I'm sending money to my sister abroad every month and the daily limit is too low for what I need. Could you help me request a higher transfer limit of 1,250,000 taka?` | Box; `newLimit: 1250000` |
| 8 | similar, different use case | `what is my transfer limit` | Must NOT open the box: 14.27 bars |

### 14.29 My transfer limit — cancel pending change
**Outcome:** app action → inline box  ·  **Result:** `APP_ACTION` `app_actions/transfer_limit_change`
**UI to show:** same U8 box as 14.28 with the pending request and the button Cancel pending request. No `newLimit` prefill. The customer has no pending change, so the box shows none.

| # | Type | Send | Expect |
|---|---|---|---|
| 1 | one word | `cancel` | Too vague: may ask what to cancel |
| 2 | two words | `cancel limit` | `transfer_limit_change` box |
| 3 | casual | `cancel my limit change req` | Same |
| 4 | normal | `I want to cancel the pending change to my daily transfer limit.` | Same; no `newLimit` |
| 5 | long | `Last Monday I asked for a bigger transfer limit but I've changed my mind, since my sister no longer needs the money. Can you cancel that pending request?` | Same |
| 6 | similar, different use case | `cancel my email transfer` | Must NOT open this: 14.12 box |
