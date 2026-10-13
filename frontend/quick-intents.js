// Demo-only quick tests: one chip per intent. Clicking sends that intent's opening message
// to the model, then shows the intent's use cases as more chips (each sends its own message).
// Messages come from handoffs/TEST_MESSAGES.md. Not part of the Dart UI handoff.
const QUICK_INTENTS = [
  {
    "intent": "ACCOUNT_INFO",
    "message": "Can you please list all of my bank accounts?",
    "options": [
      {
        "label": "1.1 Get all accounts",
        "message": "Can you please list all of my bank accounts?"
      },
      {
        "label": "1.2 Get account detail",
        "message": "Please show me the details of my savings account."
      },
      {
        "label": "1.3 Account by account/card number",
        "message": "Can you look up an account using its account number?"
      },
      {
        "label": "1.4 Accounts by username",
        "message": "Can you list the accounts linked to my username?"
      },
      {
        "label": "1.5 Star account",
        "message": "Please star my savings account so it shows on my home quick view."
      },
      {
        "label": "1.6 My loans",
        "message": "I'd like to view an overview of all my current loans, please."
      },
      {
        "label": "1.7 FD profit history",
        "message": "Can you please show me the profit history of my FD?"
      },
      {
        "label": "1.8 DPS profit history",
        "message": "I need to know how much profit I earned on my DPS savings scheme."
      },
      {
        "label": "Cards list",
        "message": "Can you show me all the cards linked to my account?"
      },
      {
        "label": "One account's transactions",
        "message": "show me the transactions on my savings account"
      },
      {
        "label": "Enrolled devices",
        "message": "Can you show me which devices are registered to my account?"
      },
      {
        "label": "Login history",
        "message": "Where was my account logged in from recently?"
      }
    ]
  },
  {
    "intent": "CHECK_BALANCE",
    "message": "How much money do I have in my account right now?",
    "options": [
      {
        "label": "6.1 Account balance",
        "message": "How much money do I have in my account right now?"
      },
      {
        "label": "6.2 Credit card summary",
        "message": "Can you show me my credit card summary?"
      }
    ]
  },
  {
    "intent": "FAILED_TRANSFER",
    "message": "Can you show me my recent transactions?",
    "options": [
      {
        "label": "8.1 Transaction history",
        "message": "Can you show me my recent transactions?"
      },
      {
        "label": "8.2 Raise dispute",
        "message": "I want to raise a dispute for a payment that failed."
      },
      {
        "label": "8.3 List disputes",
        "message": "Can you show me the list of disputes I have raised?"
      },
      {
        "label": "8.4 Submit complaint",
        "message": "I would like to file a complaint about the mobile app."
      },
      {
        "label": "8.5 My complaints",
        "message": "I want to check the status of my complaint."
      }
    ]
  },
  {
    "intent": "EDIT_PERSONAL_DETAILS",
    "message": "Can you please show me my profile details?",
    "options": [
      {
        "label": "7.1 Get profile",
        "message": "Can you please show me my profile details?"
      },
      {
        "label": "7.2 Update nickname",
        "message": "Please change my nickname to Tas."
      },
      {
        "label": "7.3/7.4 Upload / change profile image",
        "message": "I want to upload a new profile picture."
      },
      {
        "label": "7.5 Update mobile number",
        "message": "I want to change my registered mobile number."
      },
      {
        "label": "7.6 Update email address",
        "message": "I would like to update my email address."
      },
      {
        "label": "7.7 Get address",
        "message": "What address does the bank have registered for me?"
      },
      {
        "label": "7.8 Update address",
        "message": "Please update my present address to House 5, Road 2, Banani."
      },
      {
        "label": "7.9 Submit KYC",
        "message": "I need to submit my KYC documents."
      },
      {
        "label": "7.10 My contacts",
        "message": "Which phone numbers and emails are registered on my account?"
      },
      {
        "label": "7.11 Profile change — submit",
        "message": "I want to request a change to my date of birth."
      },
      {
        "label": "7.12 Profile change — list",
        "message": "Has my profile change request been processed yet?"
      },
      {
        "label": "7.13 Contact priority — submit",
        "message": "I want to change my primary contact number."
      },
      {
        "label": "7.14 Contact priority — list",
        "message": "Can you show me the status of my primary-contact change requests?"
      }
    ]
  },
  {
    "intent": "TRANSFER",
    "message": "I want to send money.",
    "options": [
      {
        "label": "14.1 Own account transfer",
        "message": "I want to move 1,250 taka to my other account."
      },
      {
        "label": "14.2 City (Polygon) Bank transfer",
        "message": "Send 500 taka to Polygon Bank account number 7305518294063."
      },
      {
        "label": "14.3 Other bank transfer",
        "message": "Send 1,250 taka to my friend's Dutch-Bangla Bank account 7305518294063."
      },
      {
        "label": "14.4 Other banks list",
        "message": "Can you show me the list of other banks I can transfer to?"
      },
      {
        "label": "14.5 Gift transfer",
        "message": "I want to send a gift of 1,250 taka to my friend."
      },
      {
        "label": "14.6 Gifts received",
        "message": "Can you show me the gifts I have received?"
      },
      {
        "label": "14.9 Email transfer — create",
        "message": "I want to send money by email."
      },
      {
        "label": "14.10 Email transfer — list",
        "message": "Can you show me a list of the email transfers I have made?"
      },
      {
        "label": "14.11 Email transfer — details",
        "message": "What is the status of my email transfer from yesterday?"
      },
      {
        "label": "14.12 Email transfer — cancel",
        "message": "I would like to cancel the email transfer I made yesterday."
      },
      {
        "label": "14.13 Email transfer — resend",
        "message": "Can you resend the notification for my email transfer?"
      },
      {
        "label": "14.14 Wallet / MFS transfer",
        "message": "Send 500 taka to my bKash number 01836290417."
      },
      {
        "label": "14.16 QR pay",
        "message": "I would like to pay a merchant by scanning a QR code."
      },
      {
        "label": "14.17 QR parse",
        "message": "Can you help me read this QR code to see who I'm paying?"
      },
      {
        "label": "14.18 QR payment history",
        "message": "Can you show me my QR payment history?"
      },
      {
        "label": "14.19 Beneficiary — list / send to a saved name",
        "message": "Can you show me my saved beneficiaries?"
      },
      {
        "label": "14.20 Beneficiary — add",
        "message": "I'd like to add a new beneficiary."
      },
      {
        "label": "14.21 Beneficiary — edit",
        "message": "I want to rename a saved beneficiary."
      },
      {
        "label": "14.22 Beneficiary — delete",
        "message": "I need to remove a saved beneficiary."
      },
      {
        "label": "14.23 Beneficiary — upload / change photo",
        "message": "I want to upload a photo for one of my saved beneficiaries."
      },
      {
        "label": "14.24 Beneficiary — remove photo",
        "message": "I want to remove the photo from a saved beneficiary."
      },
      {
        "label": "14.25 Beneficiary — pin / unpin",
        "message": "I want to pin a saved beneficiary to the top of my list."
      },
      {
        "label": "14.27 My transfer limit — get",
        "message": "Can you tell me my current transfer limit?"
      },
      {
        "label": "14.28 My transfer limit — request change",
        "message": "I want to change my transfer limit because it's too low."
      },
      {
        "label": "14.29 My transfer limit — cancel pending change",
        "message": "I want to cancel the pending change to my daily transfer limit."
      }
    ]
  },
  {
    "intent": "MINI_STATEMENT",
    "message": "Please show me my recent transactions.",
    "options": [
      {
        "label": "13.1 Transaction list",
        "message": "Please show me my recent transactions."
      },
      {
        "label": "13.2 Account transactions",
        "message": "I want to check all the transactions in my savings account."
      },
      {
        "label": "13.3 Credit card statement",
        "message": "Can you please provide my credit card statement for last month?"
      }
    ]
  }
];

