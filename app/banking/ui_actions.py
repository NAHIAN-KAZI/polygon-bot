"""Requests the chat does NOT carry out itself (T-79): one registry entry each.

For every such request the bank's own app already has the place to do it. The chat tells the
customer what it is and what they need, then hands the app one of three things:
  screen -- open this app screen, with any fields the customer already gave prefilled
  form   -- show a form in the chat UI (not used yet: dispute/complaint forms are screens today)
  info   -- show the information only (nothing to open: no app screen exists, or it is sensitive)
  unavailable -- the bank has no backend for it

This file is DATA, not behaviour: the classifier picks an entry by its `description` (the same
way it picks any service), the model extracts the optional `prefill` fields from what the customer
wrote, and the composer words the reply from `needs` -- no sentence here is shown to a customer.
Screen names and route paths come from the app itself (planning/input/API_SCREEN_MAP.md and
user_app/lib/res/routes/app_routes.dart); `rows` are the INTENT_IMPLEMENTATION_STATUS.md rows.
"""
from dataclasses import dataclass

CATEGORY = "app_actions"
CATEGORY_NAME = "App Actions"


@dataclass(frozen=True)
class UiAction:
    id: str
    name: str                 # plain name, for the catalog and for facts
    domain: str               # a DOMAINS key in routing.py (stage-1 grouping)
    kind: str                 # screen | form | info | unavailable
    description: str          # what the customer is asking for (routing prompt)
    needs: str                # what they need to have or do on the screen (facts for the reply)
    rows: tuple[str, ...]     # status-doc rows this covers
    screen: str | None = None  # app screen class
    route: str | None = None   # app route path (None for a bottom sheet / nested screen)
    prefill: tuple[tuple[str, str], ...] = ()  # (field, meaning): optional, only what the customer wrote


def _a(id, name, domain, kind, description, needs, rows, screen=None, route=None, prefill=()):
    return UiAction(id, name, domain, kind, description, needs, tuple(rows), screen, route, tuple(prefill))


