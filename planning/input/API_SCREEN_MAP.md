# API Screen Map

For each of the 14 chatbot intents: the real APIs that serve it, and the exact app screens/triggers that call each API, traced from `user_app/lib` (HTTP call -> repository -> use case -> controller -> screen). Paths are relative to the Kong gateway base URL. Source: an internal code-trace artifact (API Screen Map; 186 API URLs traced, 91 serve one of the 14 intents, 95 uncovered, 13 dead/unreachable), as of 2026-10-01. Read-only trace — does not confirm the backend works end to end, only that the app calls it.

Use this to cross-check `routing.action`/screen-redirect hints against real screen names, and to see exactly what UI action triggers each endpoint (useful when deciding how a chatbot result should map to a real navigation target).

## Part 1 — Intents

### ACCOUNT_INFO — *Covered*

**Accounts** — `polygon-bank/v1/accounts`
- Home (`HomeScreen`) — on load (HomeController finds MyAccountsController, whose onInit loads accounts)
- My Accounts (`MyAccountsScreen`) — on load / pull to refresh (refreshAccounts)
- Customize Quick View (`CustomizeQuickViewScreen`) — on load (refreshAccounts) ; toggle star
- Set/Reset PIN - select card (`SelectCardForPinResetScreen`) — on load (CardPinResetController.loadCards)
- International Transaction - select card (`SelectCardForInternationalScreen`) — on load (loadCards)
- Transaction History (`TransactionHistoryScreen`) — on load (_loadAccountsThenHistory)
- QR Transfer Confirm (`QrTransferConfirmScreen`) — on load (QrTransferConfirmController)
- Reset TPIN (`TpinVerificationScreen/ResetTpinScreen`) — on load (TpinResetController loads accounts)
- Reset Login Secret (`LoginSecretVerificationScreen/SetLoginSecretScreen`) — on load (LoginSecretResetController loads accounts)

  *Also MyAccountsController is lazily created on first Get.find, so accounts load wherever it is first resolved (Home, My Accounts, Freeze Card, etc.). Reset TPIN/Login Secret/QR rows: controller-level call, exact screen within the flow not individually verified.*

**Account detail** — `polygon-bank/v1/accounts/{id}`
- Account Detail (`AccountDetailScreen`) — on open from list/home (openDetail fires fetches)
- Card Detail (`CardDetailScreen`) — on open (openDetail fires fetches)
- Home (`HomeScreen`) — tap an account/card quick-view tile (openDetail)
- My Accounts (`MyAccountsScreen`) — tap an account row (openDetail)

  *Fetched via openDetail -> _loadDetail -> loadAccountDetail*

**Account by number** — `polygon-bank/v1/accounts/by-number/{accountOrCardNumber}`
- Register - Account/Card Entry (`RegisterAccountEntryScreen`) — tap Continue (lookupAccount)

**Accounts by username** — `polygon-bank/v1/accounts/by-username/{username}`
- Verify New Device - Select Account (`SelectVerifyScreen`) — on load (loads accounts for username); tap Continue sends OTP

**Account starred** — `polygon-bank/v1/accounts/{id}/quick-view`
- Customize Quick View (`CustomizeQuickViewScreen`) — toggle star on an account (setStarred)

**My loans** — `loan/v1/loans`
- My Loans (`LoanScreen`) — on load
- Certificate Request (`CertificateRequestScreen`) — lazy: when a loan-requiring certificate type is selected

**Fixed deposit profit history** — `product/v1/fixed-deposit/{fdIdentifier}/profit-history`
- Mudarabah Profit (`MudarabahProfitScreen`) — tap an FD account card to expand profit history

**Dps profit history** — `product/v1/dps/{dpsIdentifier}/profit-history`
- Mudarabah Profit (`MudarabahProfitScreen`) — tap a DPS account card to expand profit history


### ATM_SUPPORT — *Partial — no ATM/branch locator API exists*

**Cash by code** — `transfer/v1/cash-by-code`
- Cash by Code (`CashByCodeScreen`) — tap Continue then PIN entry (TPIN sheet confirm)

**Submit dispute** — `service-request/v1/disputes`
- Dispute a Transaction (`DisputeTransactionScreen`) — tap Submit Dispute


### CARD_ISSUE — *Partial — no card-diagnostic API; routed via other card/support APIs*

**Reset card pin** — `card/v1/cards/{cardId}/reset-pin`
- Confirm (Set/Reset PIN) (`ConfirmPinResetScreen`) — tap Reset PIN (CardPinResetController.submit)

**Unfreeze card** — `card/v1/cards/{cardId}/unfreeze`
- Freeze / Unfreeze Card (`FreezeCardScreen`) — tap Unfreeze on a frozen card
- Card Settings sheet (from Card Detail) (`CardSettingsSheet`) — toggle freeze switch off

**Submit dispute** — `service-request/v1/disputes`
- Dispute a Transaction (`DisputeTransactionScreen`) — tap Submit Dispute

**Submit complaint** — `support/v1/complaints`
- File a Complaint (`ComplaintScreen`) — tap Submit Complaint


### CARD_MANAGEMENT — *Covered*

**Freeze card** — `card/v1/cards/{cardId}/freeze`
- Freeze / Unfreeze Card (`FreezeCardScreen`)
- Card Settings sheet (from Card Detail) (`CardSettingsSheet`)

  *Freeze triggered from FreezeCardScreen (reason 'Other' in freeze reason sheet) and Card Settings sheet freeze toggle; strong-auth (OTP+TPIN) follows. Lost/stolen/close reasons route to CardReplacementScreen instead.*

**Unfreeze card** — `card/v1/cards/{cardId}/unfreeze`
- Freeze / Unfreeze Card (`FreezeCardScreen`) — tap Unfreeze on a frozen card
- Card Settings sheet (from Card Detail) (`CardSettingsSheet`) — toggle freeze switch off

**Close card** — `card/v1/cards/{cardId}/close`
- Card Settings sheet (from Card Detail) (`CardSettingsSheet`) — tap Close Card in settings sheet
- Report Card / Close Card (Lost-Stolen-Close / Replacement) (`CardReplacementScreen`) — Close Card flow (CardReplacementController.closeCard) / lost-stolen-close confirm

**Contactless preference** — `card/v1/cards/{cardId}/contactless`
- Card Settings sheet (from Card Detail) (`CardSettingsSheet`) — toggle Contactless switch

**International transaction** — `card/v1/cards/{cardId}/international-transaction`
- International Transactions (`CardInternationalProfileScreen`) — toggle international switch (toggleInternational)

**Reset card pin** — `card/v1/cards/{cardId}/reset-pin`
- Confirm (Set/Reset PIN) (`ConfirmPinResetScreen`) — tap Reset PIN (CardPinResetController.submit)

**Submit card limit change** — `card/v1/cards/{cardId}/limit-change-requests`
- Credit Limit Change (`CardLimitChangeScreen`) — tap Submit Request

**Card limit change requests** — `card/v1/cards/limit-change-requests`
- Credit Limit Change (`CardLimitChangeScreen`) — on load (onInit -> loadRequests)

**Cancel card limit change request** — `card/v1/cards/limit-change-requests/{requestId}`
- Credit Limit Change (`CardLimitChangeScreen`) — tap cancel on a request, confirm 'Cancel Request?'

**Card products** — `card/v1/card-products`
- Card Products catalog (`CardProductCatalogScreen`) — on load / change type tab
- Apply for Virtual Card (`RequestVirtualCardScreen`) — on selecting category (selectCategory)

**Debit card application** — `card/v1/cards/debit`
- Apply for Virtual Card (`RequestVirtualCardScreen`) — submit after OTP + TPIN (VirtualCardController._submit, debit category)