(function () {
  const form = document.getElementById("chatForm");
  const input = document.getElementById("chatInput");
  if (!form || !input) return;

  const bar = document.createElement("div");
  bar.id = "quickBar";
  bar.className = "quick-bar";
  form.parentNode.insertBefore(bar, form);

  function send(text) {
    input.value = text;
    form.requestSubmit();
  }

  function chip(label, onClick, extraClass) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "quick-chip" + (extraClass ? " " + extraClass : "");
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  }

  function showIntents() {
    bar.replaceChildren();
    const row = document.createElement("div");
    row.className = "quick-row";
    for (const item of QUICK_INTENTS) {
      row.append(chip(item.intent, () => { send(item.message); showOptions(item); }, "quick-intent"));
    }
    bar.append(quickLabel("Quick tests"), row);
  }

  function showOptions(item) {
    bar.replaceChildren();
    const head = document.createElement("div");
    head.className = "quick-head";
    head.append(chip("← All intents", showIntents, "quick-back"), quickLabel(item.intent));
    const row = document.createElement("div");
    row.className = "quick-row quick-options";
    for (const opt of item.options) {
      const c = chip(opt.label, () => send(opt.message));
      c.title = opt.message;
      row.append(c);
    }
    bar.append(head, row);
  }

  function quickLabel(text) {
    const s = document.createElement("span");
    s.className = "quick-label";
    s.textContent = text;
    return s;
  }

  showIntents();
})();