_LIST = [
    # ---- cards -------------------------------------------------------------------------------
    _a("card_pin_reset", "Reset card PIN", "cards", "screen",
       "reset or change the PIN of a card they hold",
       "choose the card, then confirm with a one-time code and their PIN or password",
       ["3.1", "4.6"], "SelectCardForPinResetScreen", "/set_reset_card_pin",
       [("cardLast4", "last 4 digits of the card")]),
    _a("card_unfreeze", "Unfreeze card", "cards", "screen",
       "unfreeze, unblock or reactivate a card that is currently frozen or blocked (making it usable again)",
       "choose the frozen card and confirm with a one-time code and their PIN or password",
       ["3.2", "4.2"], "FreezeCardScreen", "/freeze_card",
       [("cardLast4", "last 4 digits of the card")]),
    _a("card_close", "Close card", "cards", "screen",
       "permanently close or cancel one of their cards",
       "choose the card and confirm the permanent closure with a one-time code and their PIN or password",
       ["4.3"], "CardReplacementScreen", "/request_card_replacement",
       [("cardLast4", "last 4 digits of the card")]),
    _a("card_contactless", "Contactless on/off", "cards", "screen",
       "turn contactless (tap) payments on or off for a card, or set a contactless limit",
       "open the card, then its settings, and switch contactless on or off",
       ["4.4"], "CardDetailScreen", "/card_detail",
       [("cardLast4", "last 4 digits of the card")]),
    _a("card_international", "International use on/off", "cards", "screen",
       "turn international or overseas card transactions on or off for a card",
       "choose the card, switch international use on or off and confirm with a one-time code and their PIN or password",
       ["4.5"], "SelectCardForInternationalScreen", "/international_transaction/select_card",
       [("cardLast4", "last 4 digits of the card")]),
    _a("card_limit_change", "Change card limit", "cards", "screen",
       "ask to change or raise the limit of a credit card (submit a new limit request); not viewing existing requests",
       "choose the credit card and enter the new limit they want; the bank reviews it",
       ["4.7"], "CardLimitChangeScreen", "/card_limit_change_request",
       [("cardLast4", "last 4 digits of the card"), ("requestedLimit", "the new limit in taka")]),
    _a("card_limit_cancel", "Cancel limit change", "cards", "screen",
       "cancel a card limit change request they already submitted",
       "open the pending limit-change request and confirm the cancellation",
       ["4.9"], "CardLimitChangeScreen", "/card_limit_change_request"),
    _a("card_apply", "Apply for a card", "cards", "screen",
       "apply for or request a new card (debit, prepaid or virtual card); not viewing existing requests",
       "choose a card product and the account to link, enter the name for the card and confirm with a one-time code and PIN",
       ["4.11", "4.13", "4.15"], "CardProductCatalogScreen", "/card_product_catalog",
       [("cardType", "debit, prepaid or virtual")]),
    _a("card_virtual_cancel", "Cancel virtual card", "cards", "info",
       "cancel a virtual card or a virtual card request",
       "the app has no screen for cancelling a virtual card at the moment",
       ["4.17"]),
    _a("card_details_reveal", "Show full card details", "cards", "info",
       "reveal or show the full number, expiry or CVV of a card (debit, prepaid, virtual or replacement)",
       "full card details are sensitive and are never shown in the chat; they are only available inside the app",
       ["4.12", "4.14", "4.18", "5.3"], "CardDetailScreen", "/card_detail"),
    _a("credit_card_pay", "Pay credit card bill", "cards", "screen",
       "pay the bill or dues of their own Polygon Bank credit card (total, statement or minimum due)",
       "open the credit card, choose what to pay (total outstanding, statement due or minimum due) and the account to pay from",
       ["4.20"], "CardDetailScreen", "/card_detail",
       [("paymentType", "total outstanding, statement due or minimum due")]),
    _a("other_card_pay", "Pay another bank's card bill", "cards", "screen",
       "pay a credit card bill of another bank's card (enter the card number and amount)",
       "enter the card number, the amount and the account to pay from, then a one-time code and transaction PIN",
       ["4.21"], "CardPaymentDetailsScreen", "/card_payment/details/:type",
       [("amount", "amount in taka"), ("cardNumberLast4", "last 4 digits of the card to pay")]),
    _a("replacement_cancel", "Cancel card replacement", "cards", "screen",
       "cancel a card replacement request they already made",
       "open the pending replacement request and confirm the cancellation",
       ["5.2"], "CardReplacementScreen", "/request_card_replacement"),
    # ---- accounts / quick view ----------------------------------------------------------------
    _a("quick_view_star", "Star account or card", "accounts", "screen",
       "star, favourite or pin an account or a card so it shows on the home quick view",
       "choose which account or card to show on the home screen and switch its star on or off",
       ["1.5", "4.19"], "CustomizeQuickViewScreen", "/customize_quick_view"),
    # ---- profile ------------------------------------------------------------------------------
    _a("kyc_submit", "Submit KYC documents", "profile", "screen",
       "submit or update KYC / identity documents (NID photos, signature) or occupation and income details",
       "photograph the NID front and back and the signature, and optionally add occupation and income details; photos are taken in the app",
       ["7.9"], "UpdateKycScreen", "/profile/update_kyc",
       [("occupation", "their occupation")]),
    _a("profile_change_request", "Request a profile detail change", "profile", "screen",
       "request a change to a verified detail (legal name, date of birth, NID, or a verified mobile or email) that the bank reviews",
       "pick the detail to change, enter the new value and a reason, and verify with a one-time code; the bank reviews it",
       ["7.11"], "ProfileChangeRequestScreen", "/profile_change_request",
       [("fieldName", "which detail: mobile, email, NID, legal name or date of birth"),
        ("requestedValue", "the new value"), ("reason", "why they want it changed")]),
    _a("contact_priority_change", "Change primary contact", "profile", "screen",
       "choose which of their registered phone numbers or emails is the primary contact",
       "choose which registered contact becomes primary, give a reason and verify with a one-time code",
       ["7.13"], "ContactPriorityScreen", "/contact_priority",
       [("reason", "why they want it changed")]),
    # ---- transfers and money ------------------------------------------------------------------
    _a("cash_by_code", "Cash by code", "transfers", "screen",
       "send cash by code (a code the recipient uses to withdraw) or withdraw cash using a code",
       "choose the account, the recipient's mobile number, the amount and how the code is delivered, then confirm with a one-time code and transaction PIN",
       ["2.1"], "CashByCodeScreen", "/cash_by_code",
       [("amount", "amount in taka"), ("recipientMobile", "the recipient's mobile number")]),
    _a("gift_transfer", "Send a gift", "transfers", "screen",
       "send a gift with a wish message to someone",
       "choose the recipient, a gift design, a wish message and the amount, then confirm with a one-time code and PIN",
       ["14.5"], "GiftScreen", "/gift",
       [("amount", "amount in taka"), ("recipient", "who the gift is for")]),
    _a("email_transfer_create", "Send money by email", "transfers", "screen",
       "send money to someone using only their email address (email transfer)",
       "enter the recipient's email, the amount and a security question and answer, then confirm with a one-time code and PIN",
       ["14.9"], "EmailTransferEntryScreen", "/email_transfer/entry",
       [("recipientEmail", "the recipient's email address"), ("amount", "amount in taka")]),
    _a("email_transfer_manage", "Cancel or resend an email transfer", "transfers", "screen",
       "cancel a pending email transfer or resend the notification of an email transfer",
       "open the email transfer and choose cancel or resend",
       ["14.12", "14.13"], "EmailTransferListScreen", "/email_transfer/list",
       [("action", "cancel or resend")]),
    _a("qr_payment", "Pay by QR code", "transfers", "screen",
       "pay a merchant by scanning a QR code",
       "scan the merchant's QR code with the phone camera, then confirm the amount and the account to pay from with a one-time code and PIN",
       ["14.16", "14.17"], "QrScanScreen", None),
    _a("beneficiary_edit", "Edit a beneficiary", "transfers", "screen",
       "rename or edit a saved beneficiary",
       "open the beneficiary and change its nickname (only the nickname can be edited)",
       ["14.21"], "BeneficiaryFormScreen", "/beneficiary/form",
       [("nickname", "the new nickname")]),
    _a("beneficiary_delete", "Delete a beneficiary", "transfers", "screen",
       "delete or remove a saved beneficiary",
       "open the saved beneficiaries, pick the one to remove and confirm",
       ["14.22"], "BeneficiaryScreen", "/beneficiary"),
    _a("beneficiary_pin", "Pin a beneficiary", "transfers", "screen",
       "pin or unpin a saved beneficiary so it stays at the top of the list",
       "tap the pin on the beneficiary to keep it at the top (this is list pinning, not a security PIN)",
       ["14.25"], "BeneficiaryScreen", "/beneficiary"),
    _a("beneficiary_photo", "Beneficiary photo", "transfers", "screen",
       "add, change or remove the photo of a saved beneficiary",
       "pick a photo from the phone's gallery or camera; photos are chosen in the app",
       ["14.23", "14.24"], "BeneficiaryFormScreen", "/beneficiary/form"),
    _a("transfer_limit_change", "Change transfer limit", "transfers", "screen",
       "ask to change their transfer limit, or cancel a pending transfer-limit change request",
       "choose the account and the new limit, or open the pending request, and confirm with a one-time code and PIN",
       ["14.28", "14.29"], "TransferLimitScreen", "/transfer_limit",
       [("newLimit", "the new limit in taka")]),
    # ---- no backend ---------------------------------------------------------------------------
    _a("qr_payment_cards", "QR payment cards", "cards", "unavailable",
       "see, list or switch on/off the cards used for QR payments (the QR payment card settings; the bank's card products are a different thing)",
       "QR payment card settings are not available at the moment",
       ["4.22", "4.23"]),
    _a("other_banks_list", "List of other banks", "transfers", "unavailable",
       "see the list of other banks they can transfer to",
       "this list is not available at the moment",
       ["14.4"]),
]

UI_ACTIONS: dict[str, UiAction] = {a.id: a for a in _LIST}


def get(service_id: str) -> UiAction | None:
    return UI_ACTIONS.get(service_id)


def catalog_category() -> dict:
    """The synthetic taxonomy category, so the classifier can choose these like any service."""
    return {
        "id": CATEGORY, "name": CATEGORY_NAME, "isActive": True,
        "services": [{"id": a.id, "name": a.name, "isActive": True} for a in _LIST],
    }


def keys() -> frozenset[tuple[str, str]]:
    return frozenset((CATEGORY, a.id) for a in _LIST)


def keys_for_domain(domain: str) -> frozenset[tuple[str, str]]:
    return frozenset((CATEGORY, a.id) for a in _LIST if a.domain == domain)