**Reveal debit card** — `card/v1/cards/debit/{cardId}/reveal`
- Apply for Virtual Card (`RequestVirtualCardScreen`) — automatically right after debit application succeeds (repo-internal _revealCardApplication); shows credential reveal dialog

**Prepaid card application** — `card/v1/cards/prepaid`
- Apply for Virtual Card (`RequestVirtualCardScreen`) — submit after OTP + TPIN (VirtualCardController._submit, prepaid category)

**Reveal prepaid card** — `card/v1/cards/prepaid/{cardId}/reveal`
- Apply for Virtual Card (`RequestVirtualCardScreen`) — automatically right after prepaid application succeeds (repo-internal _revealCardApplication)

**Virtual card requests** — `card/v1/cards/virtual/requests`
- *(no reachable screen calls this)*

  *Dead code: use cases are only registered in CardBinding; no controller/screen calls submitVirtualCardRequest/listMy/cancel/reveal. RequestVirtualCardScreen uses debit/prepaid application endpoints instead.*

**Cancel virtual card request** — `card/v1/cards/virtual/requests/{requestId}`
- *(no reachable screen calls this)*

  *Dead code: use cases are only registered in CardBinding; no controller/screen calls submitVirtualCardRequest/listMy/cancel/reveal. RequestVirtualCardScreen uses debit/prepaid application endpoints instead.*

**Reveal virtual card** — `card/v1/cards/virtual/requests/{requestId}/reveal`
- *(no reachable screen calls this)*

  *Dead code: use cases are only registered in CardBinding; no controller/screen calls submitVirtualCardRequest/listMy/cancel/reveal. RequestVirtualCardScreen uses debit/prepaid application endpoints instead.*

**Card starred** — `card/v1/cards/{cardId}/quick-view`
- Customize Quick View (`CustomizeQuickViewScreen`) — toggle star on a card (setStarred)

**Credit card payment** — `card/v1/cards/{id}/credit-card/payment`
- Card Detail (`CardDetailScreen`) — tap pay-credit-card-bill confirm button (payCreditCard, card_detail_screen.dart:~492)

**Card payment** — `bill/v1/payment/card_payment`
- Card Payment details (other bank card) (`CardPaymentDetailsScreen`) — Continue -> OTP -> TPIN confirm (CardPaymentController._submit)

**Qr payment cards** — `auth/v1/user/qr-settings/cards`
- QR Card Configuration (`QrCardConfigurationScreen`) — on load / toggle card (unreachable)

  *DEAD/UNREACHABLE: QrLoginSettingsController screens (QrPaymentWithoutLoginScreen, QrCardConfigurationScreen) are registered routes, but the only entry (QrScanPaymentsScreen from Profile) renders both options disabled (enabled:false, onTap shows 'temporarily unavailable'); nothing calls Get.toNamed to qrPaymentWithoutLogin/qrCardConfiguration.*

**Set qr payment card enabled** — `auth/v1/user/qr-settings/cards/{cardId}`
- QR Card Configuration (`QrCardConfigurationScreen`) — on load / toggle card (unreachable)

  *DEAD/UNREACHABLE: QrLoginSettingsController screens (QrPaymentWithoutLoginScreen, QrCardConfigurationScreen) are registered routes, but the only entry (QrScanPaymentsScreen from Profile) renders both options disabled (enabled:false, onTap shows 'temporarily unavailable'); nothing calls Get.toNamed to qrPaymentWithoutLogin/qrCardConfiguration.*


### CARD_REPLACEMENT — *Covered*

**Card replacement requests** — `card/v1/cards/replacement-requests`
- Report Card / Close Card (Lost-Stolen-Close / Replacement) (`CardReplacementScreen`) — on load (onInit -> loadRequests) lists 'Your Requests'

**Cancel card replacement request** — `card/v1/cards/replacement-requests/{requestId}`
- Report Card / Close Card (Lost-Stolen-Close / Replacement) (`CardReplacementScreen`) — tap cancel on a request, confirm 'Cancel Request?'

**Reveal card replacement** — `card/v1/cards/replacement-requests/{requestId}/reveal`
- Report Card / Close Card (Lost-Stolen-Close / Replacement) (`CardReplacementScreen`) — tap 'Reveal Card' on an approved request


### CHECK_BALANCE — *Covered*

**Account balance** — `transfer/v1/accounting/balance`
- Home (`HomeScreen`) — on load / balance refresh per account tile (HomeController -> refreshBalance)
- Account Detail (`AccountDetailScreen`) — on open (openDetail refreshBalance) if account has ledger balance
- Card Detail (`CardDetailScreen`) — on open (openDetail refreshBalance)
- My Accounts (`MyAccountsScreen`) — tap row / balance reveal toggle

**Credit card summary** — `card/v1/cards/{id}/credit-summary`
- Card Detail (`CardDetailScreen`) — on open for credit cards (openDetail -> loadCreditCardSummary); Credit summary section
- My Accounts (`MyAccountsScreen`) — tap credit card row (openDetail)
- Home (`HomeScreen`) — tap credit card tile (openDetail)


### EDIT_PERSONAL_DETAILS — *Covered*

**Profile** — `auth/v1/user`
- Profile (`ProfileScreen`) — on load and pull to refresh

**Update nickname** — `auth/v1/user/profile/nickname`
- Profile (`ProfileScreen`) — Edit options sheet > Update Nickname > Save (EditNameSheet)

**Upload profile image** — `auth/v1/user/profile/image`
- Profile (`ProfileScreen`) — pick avatar image

**Update mobile number** — `auth/v1/auth/mobile/update`
- Update Mobile Number (`UpdateMobileScreen`) — enter new number, OTP verified, then submit

  *Reached only via Services tab server-driven catalog id 'update_mobile_number' (local_service_catalog.dart).*

**Update email address** — `auth/v1/auth/email/update`
- Update Email Address (`UpdateEmailScreen`) — enter new email, OTP verified, then submit

  *Reached only via Services tab server-driven catalog id 'update_email_address'.*

**User demographic profile** — `customer/v1/me/demographic`
- Update Address (`UpdateAddressScreen`) — on load (prefill)
- Update KYC (`UpdateKycScreen`) — on load (status)

  *Both reached only via Services tab catalog ids update_address / update_kyc.*

**Update address** — `customer/v1/me/demographic`
- Update Address (`UpdateAddressScreen`) — tap Save

**Submit kyc** — `customer/v1/me/kyc`
- Update KYC (`UpdateKycScreen`) — tap Submit for Review

**My contacts** — `customer/v1/me/contacts`
- My Contacts (`ContactPriorityScreen`) — on load (loadAll)

**Submit profile change** — `service-request/v1/profile-changes`
- Profile Change Request (`ProfileChangeRequestScreen`) — tap Submit

**Profile changes** — `service-request/v1/profile-changes`
- Profile Change Request (`ProfileChangeRequestScreen`) — on load (history list)

**Submit contact priority** — `service-request/v1/contact-priority`
- My Contacts (`ContactPriorityScreen`) — tap 'Set as Primary' on a contact

**Contact priority requests** — `service-request/v1/contact-priority`
- My Contacts (`ContactPriorityScreen`) — on load (loadAll)


### FAILED_TRANSFER — *Partial — no API to check/retry a single transfer*

**Transaction history** — `transfer/v1/accounting/transaction-list`
- Transaction History (`TransactionHistoryScreen`) — on load, pull to refresh, scroll for more, apply filter

**Submit dispute** — `service-request/v1/disputes`
- Dispute a Transaction (`DisputeTransactionScreen`) — tap Submit Dispute

**Disputes by account** — `service-request/v1/disputes`
- Dispute a Transaction (`DisputeTransactionScreen`) — on load / account change (history list)

**Submit complaint** — `support/v1/complaints`
- File a Complaint (`ComplaintScreen`) — tap Submit Complaint

**My complaints** — `support/v1/complaints`
- File a Complaint (`ComplaintScreen`) — on open (onInit loadComplaints), likely reloaded after submit


### FALLBACK — *Conversational — APIs used as hand-off*

**Polygon ai chat** — `support/v1/ai/chat`
- Polygon AI (logged in) (`PolygonAiChatScreen`) — send message (SSE stream)

  *entry: AppShell AI icon -> AppRoutes.polygonAi*

**Polygon ai public chat** — `support/v1/ai/public/chat`
- Polygon AI (login screen, pre-auth) (`PublicAiChatScreen`) — send message (SSE stream)

  *entry: login screen AI icon -> AppRoutes.polygonAiPublic*

**Polygon ai status** — `support/v1/ai/status`
- Polygon AI (logged in) (`PolygonAiChatScreen`) — on open (controller onInit _checkStatus)

**Polygon ai public status** — `support/v1/ai/public/status`
- Polygon AI (login screen, pre-auth) (`PublicAiChatScreen`) — on open (_checkStatus)

**Faq categories** — `support/v1/faq-categories`
- FAQ (`FaqScreen`) — on open (onInit loadAll)

**Faqs** — `support/v1/faqs`
- FAQ (`FaqScreen`) — on open (onInit loadAll)

**Submit complaint** — `support/v1/complaints`
- File a Complaint (`ComplaintScreen`) — tap Submit Complaint


### FEES — *Covered (quote only, no full fee list API)*

**Transaction charge** — `transfer/v1/transaction-type/charge-with-amount`
- Polygon Bank Account Transfer (`PolygonBankAccountScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Transfer to Other Bank (`OtherBankScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Own Account Transfer (`OwnAccountScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Cash by Code (`CashByCodeScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Education Fee (`EducationScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Club Fee (`ClubFeeScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Mobile Recharge (`MobileRechargeScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Email Transfer (`EmailTransferAmountScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Send Gift (`GiftScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Zakat (`ZakatScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Insurance Premium (`InsuranceScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Universal Pension (`PensionScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Card Bill Payment (`CardPaymentDetailsScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Donation (`DonationScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges
- Wallet Transfer (`WalletTransferScreen`) — as amount/beneficiary changes (debounced ~400ms) -> _loadCharges


### GREETING — *Conversational — no API needed*

No endpoints.

### LOST_OR_STOLEN_CARD — *Covered*

**Report lost stolen card** — `card/v1/cards/{cardId}/replacement-requests`
- Report Card / Close Card (Lost-Stolen-Close / Replacement) (`CardReplacementScreen`) — confirm Report Lost/Stolen after OTP + TPIN (startReport -> _submit); reached from Freeze reason sheet (lost/stolen/close) or route reportLostStolenCard/requestCardReplacement

**Freeze card** — `card/v1/cards/{cardId}/freeze`
- Freeze / Unfreeze Card (`FreezeCardScreen`)
- Card Settings sheet (from Card Detail) (`CardSettingsSheet`)

  *Freeze triggered from FreezeCardScreen (reason 'Other' in freeze reason sheet) and Card Settings sheet freeze toggle; strong-auth (OTP+TPIN) follows. Lost/stolen/close reasons route to CardReplacementScreen instead.*


### MINI_STATEMENT — *Covered*

**Transaction history** — `transfer/v1/accounting/transaction-list`
- Transaction History (`TransactionHistoryScreen`) — on load, pull to refresh, scroll for more, apply filter

**Account transactions** — `polygon-bank/v1/accounts/{id}/transactions`
- Account Detail (`AccountDetailScreen`) — on open from list/home (openDetail fires fetches)
- Card Detail (`CardDetailScreen`) — on open (openDetail fires fetches)
- Home (`HomeScreen`) — tap tile (openDetail)
- My Accounts (`MyAccountsScreen`) — tap row (openDetail)

  *openDetail -> _loadDetail -> loadTransactions; recent transactions tab on detail screens*

**Credit card statement detail** — `card/v1/cards/{id}/statements`
- Card Detail (`CardDetailScreen`) — initState + switching Billed/Unbilled or month (loadStatementDetail), credit card only

**Expense tracker category transactions** — `report/v1/expense-tracker/categories/{categoryRef}/transactions`
- Category Transactions (`CategoryTransactionsScreen`) — on open (selectCategory), tapped from tracker category list


### TRANSFER — *Covered*

**Own account transfer** — `transfer/v1/bank-transfer/own-account`
- Own Account Transfer (`OwnAccountScreen`) — tap Continue then PIN entry (TPIN sheet confirm)

**City bank transfer** — `transfer/v1/bank-transfer/city-bank`
- Polygon Bank Account (calls city-bank transfer) (`PolygonBankAccountScreen`) — tap Continue then PIN entry (TPIN sheet confirm)

**Other bank transfer** — `transfer/v1/bank-transfer/other-bank`
- Transfer to Other Bank (`OtherBankScreen`) — tap Continue then PIN entry (TPIN sheet confirm)

**Other banks** — `transfer/v1/other-banks`
- *(no reachable screen calls this)*

  *Dead code: GetOtherBanksUseCase only registered in bank_transfer_binding.dart; never invoked*

**Gift transfer** — `transfer/v1/bank-transfer/gift`
- Gift (`GiftScreen`) — tap Confirm & Send then PIN entry

**Gift received** — `transfer/v1/bank-transfer/gift/received`
- Transaction History (`TransactionHistoryScreen`) — on load (received gifts list)

**Do transaction** — `transfer/v1/transactions/do-transaction`
- *(no reachable screen calls this)*

  *Dead code: TransferPolygonAccountUseCase is only registered in bank_transfer_binding.dart; no controller calls it (Polygon Bank Account screen uses TransferCityBankUseCase)*

**Linked account** — `transfer/v1/accounting/linked-account`
- Own Account Transfer (`OwnAccountScreen`) — on account selection (linked-account lookup)

**Email transfer create** — `transfer/v1/email-transfer`
- Email Transfer (amount step) (`EmailTransferAmountScreen`) — tap Continue then PIN entry (TPIN sheet confirm)

**Email transfer list** — `transfer/v1/email-transfer`
- Email Transfer (entry) (`EmailTransferEntryScreen`) — on load (history existence check, size 1)
- Email Transfer (history list) (`EmailTransferListScreen`) — on load, tab switch, pagination

**Email transfer details** — `transfer/v1/email-transfer/{id}`
- Email Transfer Details (`EmailTransferDetailsScreen`) — on load

**Email transfer cancel** — `transfer/v1/email-transfer/{id}/cancel`
- Email Transfer Details (`EmailTransferDetailsScreen`) — tap Cancel transfer

**Email transfer resend** — `transfer/v1/email-transfer/{id}/resend-notification`
- Email Transfer Details (`EmailTransferDetailsScreen`) — tap Resend notification

**Wallet transfer** — `transfer/v1/wallet-transfer`
- Wallet Transfer (`WalletTransferScreen`) — tap Continue then PIN entry (TPIN sheet confirm)

**Wallet verify** — `transfer/v1/wallet-transfer/verify`
- Wallet Transfer (`WalletTransferScreen`) — while typing wallet number (400ms debounce)

**Pay by qr** — `merchant/v1/qr/pay`
- Confirm Payment (`QrPaymentConfirmScreen`) — tap Continue then PIN entry (TPIN sheet confirm)
- QR Transfer (`QrTransferConfirmScreen`) — tap Continue then PIN entry (TPIN sheet confirm)

**Parse qr** — `merchant/v1/qr/parse`
- Scan or Share (QR scanner) (`QrScanScreen`) — on QR detected or Upload QR Image

**Parse qr by id** — `merchant/v1/qr/by-id`
- Scan or Share (QR scanner) (`QrScanScreen`) — submit Enter QR ID dialog

**Qr history** — `merchant/v1/qr/history`
- QR Payment History (`QrHistoryScreen`) — on load, refresh, pagination

**Beneficiaries** — `beneficiary/v1/beneficiaries`
- Beneficiary (`BeneficiaryScreen`) — on load (list GET) / add (POST) via form
- Add/Edit Beneficiary (`BeneficiaryFormScreen`) — POST create on submit
- Home (`HomeScreen`) — on load (HomeController beneficiary section)
- Education (`EducationScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Club Fee (`ClubFeeScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Mobile Recharge (`MobileRechargeScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Zakat (`ZakatScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Insurance (`InsuranceScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Universal Pension (`PensionScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Card Payment Details (`CardPaymentDetailsScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Donation (`DonationScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Polygon Bank Account (`PolygonBankAccountScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Transfer to Other Bank (`OtherBankScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Gift (`GiftScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)
- Wallet Transfer (`WalletTransferScreen`) — on load (BeneficiaryRow saved-beneficiary strip, GET filtered by service type)

  *GET list: BeneficiaryScreen + Home; GET by service type via BeneficiaryRow on 12 screens; POST on BeneficiaryFormScreen submit*

**Beneficiary by id** — `beneficiary/v1/beneficiaries/{id}`
- Add/Edit Beneficiary (`BeneficiaryFormScreen`) — PATCH nickname on save when editing
- Beneficiary (`BeneficiaryScreen`) — DELETE on delete action (list / details sheet)

**Beneficiary photo** — `beneficiary/v1/beneficiaries/{id}/photo`
- Add/Edit Beneficiary (`BeneficiaryFormScreen`) — after create when a photo was picked

**Beneficiary pin** — `beneficiary/v1/beneficiaries/{id}/pin`
- Beneficiary (`BeneficiaryScreen`) — tap Pin/Unpin icon (also via beneficiary details sheet, which is also opened from Home)

**Polygon beneficiary info** — `polygon-bank/v1/accounts/by-number/{identifier}`
- Polygon Bank Account (`PolygonBankAccountScreen`) — on recipient account lookup (Continue)
- Gift (`GiftScreen`) — recipient lookup (Continue from Recipient step)
- Your Gift (received gift detail) (`GiftReceivedDetailScreen`) — on load (resolves sender name)

**My limit** — `transfer/v1/my-limit/{accountIdentifier}`
- Transfer Limit (`TransferLimitScreen`) — GET on load/refresh/account change; PUT (change limit) after OTP + TPIN

**Cancel pending limit change** — `transfer/v1/my-limit/pending/{requestId}`
- Transfer Limit (`TransferLimitScreen`) — tap cancel pending change


## Part 2 — APIs not covered by any of the 14 intents

Candidates for new intents.

### Bill Payment

**Club fee payment** — `bill/v1/payment/club_fee`
- Club Fee (`ClubFeeScreen`) — after TPIN confirm (_submit)

**Donation payment** — `bill/v1/payment/donation`
- Donation (`DonationScreen`) — after TPIN confirm (_submit)

**Education payment** — `bill/v1/payment/education`
- Education Fee (`EducationScreen`) — after TPIN confirm (_submit)

**Insurance payment** — `bill/v1/payment/insurance`
- Insurance Premium (`InsuranceScreen`) — after TPIN confirm (_submit)

**Mobile operators** — `transfer/v1/mobile-operators`
- Mobile Recharge (`MobileRechargeScreen`) — on screen open (controller onInit -> _loadOperators)

**Mobile recharge packages** — `transfer/v1/mobile-recharge-packages`
- Mobile Recharge (`MobileRechargeScreen`) — tap Continue on details step (continueToAmount -> _loadPackages)

**Mobile recharge** — `bill/v1/payment/mobile_recharge`
- Mobile Recharge (`MobileRechargeScreen`) — after TPIN/OTP confirm (confirmTpin -> _submit)

**Universal pension payment** — `bill/v1/payment/universal_pension`
- Universal Pension (`PensionScreen`) — after TPIN confirm (_submit)

**Verify member** — `bill/v1/biller-subscribers/verify`
- Club Fee (`ClubFeeScreen`) — typing member ID (auto lookup) and tap Continue

**Verify policy** — `bill/v1/biller-subscribers/verify`
- Insurance Premium (`InsuranceScreen`) — typing policy number (auto lookup) and tap Continue

**Verify student** — `bill/v1/biller-subscribers/verify`
- Education Fee (`EducationScreen`) — typing student ID (auto lookup) and tap Continue

**Verify subscriber** — `bill/v1/biller-subscribers/verify`
- Universal Pension (`PensionScreen`) — typing subscriber ID (auto lookup) and tap Continue

**Zakat payment** — `bill/v1/payment/zakat`
- Zakat (`ZakatScreen`) — after TPIN confirm (_submit)


### Loan

**Calculate emi** — `loan/v1/loans/emi/calculate`
- EMI Calculator (`EmiCalculatorScreen`) — tap Calculate

**Calculate murabaha** — `loan/v1/loans/financing/calculate`
- Loan Request / Financing Request (`LoanRequestScreen`) — tap 'See Today's Estimate' (Murabaha mode only)

  *Not used by EMI Calculator or My Loans; only Loan Request*

**Close loan** — `loan/v1/loans/{loanIdentifier}/closure`
- My Loans (`LoanScreen`) — tap Close Loan -> OTP -> TPIN confirm

**Loan closure quote** — `loan/v1/loans/{loanIdentifier}/closure/quote`
- My Loans (`LoanScreen`) — tap closure-quote button on a loan card

**Loan emi schedule** — `loan/v1/loans/{loanIdentifier}/emi-schedule`
- My Loans (`LoanScreen`) — tap a loan card to expand EMI schedule; also reloaded after EMI payment

**Loan request document** — `service-request/v1/loan-requests/{loanRequestId}/document`
- Loan Request / Financing Request (`LoanRequestScreen`) — tap view document on a request card

  *Presigned URL fetch; uploading a document uses a different (non-listed) getter*

**My loan requests** — `service-request/v1/loan-requests`
- Loan Request / Financing Request (`LoanRequestScreen`) — on load (past requests list)

**Pay loan emi** — `loan/v1/loans/{loanIdentifier}/emi/pay`
- My Loans (`LoanScreen`) — tap Pay EMI -> OTP -> TPIN confirm

**Submit loan request** — `service-request/v1/loan-requests`
- Loan Request / Financing Request (`LoanRequestScreen`) — tap Submit (then LoanRequestSuccessScreen)

  *Title is 'Financing Request' for Islamic accounts*


### Deposits & Products

**Exchange houses** — `product/v1/remittance/exchange-houses`
- Receive Remittance (`ReceiveRemittanceScreen`) — on load

**Products by type** — `product/v1/products/type/{type}`
- Open a Fixed Deposit (`OpenFixedDepositScreen`) — on load (type FIXED_DEPOSIT)
- Open a DPS (`OpenDpsScreen`) — on load (type DPS)

**My deposit closures** — `service-request/v1/deposit-closures`
- Deposit Closure Request (`DepositClosureRequestScreen`) — on load (history list)

**Open dps** — `product/v1/dps`
- Open a DPS (`OpenDpsScreen`) — tap Continue/submit (POST open DPS)
- Mudarabah Profit (`MudarabahProfitScreen`) — on load (GET list of user's DPS)
- Deposit Closure Request (`DepositClosureRequestScreen`) — on load (GET list of user's open DPS to pick from)

  *Base URL: GET on it lists the user's open deposits (not 'open'); POST on it opens one. Used by 3 features as noted*

**Open fixed deposit** — `product/v1/fixed-deposit`
- Open a Fixed Deposit (`OpenFixedDepositScreen`) — tap Continue/submit (POST open FD)
- Mudarabah Profit (`MudarabahProfitScreen`) — on load (GET list of user's FDs)
- Deposit Closure Request (`DepositClosureRequestScreen`) — on load (GET list of user's open FDs to pick from)

  *Base URL: GET on it lists the user's open deposits (not 'open'); POST on it opens one. Used by 3 features as noted*

**Receive remittance** — `product/v1/remittance/receive`
- Receive Remittance (`ReceiveRemittanceScreen`) — tap Continue/submit

**Submit deposit closure** — `service-request/v1/deposit-closures`
- Deposit Closure Request (`DepositClosureRequestScreen`) — tap Submit (then DepositClosureSuccessScreen)


### Cheque Book

**Cheque books** — `service-request/v1/cheque-books`
- Cheque Book (`ChequeBookScreen`) — on load / on account change (lists cheque books)
- Stop Cheque (`ChequeStopScreen`) — on load / account change (loads cheque books to pick from)
- Positive Pay (`PositivePayScreen`) — on load / account change (loads cheque books to pick from)

  *GET list of cheque books per account; same use case reused by 3 controllers*

**Cheque stop** — `service-request/v1/cheque-stop`
- Stop Cheque (`ChequeStopScreen`) — tap Continue/submit stop (then success screen)

**Positive pay** — `service-request/v1/positive-pay`
- Positive Pay (`PositivePayScreen`) — tap Continue/submit (then success screen)

**Request cheque book** — `service-request/v1/cheque-books`
- Request Cheque Book (`RequestChequeBookScreen`) — tap Continue/submit (then success screen)


### Certificates

**Certificate document** — `service-request/v1/certificates/{requestId}/document`
- Certificate Request (`CertificateRequestScreen`) — tap download on a past request

**Certificates by account** — `service-request/v1/certificates`
- Certificate Request (`CertificateRequestScreen`) — on load / on account change (history list)

**Submit certificate** — `service-request/v1/certificates`
- Certificate Request (`CertificateRequestScreen`) — tap Submit Request


### Offers & Rewards

**Offers and vouchers** — `campaign/v1/campaigns`
- Offers & Vouchers (`OffersAndVouchersScreen`) — on open (onInit getData)

**Points history** — `campaign/v1/rewards/points-history`
- Points History (`PointsHistoryScreen`) — on open

**Redeemed vouchers** — `campaign/v1/rewards/vouchers`
- My Vouchers (`MyVouchersScreen`) — on open

**Rewards summary** — `campaign/v1/rewards/summary`
- MyRewards (`MyRewardsScreen`) — on open


### Exchange Rates

**Exchange rates** — `support/v1/exchange-rates`
- Exchange Rates (`ExchangeRatesScreen`) — on open


### Expense Tracker

**Expense tracker all categories** — `report/v1/expense-tracker/categories/all`
- Income and Expense Tracker / Wealth (via shared controller) (`ExpenseTrackerScreen`) — controller onInit loadCategories (EXPENSE+INCOME); reload after returning from My Categories
- Transaction Detail (change category sheet uses these lists) (`TransactionDetailScreen`) — uses preloaded lists
- Category picker inside payment/transfer forms (`TransactionCategorySelector (widget)`) — initState on any screen showing it: Zakat, Wallet Transfer, Own Account, Polygon Bank Account, Other Bank, Email Transfer, Cash by Code, QR Transfer Confirm, Card Payment, Mobile Recharge, Club Fee, Donation, Pension, Insurance, Education (via CategoryFormSection in TransactionFormCard)

  *core CategoryHttpImpl calls this URL (GetAllCategoriesUseCase) for form pickers; expense_tracker repo calls it for tracker categories*

**Expense tracker exclude transaction** — `report/v1/expense-tracker/transactions/{transactionId}/exclude`
- Transaction Detail (`TransactionDetailScreen`) — tap Exclude and confirm dialog

**Expense tracker my categories** — `report/v1/expense-tracker/my-categories`
- My Categories (`MyCategoriesScreen`) — GET on open (CustomCategoryController onInit/load, pull-to-refresh); POST on New category sheet create

**Expense tracker my category** — `report/v1/expense-tracker/my-categories/{categoryId}`
- My Categories (`MyCategoriesScreen`) — PATCH on rename / activate toggle; DELETE on remove category tile action

**Expense tracker summary** — `report/v1/expense-tracker/summary`
- Wealth (bottom-nav tab 4) (`WealthScreen`) — first Get.find of ExpenseTrackerController (lazyPut) -> onInit loadOverview; pull-to-refresh
- Income and Expense Tracker (`ExpenseTrackerScreen`) — on open (shared controller onInit/loadOverview), month change, pull-to-refresh

**Expense tracker trend** — `report/v1/expense-tracker/trend`
- Wealth (bottom-nav tab 4) (`WealthScreen`) — first Get.find of ExpenseTrackerController (lazyPut) -> onInit loadOverview; pull-to-refresh
- Income and Expense Tracker (`ExpenseTrackerScreen`) — on open (shared controller onInit/loadOverview), month change, pull-to-refresh

**Expense tracker update transaction category** — `report/v1/expense-tracker/transactions/{transactionId}/category`
- Transaction Detail (`TransactionDetailScreen`) — tap change category and pick one in bottom sheet


### QR (receive money)

**Generate dynamic qr** — `merchant/v1/qr/dynamic`
- Add Amount (`AddAmountScreen`) — tap generate QR

**Static qr** — `merchant/v1/qr/static`
- Scan or Share (My QR tab) (`QrScanScreen`) — on load (MyQrController.onInit)
- My QR (dynamic) (`DynamicQrScreen`) — shares MyQrController; reload static QR


### Authentication & Registration

**Biometric challenge** — `auth/v1/auth/biometric/challenge`
- Login (`LoginScreen`) — tap biometric login button

**Biometric enroll** — `auth/v1/auth/biometric/enroll`
- Login Settings (`LoginSettingsScreen`) — toggle Biometric Login ON (enrolls public key first)
- Verify New Device - Set Login Method (`SetLoginMethodScreen`) — tap Finish/Continue

**Biometric login** — `auth/v1/auth/biometric/login`
- Login (`LoginScreen`) — tap biometric login button (after challenge signed)

**Biometric toggle** — `auth/v1/auth/biometric/{deviceId}`
- Login Settings (`LoginSettingsScreen`) — toggle Biometric Login switch

**Check username** — `polygon-bank/v1/registration/username/check`
- Register - Choose Username (`RegisterUsernameScreen`) — as user types username (onUsernameChanged availability check)

**Device bind** — `auth/v1/auth/device/bind`
- Verify New Device - OTP sheet (`DeviceOtpVerifySheet`) — enter OTP and tap Verify / Resend (shown from SelectVerifyScreen)

  *DeviceVerificationController.verifyOtpAndLogin: verify OTP then bind device*

**Device otp send** — `auth/v1/auth/otp/send`
- Verify New Device - Select Account (`SelectVerifyScreen`) — on load (loads accounts for username); tap Continue sends OTP
- Verify New Device - OTP sheet (`DeviceOtpVerifySheet`) — enter OTP and tap Verify / Resend (shown from SelectVerifyScreen)

  *SendDeviceOtpUseCase: DeviceVerificationController.continueToOtp -> sendOtp, and resend in sheet*

**Active login background** — `support/v1/login-background/active`
- Welcome (`WelcomeScreen`) — VideoBackground refreshes playlist in background on show
- Login (`LoginScreen`) — tap Login button (username + PIN/password)

  *Via VideoBackground widget (also stale-while-revalidate).*

**Device** — `auth/v1/devices/{deviceId}`
- App startup (background) (`StartupGate / BootstrapService`) — on app launch: BootstrapService.initialize() -> checkDevice(deviceId)
- Login (`LoginScreen`) — on load, fallback device check when cached user exists (LoginScreenController._fetchDeviceCheck)

**Otp verify** — `otp/v1/verify`
- My Contacts (Set as Primary) (`ContactPriorityScreen`) — OtpVerification.request sheet: tap Set as Primary
- Polygon Bank Account Transfer (`PolygonBankAccountScreen`) — OtpVerification.request sheet: tap Continue
- Transfer to Other Bank (`OtherBankScreen`) — OtpVerification.request sheet: tap Continue
- Own Account Transfer (`OwnAccountScreen`) — OtpVerification.request sheet: tap Continue
- Open a Fixed Deposit (`OpenFixedDepositScreen`) — OtpVerification.request sheet: tap Continue
- Receive Remittance (`ReceiveRemittanceScreen`) — OtpVerification.request sheet: tap Continue
- Open a DPS (`OpenDpsScreen`) — OtpVerification.request sheet: tap Continue
- Cash by Code (`CashByCodeScreen`) — OtpVerification.request sheet: tap Continue
- Dispute a Transaction (`DisputeTransactionScreen`) — OtpVerification.request sheet: tap Submit Dispute
- QR Transfer (`QrTransferConfirmScreen`) — OtpVerification.request sheet: tap Proceed/Confirm
- Confirm Payment (QR) (`QrPaymentConfirmScreen`) — OtpVerification.request sheet: tap Confirm Payment
- Loan / Financing Request (`LoanRequestScreen`) — OtpVerification.request sheet: tap Submit
- Education Fee (`EducationScreen`) — OtpVerification.request sheet: tap Continue
- Club Fee (`ClubFeeScreen`) — OtpVerification.request sheet: tap Continue
- Mobile Recharge (`MobileRechargeScreen`) — OtpVerification.request sheet: tap Continue
- Email Transfer (`EmailTransferAmountScreen`) — OtpVerification.request sheet: tap Continue
- Certificate Request (`CertificateRequestScreen`) — OtpVerification.request sheet: tap Submit Request
- International Transactions (card) (`CardInternationalProfileScreen`) — OtpVerification.request sheet: toggle international on/off or Update Limit
- Apply for Virtual Card (`RequestVirtualCardScreen`) — OtpVerification.request sheet: tap Continue
- Card PIN Reset - Reason (`SelectPinResetReasonScreen`) — OtpVerification.request sheet: tap Continue
- Report Lost/Stolen/Close or Request Replacement (card) (`CardReplacementScreen`) — OtpVerification.request sheet: tap Report Card / Request
- Freeze / Unfreeze Card (`FreezeCardScreen`) — OtpVerification.request sheet: tap Freeze / Unfreeze
- Card Settings sheet (freeze, close card) (`CardSettingsSheet`) — OtpVerification.request sheet: tap freeze/unfreeze/close (opened from CardDetailScreen)
- Deposit Closure Request (`DepositClosureRequestScreen`) — OtpVerification.request sheet: tap Submit Request
- My Loans (Pay EMI / Close Loan) (`LoanScreen`) — OtpVerification.request sheet: tap Pay EMI / Close Loan
- Send Gift (`GiftScreen`) — OtpVerification.request sheet: tap Confirm & Send
- Positive Pay (`PositivePayScreen`) — OtpVerification.request sheet: tap Continue
- Request Cheque Book (`RequestChequeBookScreen`) — OtpVerification.request sheet: tap Continue
- Stop Cheque (`ChequeStopScreen`) — OtpVerification.request sheet: tap Continue
- Zakat (`ZakatScreen`) — OtpVerification.request sheet: tap Continue
- Insurance Premium (`InsuranceScreen`) — OtpVerification.request sheet: tap Continue
- Profile Change Request (`ProfileChangeRequestScreen`) — OtpVerification.request sheet: tap Submit Request
- Universal Pension (`PensionScreen`) — OtpVerification.request sheet: tap Continue
- Card Bill Payment (`CardPaymentDetailsScreen`) — OtpVerification.request sheet: tap Continue
- Transfer Limit (`TransferLimitScreen`) — OtpVerification.request sheet: tap Update Limit
- Update Mobile Number (`UpdateMobileScreen`) — OtpVerification.request sheet: tap Continue
- Update Email Address (`UpdateEmailScreen`) — OtpVerification.request sheet: tap Continue
- Donation (`DonationScreen`) — OtpVerification.request sheet: tap Continue
- Wallet Transfer (bKash/Nagad/etc.) (`WalletTransferScreen`) — OtpVerification.request sheet: tap Continue
- Register - Verify Contact (OTP) (`RegisterVerifyContactScreen`) — enter OTP and verify / resend
- Verify New Device - OTP sheet (`DeviceOtpVerifySheet`) — enter OTP and tap Verify / Resend (shown from SelectVerifyScreen)

  *Core OtpVerificationController.sendOtp, shown as OtpVerificationSheet (core/presentation/widgets/otp/) over every screen listed; any new transaction confirm step calls OtpVerification.request(phone). Also used by registration (RegisterVerifyContactScreen) and new-device verification (DeviceOtpVerifySheet) via VerifyRegistrationOtpUseCase.*

**Set password** — `auth/v1/auth/set-pin/{accountOrCardNumber}`
- Register - Set Password (`RegisterPasswordScreen`) — tap Complete/Submit (completeRegistration)

**Set username** — `polygon-bank/v1/registration/username`
- Register - Choose Username (`RegisterUsernameScreen`) — tap Continue

**Username login** — `auth/v1/auth/login";

  @override
  String getDeviceUrl(String deviceId) =>
      `
- Login (`LoginScreen`) — tap Login button (username + PIN/password)
- Verify New Device - OTP sheet (auto re-login after device bind) (`DeviceOtpVerifySheet`) — tap Verify OTP -> DeviceVerificationController._completeLogin() calls DoLoginUseCase

  *Also called with a fresh login request right after device binding in device verification flow.*

**Verify contact** — `polygon-bank/v1/registration/verify-contact/{accountOrCardNumber}`
- Register - Verify Contact (`RegisterVerifyContactScreen`) — tap Send OTP / Continue (sends OTP to the account contact); resend


### Security Settings

**Delete device** — `auth/v1/devices/{deviceId}`
- Device Management (`DeviceManagementScreen`) — tap Remove device + confirm (also used for rename PATCH on same path)

  *Same URL getter used for rename (PATCH) via RenameDeviceUseCase from Device Management.*

**Device login history** — `auth/v1/devices/{deviceId}/login-history`
- Device Management (`DeviceManagementScreen`) — expand/open a device's login history; Load more

**Devices** — `auth/v1/devices`
- Device Management (`DeviceManagementScreen`) — on load and pull to refresh

**Qr login settings** — `auth/v1/user/qr-settings`
- QR Payment Without Login (`QrPaymentWithoutLoginScreen`) — on load / Save (unreachable)

  *DEAD/UNREACHABLE: QrLoginSettingsController screens (QrPaymentWithoutLoginScreen, QrCardConfigurationScreen) are registered routes, but the only entry (QrScanPaymentsScreen from Profile) renders both options disabled (enabled:false, onTap shows 'temporarily unavailable'); nothing calls Get.toNamed to qrPaymentWithoutLogin/qrCardConfiguration.*

**Identity verify account** — `auth/v1/auth/identity/verify-account`
- Login PIN / Login Password - Verification (`LoginSecretVerificationScreen`) — tap Verify

  *Account option.*

**Identity verify card** — `auth/v1/auth/identity/verify-card`
- Login PIN / Login Password - Verification (`LoginSecretVerificationScreen`) — tap Verify

  *Reached from Login Settings (Change PIN / Change Password). Card option.*

**Login settings status** — `auth/v1/auth/login-settings/status`
- Login Settings (`LoginSettingsScreen`) — on load

**Otp lock status** — `auth/v1/auth/settings/otp-lock`
- OTP Settings (`OtpSettingsScreen`) — on load

**Otp lock** — `auth/v1/auth/settings/otp-lock`
- OTP Settings (`OtpSettingsScreen`) — toggle Lock OTP ON + confirm

**Otp unlock** — `auth/v1/auth/settings/otp-unlock`
- OTP Settings (`OtpSettingsScreen`) — toggle Lock OTP OFF

**Pin login toggle** — `auth/v1/auth/settings/pin-login`
- Login Settings (`LoginSettingsScreen`) — toggle PIN Login switch

**Reset login password** — `auth/v1/auth/reset-password`
- Set Login Password (`SetLoginSecretScreen`) — tap Submit (target = password)

**Reset login pin** — `auth/v1/auth/pin/reset`
- Set Login PIN (`SetLoginSecretScreen`) — tap Submit (target = PIN)

**Tpin reset** — `auth/v1/auth/tpin/reset`
- TPIN Settings - Set New TPIN (`ResetTpinScreen`) — tap Submit/Confirm

**Tpin reset verify account** — `auth/v1/auth/tpin/reset/verify-account`
- TPIN Settings - Verification (`TpinVerificationScreen`) — tap Verify

  *Account option selected.*

**Tpin reset verify card** — `auth/v1/auth/tpin/reset/verify-card`
- TPIN Settings - Verification (`TpinVerificationScreen`) — tap Verify

  *Reached from Profile > Security > TPIN Settings and from TpinSetupPromptSheet (mandatory TPIN setup). Card option selected.*

**Update qr login settings** — `auth/v1/user/qr-settings`
- QR Payment Without Login (`QrPaymentWithoutLoginScreen`) — on load / Save (unreachable)

  *DEAD/UNREACHABLE: QrLoginSettingsController screens (QrPaymentWithoutLoginScreen, QrCardConfigurationScreen) are registered routes, but the only entry (QrScanPaymentsScreen from Profile) renders both options disabled (enabled:false, onTap shows 'temporarily unavailable'); nothing calls Get.toNamed to qrPaymentWithoutLogin/qrCardConfiguration.*


### Profile & Account

**Delete account** — `auth/v1/user`
- Profile (`ProfileScreen`) — Security > Delete Polygon Account confirm

  *Effectively unreachable: menu entry is constructed with enabled: false (profile_screen.dart ~line 241), so the tap handler is disabled.*

**Logout** — `auth/v1/auth/logout`
- Profile (`ProfileScreen`) — tap Logout + confirm
- Login Password reset - Success (`LoginSecretResetSuccessScreen`) — tap Finish after password reset (forces logout)

  *ProfileCacheImpl.logout also calls unregisterDeviceTokenUrl first.*


### Notifications

**Device token** — `notification/v1/device-token`
- App startup (background) (`BootstrapService`) — FCM onTokenRefresh -> syncDeviceToken (only if logged in)
- After login (background) (`LoginScreen / SelectVerify flow (AuthCacheImpl)`) — after any successful login (password/PIN/biometric) _persistSessionIfPresent registers FCM token

**Notifications** — `notification/v1/notifications`
- Notifications (`NotificationScreen`) — on load and pull to refresh (opened from Home header bell)

**Subscribe topic** — `notification/v1/topics/{topic}/subscribe`
- *(no reachable screen calls this)*

  *DEAD: SubscribeTopicUseCase only registered in app_binding.dart; never invoked from any controller/service.*

**Unregister device token** — `notification/v1/device-token/{deviceId}`
- Profile (`ProfileScreen`) — tap Logout + confirm (ProfileCacheImpl.logout best-effort unregister before logout call)

  *Background side-effect of logout.*

**Unsubscribe topic** — `notification/v1/topics/{topic}/unsubscribe`
- *(no reachable screen calls this)*

  *DEAD: UnsubscribeTopicUseCase only registered in app_binding.dart; never invoked.*


### Shared / Core

**Expense tracker categories** — `report/v1/expense-tracker/categories`
- *(no reachable screen calls this)*

  *DEAD: reached only via CategoryRepository.getCategories / GetCategoriesUseCase, which is registered in app_binding.dart but never called. Live category selector (TransactionCategorySelector) uses GetAllCategoriesUseCase -> expenseTrackerAllCategoriesUrl (a different getter).*

**Otp send** — `otp/v1/send`
- My Contacts (Set as Primary) (`ContactPriorityScreen`) — OtpVerification.request sheet: tap Set as Primary
- Polygon Bank Account Transfer (`PolygonBankAccountScreen`) — OtpVerification.request sheet: tap Continue
- Transfer to Other Bank (`OtherBankScreen`) — OtpVerification.request sheet: tap Continue
- Own Account Transfer (`OwnAccountScreen`) — OtpVerification.request sheet: tap Continue
- Open a Fixed Deposit (`OpenFixedDepositScreen`) — OtpVerification.request sheet: tap Continue
- Receive Remittance (`ReceiveRemittanceScreen`) — OtpVerification.request sheet: tap Continue
- Open a DPS (`OpenDpsScreen`) — OtpVerification.request sheet: tap Continue
- Cash by Code (`CashByCodeScreen`) — OtpVerification.request sheet: tap Continue
- Dispute a Transaction (`DisputeTransactionScreen`) — OtpVerification.request sheet: tap Submit Dispute
- QR Transfer (`QrTransferConfirmScreen`) — OtpVerification.request sheet: tap Proceed/Confirm
- Confirm Payment (QR) (`QrPaymentConfirmScreen`) — OtpVerification.request sheet: tap Confirm Payment
- Loan / Financing Request (`LoanRequestScreen`) — OtpVerification.request sheet: tap Submit
- Education Fee (`EducationScreen`) — OtpVerification.request sheet: tap Continue
- Club Fee (`ClubFeeScreen`) — OtpVerification.request sheet: tap Continue
- Mobile Recharge (`MobileRechargeScreen`) — OtpVerification.request sheet: tap Continue
- Email Transfer (`EmailTransferAmountScreen`) — OtpVerification.request sheet: tap Continue
- Certificate Request (`CertificateRequestScreen`) — OtpVerification.request sheet: tap Submit Request
- International Transactions (card) (`CardInternationalProfileScreen`) — OtpVerification.request sheet: toggle international on/off or Update Limit
- Apply for Virtual Card (`RequestVirtualCardScreen`) — OtpVerification.request sheet: tap Continue
- Card PIN Reset - Reason (`SelectPinResetReasonScreen`) — OtpVerification.request sheet: tap Continue
- Report Lost/Stolen/Close or Request Replacement (card) (`CardReplacementScreen`) — OtpVerification.request sheet: tap Report Card / Request
- Freeze / Unfreeze Card (`FreezeCardScreen`) — OtpVerification.request sheet: tap Freeze / Unfreeze
- Card Settings sheet (freeze, close card) (`CardSettingsSheet`) — OtpVerification.request sheet: tap freeze/unfreeze/close (opened from CardDetailScreen)
- Deposit Closure Request (`DepositClosureRequestScreen`) — OtpVerification.request sheet: tap Submit Request
- My Loans (Pay EMI / Close Loan) (`LoanScreen`) — OtpVerification.request sheet: tap Pay EMI / Close Loan
- Send Gift (`GiftScreen`) — OtpVerification.request sheet: tap Confirm & Send
- Positive Pay (`PositivePayScreen`) — OtpVerification.request sheet: tap Continue
- Request Cheque Book (`RequestChequeBookScreen`) — OtpVerification.request sheet: tap Continue
- Stop Cheque (`ChequeStopScreen`) — OtpVerification.request sheet: tap Continue
- Zakat (`ZakatScreen`) — OtpVerification.request sheet: tap Continue
- Insurance Premium (`InsuranceScreen`) — OtpVerification.request sheet: tap Continue
- Profile Change Request (`ProfileChangeRequestScreen`) — OtpVerification.request sheet: tap Submit Request
- Universal Pension (`PensionScreen`) — OtpVerification.request sheet: tap Continue
- Card Bill Payment (`CardPaymentDetailsScreen`) — OtpVerification.request sheet: tap Continue
- Transfer Limit (`TransferLimitScreen`) — OtpVerification.request sheet: tap Update Limit
- Update Mobile Number (`UpdateMobileScreen`) — OtpVerification.request sheet: tap Continue
- Update Email Address (`UpdateEmailScreen`) — OtpVerification.request sheet: tap Continue
- Donation (`DonationScreen`) — OtpVerification.request sheet: tap Continue
- Wallet Transfer (bKash/Nagad/etc.) (`WalletTransferScreen`) — OtpVerification.request sheet: tap Continue

  *Core OtpVerificationController.sendOtp, shown as OtpVerificationSheet (core/presentation/widgets/otp/) over every screen listed; any new transaction confirm step calls OtpVerification.request(phone).*

**Refresh token** — `auth/v1/auth/refresh-token`
- All authenticated calls (interceptor) (`ApiClient`) — automatic when access token expired (_getValidToken) or 401 (_handleUnauthorized); also silent refresh during startup

  *Not tied to any screen.*


### App Configuration

**Active app icon** — `support/v1/app-icon/active`
- After login (background) (`syncActiveAppIcon (AuthCacheImpl)`) — after any successful login (_persistSessionIfPresent)

  *Background; no screen.*

**Pay transfer** — `support/v1/pay-transfer`
- Pay & Transfer (bottom tab) (`PayTransferScreen`) — on load / refresh (tab 2 in AppShell)
- Add Beneficiary (`BeneficiaryFormScreen`) — on load (Select Service catalog)

**Services** — `support/v1/services`
- Services (bottom tab) (`ServicesScreen`) — on load / pull to refresh (tab 5 in AppShell)

**Quick actions** — `support/v1/quick-actions`
- Home (`HomeScreen`) — on load (GET quick actions)
- Manage Quick Actions (`QuickActionSettingsScreen`) — on load (GET) and Save order (PUT); opened from Profile > Manage Quick Actions

  *Same getter for GET and PUT.*


## Part 3 — Dead code (registered but never called by any controller)

**Cancel virtual card request** — `card/v1/cards/virtual/requests/{requestId}`
- *(no reachable screen calls this)*

  *Dead code: use cases are only registered in CardBinding; no controller/screen calls submitVirtualCardRequest/listMy/cancel/reveal. RequestVirtualCardScreen uses debit/prepaid application endpoints instead.*

**Do transaction** — `transfer/v1/transactions/do-transaction`
- *(no reachable screen calls this)*

  *Dead code: TransferPolygonAccountUseCase is only registered in bank_transfer_binding.dart; no controller calls it (Polygon Bank Account screen uses TransferCityBankUseCase)*

**Expense tracker categories** — `report/v1/expense-tracker/categories`
- *(no reachable screen calls this)*

  *DEAD: reached only via CategoryRepository.getCategories / GetCategoriesUseCase, which is registered in app_binding.dart but never called. Live category selector (TransactionCategorySelector) uses GetAllCategoriesUseCase -> expenseTrackerAllCategoriesUrl (a different getter).*

**Other banks** — `transfer/v1/other-banks`
- *(no reachable screen calls this)*

  *Dead code: GetOtherBanksUseCase only registered in bank_transfer_binding.dart; never invoked*

**Reveal virtual card** — `card/v1/cards/virtual/requests/{requestId}/reveal`
- *(no reachable screen calls this)*

  *Dead code: use cases are only registered in CardBinding; no controller/screen calls submitVirtualCardRequest/listMy/cancel/reveal. RequestVirtualCardScreen uses debit/prepaid application endpoints instead.*

**Subscribe topic** — `notification/v1/topics/{topic}/subscribe`
- *(no reachable screen calls this)*

  *DEAD: SubscribeTopicUseCase only registered in app_binding.dart; never invoked from any controller/service.*

**Unsubscribe topic** — `notification/v1/topics/{topic}/unsubscribe`
- *(no reachable screen calls this)*

  *DEAD: UnsubscribeTopicUseCase only registered in app_binding.dart; never invoked.*

**Virtual card requests** — `card/v1/cards/virtual/requests`
- *(no reachable screen calls this)*

  *Dead code: use cases are only registered in CardBinding; no controller/screen calls submitVirtualCardRequest/listMy/cancel/reveal. RequestVirtualCardScreen uses debit/prepaid application endpoints instead.*

## Part 4 — Unreachable (wired to a screen, but that screen can't be reached)

`getDashboardData` also exists but throws `UnimplementedError` and is never called.

**Qr login settings** — `auth/v1/user/qr-settings`
- QR Payment Without Login (`QrPaymentWithoutLoginScreen`) — on load / Save (unreachable)

  *DEAD/UNREACHABLE: QrLoginSettingsController screens (QrPaymentWithoutLoginScreen, QrCardConfigurationScreen) are registered routes, but the only entry (QrScanPaymentsScreen from Profile) renders both options disabled (enabled:false, onTap shows 'temporarily unavailable'); nothing calls Get.toNamed to qrPaymentWithoutLogin/qrCardConfiguration.*

**Update qr login settings** — `auth/v1/user/qr-settings`
- QR Payment Without Login (`QrPaymentWithoutLoginScreen`) — on load / Save (unreachable)

  *DEAD/UNREACHABLE: QrLoginSettingsController screens (QrPaymentWithoutLoginScreen, QrCardConfigurationScreen) are registered routes, but the only entry (QrScanPaymentsScreen from Profile) renders both options disabled (enabled:false, onTap shows 'temporarily unavailable'); nothing calls Get.toNamed to qrPaymentWithoutLogin/qrCardConfiguration.*

**Qr payment cards** — `auth/v1/user/qr-settings/cards`
- QR Card Configuration (`QrCardConfigurationScreen`) — on load / toggle card (unreachable)

  *DEAD/UNREACHABLE: QrLoginSettingsController screens (QrPaymentWithoutLoginScreen, QrCardConfigurationScreen) are registered routes, but the only entry (QrScanPaymentsScreen from Profile) renders both options disabled (enabled:false, onTap shows 'temporarily unavailable'); nothing calls Get.toNamed to qrPaymentWithoutLogin/qrCardConfiguration.*

**Set qr payment card enabled** — `auth/v1/user/qr-settings/cards/{cardId}`
- QR Card Configuration (`QrCardConfigurationScreen`) — on load / toggle card (unreachable)

  *DEAD/UNREACHABLE: QrLoginSettingsController screens (QrPaymentWithoutLoginScreen, QrCardConfigurationScreen) are registered routes, but the only entry (QrScanPaymentsScreen from Profile) renders both options disabled (enabled:false, onTap shows 'temporarily unavailable'); nothing calls Get.toNamed to qrPaymentWithoutLogin/qrCardConfiguration.*

**Delete account** — `auth/v1/user`
- Profile (`ProfileScreen`) — Security > Delete Polygon Account confirm

  *Effectively unreachable: menu entry is constructed with enabled: false (profile_screen.dart ~line 241), so the tap handler is disabled.*
