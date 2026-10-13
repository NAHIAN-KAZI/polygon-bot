// Demo-only quick tests: one chip per intent. Clicking an intent only lists its use cases;
// clicking a use case offers three versions of its message (English, Bangla, Banglish);
// nothing is sent to the model until one of those is clicked.
// English messages come from handoffs/TEST_MESSAGES.md. Not part of the Dart UI handoff.
const QUICK_INTENTS = [
  {
    "intent": "ACCOUNT_INFO",
    "options": [
      {
        "label": "1.1 Get all accounts",
        "message": "Can you please list all of my bank accounts?",
        "bn": "আমার সব ব্যাংক অ্যাকাউন্টের লিস্ট দেখাতে পারবেন?",
        "bl": "amar sob bank account er list dekhaite parben?"
      },
      {
        "label": "1.2 Get account detail",
        "message": "Please show me the details of my savings account.",
        "bn": "আমার সেভিংস অ্যাকাউন্টের ডিটেইলস দেখান প্লিজ।",
        "bl": "amar savings account er details dekhan please."
      },
      {
        "label": "1.3 Account by account/card number",
        "message": "Can you look up an account using its account number?",
        "bn": "অ্যাকাউন্ট নাম্বার দিয়ে কি একটা অ্যাকাউন্ট খুঁজে দেখা যাবে?",
        "bl": "account number diye ki ekta account khuje dekha jabe?"
      },
      {
        "label": "1.4 Accounts by username",
        "message": "Can you list the accounts linked to my username?",
        "bn": "আমার ইউজারনেমের সাথে যেসব অ্যাকাউন্ট লিংক করা আছে সেগুলোর লিস্ট দেখাতে পারবেন?",
        "bl": "amar username er sathe linked account gulor list dekhaite parben?"
      },
      {
        "label": "1.5 Star account",
        "message": "Please star my savings account so it shows on my home quick view.",
        "bn": "আমার সেভিংস অ্যাকাউন্টটা স্টার করে দিন, যাতে হোমের কুইক ভিউতে দেখায়।",
        "bl": "amar savings account ta star kore din, jate home quick view te dekhay."
      },
      {
        "label": "1.6 My loans",
        "message": "I'd like to view an overview of all my current loans, please.",
        "bn": "আমার সব চলমান লোনের একটা ওভারভিউ দেখতে চাই।",
        "bl": "amar sob cholman loan er ekta overview dekhte chai."
      },
      {
        "label": "1.7 FD profit history",
        "message": "Can you please show me the profit history of my FD?",
        "bn": "আমার FD-র প্রফিট হিস্টরি দেখাতে পারবেন?",
        "bl": "amar FD er profit history dekhaite parben?"
      },
      {
        "label": "1.8 DPS profit history",
        "message": "I need to know how much profit I earned on my DPS savings scheme.",
        "bn": "আমার DPS সঞ্চয় স্কিমে কত প্রফিট হয়েছে সেটা জানতে চাই।",
        "bl": "amar DPS e koto profit hoyeche ta jante chai."
      },
      {
        "label": "Cards list",
        "message": "Can you show me all the cards linked to my account?",
        "bn": "আমার অ্যাকাউন্টের সাথে লিংক করা সব কার্ড দেখাতে পারবেন?",
        "bl": "amar account er sathe linked sob card dekhaite parben?"
      },
      {
        "label": "One account's transactions",
        "message": "show me the transactions on my savings account",
        "bn": "আমার সেভিংস অ্যাকাউন্টের ট্রানজেকশনগুলো দেখান",
        "bl": "amar savings account er transaction gulo dekhan"
      },
      {
        "label": "Enrolled devices",
        "message": "Can you show me which devices are registered to my account?",
        "bn": "আমার অ্যাকাউন্টে কোন কোন ডিভাইস রেজিস্টার্ড আছে দেখাতে পারবেন?",
        "bl": "amar account e kon kon device registered ache dekhaite parben?"
      },
      {
        "label": "Login history",
        "message": "Where was my account logged in from recently?",
        "bn": "সম্প্রতি আমার অ্যাকাউন্টে কোথা থেকে লগইন করা হয়েছে?",
        "bl": "shomprotik amar account e kotha theke login hoyeche?"
      }
    ]
  },
  {
    "intent": "CHECK_BALANCE",
    "options": [
      {
        "label": "6.1 Account balance",
        "message": "How much money do I have in my account right now?",
        "bn": "এই মুহূর্তে আমার অ্যাকাউন্টে কত টাকা আছে?",
        "bl": "ekhon amar account e koto taka ache?"
      },
      {
        "label": "6.2 Credit card summary",
        "message": "Can you show me my credit card summary?",
        "bn": "আমার ক্রেডিট কার্ডের সামারি দেখাতে পারবেন?",
        "bl": "amar credit card er summary dekhaite parben?"
      }
    ]
  },
  {
    "intent": "FAILED_TRANSFER",
    "options": [
      {
        "label": "8.1 Transaction history",
        "message": "Can you show me my recent transactions?",
        "bn": "আমার সাম্প্রতিক ট্রানজেকশনগুলো দেখাতে পারবেন?",
        "bl": "amar recent transaction gulo dekhaite parben?"
      },
      {
        "label": "8.2 Raise dispute",
        "message": "I want to raise a dispute for a payment that failed.",
        "bn": "একটা ফেইল হওয়া পেমেন্টের জন্য আমি ডিসপিউট করতে চাই।",
        "bl": "ekta failed payment er jonno ami dispute raise korte chai."
      },
      {
        "label": "8.3 List disputes",
        "message": "Can you show me the list of disputes I have raised?",
        "bn": "আমি যেসব ডিসপিউট করেছি সেগুলোর লিস্ট দেখাতে পারবেন?",
        "bl": "ami je dispute gulo korechi tar list dekhaite parben?"
      },
      {
        "label": "8.4 Submit complaint",
        "message": "I would like to file a complaint about the mobile app.",
        "bn": "মোবাইল অ্যাপ নিয়ে আমি একটা অভিযোগ জানাতে চাই।",
        "bl": "mobile app niye ami ekta complaint korte chai."
      },
      {
        "label": "8.5 My complaints",
        "message": "I want to check the status of my complaint.",
        "bn": "আমার অভিযোগের স্ট্যাটাস জানতে চাই।",
        "bl": "amar complaint er status jante chai."
      }
    ]
  },
  {
    "intent": "EDIT_PERSONAL_DETAILS",
    "options": [
      {
        "label": "7.1 Get profile",
        "message": "Can you please show me my profile details?",
        "bn": "আমার প্রোফাইলের ডিটেইলস দেখাতে পারবেন?",
        "bl": "amar profile er details dekhaite parben?"
      },
      {
        "label": "7.2 Update nickname",
        "message": "Please change my nickname to Tas.",
        "bn": "আমার nickname টা Tas করে দিন প্লিজ।",
        "bl": "amar nickname ta Tas kore din please"
      },
      {
        "label": "7.3/7.4 Upload / change profile image",
        "message": "I want to upload a new profile picture.",
        "bn": "আমি নতুন একটা প্রোফাইল ছবি আপলোড করতে চাই।",
        "bl": "ami notun ekta profile picture upload korte chai"
      },
      {
        "label": "7.5 Update mobile number",
        "message": "I want to change my registered mobile number.",
        "bn": "আমি আমার রেজিস্টার্ড মোবাইল নম্বরটা পরিবর্তন করতে চাই।",
        "bl": "ami amar registered mobile number ta change korte chai"
      },
      {
        "label": "7.6 Update email address",
        "message": "I would like to update my email address.",
        "bn": "আমি আমার ইমেইল অ্যাড্রেসটা আপডেট করতে চাই।",
        "bl": "ami amar email address ta update korte chai"
      },
      {
        "label": "7.7 Get address",
        "message": "What address does the bank have registered for me?",
        "bn": "ব্যাংকে আমার নামে কোন ঠিকানা রেজিস্টার্ড আছে?",
        "bl": "bank e amar nam e kon address registered ache?"
      },
      {
        "label": "7.8 Update address",
        "message": "Please update my present address to House 5, Road 2, Banani.",
        "bn": "আমার বর্তমান ঠিকানা আপডেট করে House 5, Road 2, Banani দিন প্লিজ।",
        "bl": "amar present address update kore House 5, Road 2, Banani din please"
      },
      {
        "label": "7.9 Submit KYC",
        "message": "I need to submit my KYC documents.",
        "bn": "আমার KYC এর কাগজপত্র জমা দিতে হবে।",
        "bl": "amar KYC er documents submit korte hobe"
      },
      {
        "label": "7.10 My contacts",
        "message": "Which phone numbers and emails are registered on my account?",
        "bn": "আমার অ্যাকাউন্টে কোন কোন ফোন নম্বর আর ইমেইল রেজিস্টার্ড আছে?",
        "bl": "amar account e kon kon phone number ar email registered ache?"
      },
      {
        "label": "7.11 Profile change — submit",
        "message": "I want to request a change to my date of birth.",
        "bn": "আমি আমার জন্ম তারিখ পরিবর্তনের জন্য অনুরোধ করতে চাই।",
        "bl": "ami amar jonmo tarikh change er jonno request korte chai"
      },
      {
        "label": "7.12 Profile change — list",
        "message": "Has my profile change request been processed yet?",
        "bn": "আমার প্রোফাইল পরিবর্তনের অনুরোধটা কি প্রসেস হয়েছে?",
        "bl": "amar profile change request ta ki process hoyeche?"
      },
      {
        "label": "7.13 Contact priority — submit",
        "message": "I want to change my primary contact number.",
        "bn": "আমি আমার প্রাইমারি কন্টাক্ট নম্বর পরিবর্তন করতে চাই।",
        "bl": "ami amar primary contact number change korte chai"
      },
      {
        "label": "7.14 Contact priority — list",
        "message": "Can you show me the status of my primary-contact change requests?",
        "bn": "আমার প্রাইমারি কন্টাক্ট পরিবর্তনের অনুরোধগুলোর স্ট্যাটাস দেখাতে পারবেন?",
        "bl": "amar primary contact change request gulor status dekhate parben?"
      }
    ]
  },
  {
    "intent": "TRANSFER",
    "options": [
      {
        "label": "14.1 Own account transfer",
        "message": "I want to move 1,250 taka to my other account.",
        "bn": "আমি আমার অন্য অ্যাকাউন্টে 1,250 টাকা পাঠাতে চাই।",
        "bl": "ami amar onno account e 1,250 taka pathate chai"
      },
      {
        "label": "14.2 City (Polygon) Bank transfer",
        "message": "Send 500 taka to Polygon Bank account number 7305518294063.",
        "bn": "Polygon Bank এর 7305518294063 নম্বর অ্যাকাউন্টে 500 টাকা পাঠিয়ে দিন।",
        "bl": "Polygon Bank er 7305518294063 number account e 500 taka pathiye din"
      },
      {
        "label": "14.3 Other bank transfer",
        "message": "Send 1,250 taka to my friend's Dutch-Bangla Bank account 7305518294063.",
        "bn": "আমার বন্ধুর Dutch-Bangla Bank অ্যাকাউন্ট 7305518294063 এ 1,250 টাকা পাঠিয়ে দিন।",
        "bl": "amar bondhur Dutch-Bangla Bank account 7305518294063 e 1,250 taka pathiye din"
      },
      {
        "label": "14.4 Other banks list",
        "message": "Can you show me the list of other banks I can transfer to?",
        "bn": "আমি কোন কোন অন্য ব্যাংকে টাকা পাঠাতে পারি তার তালিকাটা দেখাতে পারবেন?",
        "bl": "ami kon kon onno bank e taka pathate pari tar list ta dekhate parben?"
      },
      {
        "label": "14.5 Gift transfer",
        "message": "I want to send a gift of 1,250 taka to my friend.",
        "bn": "আমি আমার বন্ধুকে 1,250 টাকা গিফট পাঠাতে চাই।",
        "bl": "ami amar bondhuke 1,250 taka gift pathate chai"
      },
      {
        "label": "14.6 Gifts received",
        "message": "Can you show me the gifts I have received?",
        "bn": "আমি যেসব গিফট পেয়েছি সেগুলো দেখাতে পারবেন?",
        "bl": "ami jei gift gulo peyechi segulo dekhate parben?"
      },
      {
        "label": "14.9 Email transfer — create",
        "message": "I want to send money by email.",
        "bn": "আমি ইমেইলের মাধ্যমে টাকা পাঠাতে চাই।",
        "bl": "ami email er maddhome taka pathate chai"
      },
      {
        "label": "14.10 Email transfer — list",
        "message": "Can you show me a list of the email transfers I have made?",
        "bn": "আমি ইমেইলের মাধ্যমে যেসব ট্রান্সফার করেছি তার একটা তালিকা দেখাতে পারবেন?",
        "bl": "ami email diye jei transfer gulo koreechi tar ekta list dekhate parben?"
      },
      {
        "label": "14.11 Email transfer — details",
        "message": "What is the status of my email transfer from yesterday?",
        "bn": "গতকালের আমার ইমেইল ট্রান্সফারের স্ট্যাটাস কী?",
        "bl": "gotokal amar email transfer er status ki?"
      },
      {
        "label": "14.12 Email transfer — cancel",
        "message": "I would like to cancel the email transfer I made yesterday.",
        "bn": "গতকাল যে ইমেইল ট্রান্সফারটা করেছিলাম সেটা ক্যানসেল করতে চাই।",
        "bl": "gotokal je email transfer ta korechilam seta cancel korte chai."
      },
      {
        "label": "14.13 Email transfer — resend",
        "message": "Can you resend the notification for my email transfer?",
        "bn": "আমার ইমেইল ট্রান্সফারের নোটিফিকেশনটা কি আবার পাঠাতে পারবেন?",
        "bl": "amar email transfer er notification ta ki abar pathate parben?"
      },
      {
        "label": "14.14 Wallet / MFS transfer",
        "message": "Send 500 taka to my bKash number 01836290417.",
        "bn": "আমার bKash নম্বর 01836290417-এ 500 টাকা পাঠান।",
        "bl": "amar bKash number 01836290417 e 500 taka pathan."
      },
      {
        "label": "14.16 QR pay",
        "message": "I would like to pay a merchant by scanning a QR code.",
        "bn": "আমি QR কোড স্ক্যান করে একটা মার্চেন্টকে পেমেন্ট করতে চাই।",
        "bl": "ami QR code scan kore ekta merchant ke payment korte chai."
      },
      {
        "label": "14.17 QR parse",
        "message": "Can you help me read this QR code to see who I'm paying?",
        "bn": "এই QR কোডটা পড়ে দেখতে একটু সাহায্য করবেন, আমি কাকে পেমেন্ট করছি?",
        "bl": "ei QR code ta pore dekhte ektu help korben, ami kake payment korchi?"
      },
      {
        "label": "14.18 QR payment history",
        "message": "Can you show me my QR payment history?",
        "bn": "আমার QR পেমেন্টের হিস্ট্রি দেখাবেন?",
        "bl": "amar QR payment er history dekhaben?"
      },
      {
        "label": "14.19 Beneficiary — list / send to a saved name",
        "message": "Can you show me my saved beneficiaries?",
        "bn": "আমার সেভ করা বেনিফিশিয়ারিগুলো দেখাবেন?",
        "bl": "amar save kora beneficiary gulo dekhaben?"
      },
      {
        "label": "14.20 Beneficiary — add",
        "message": "I'd like to add a new beneficiary.",
        "bn": "আমি একজন নতুন বেনিফিশিয়ারি অ্যাড করতে চাই।",
        "bl": "ami notun ekjon beneficiary add korte chai."
      },
      {
        "label": "14.21 Beneficiary — edit",
        "message": "I want to rename a saved beneficiary.",
        "bn": "আমি একটা সেভ করা বেনিফিশিয়ারির নাম পরিবর্তন করতে চাই।",
        "bl": "ami ekta save kora beneficiary er naam change korte chai."
      },
      {
        "label": "14.22 Beneficiary — delete",
        "message": "I need to remove a saved beneficiary.",
        "bn": "একটা সেভ করা বেনিফিশিয়ারি আমার ডিলিট করতে হবে।",
        "bl": "ekta save kora beneficiary delete korte hobe."
      },
      {
        "label": "14.23 Beneficiary — upload / change photo",
        "message": "I want to upload a photo for one of my saved beneficiaries.",
        "bn": "আমার সেভ করা একটা বেনিফিশিয়ারির জন্য ছবি আপলোড করতে চাই।",
        "bl": "amar save kora ekta beneficiary er jonno photo upload korte chai."
      },
      {
        "label": "14.24 Beneficiary — remove photo",
        "message": "I want to remove the photo from a saved beneficiary.",
        "bn": "সেভ করা একটা বেনিফিশিয়ারির ছবি সরিয়ে ফেলতে চাই।",
        "bl": "save kora ekta beneficiary er photo remove korte chai."
      },
      {
        "label": "14.25 Beneficiary — pin / unpin",
        "message": "I want to pin a saved beneficiary to the top of my list.",
        "bn": "একটা সেভ করা বেনিফিশিয়ারিকে আমার লিস্টের উপরে পিন করতে চাই।",
        "bl": "ekta save kora beneficiary ke amar list er upore pin korte chai."
      },
      {
        "label": "14.27 My transfer limit — get",
        "message": "Can you tell me my current transfer limit?",
        "bn": "আমার বর্তমান ট্রান্সফার লিমিট কত বলতে পারবেন?",
        "bl": "amar current transfer limit koto bolte parben?"
      },
      {
        "label": "14.28 My transfer limit — request change",
        "message": "I want to change my transfer limit because it's too low.",
        "bn": "আমার ট্রান্সফার লিমিট খুব কম, তাই এটা পরিবর্তন করতে চাই।",
        "bl": "amar transfer limit khub kom, tai change korte chai."
      },
      {
        "label": "14.29 My transfer limit — cancel pending change",
        "message": "I want to cancel the pending change to my daily transfer limit.",
        "bn": "আমার ডেইলি ট্রান্সফার লিমিটের যে পরিবর্তনটা পেন্ডিং আছে সেটা ক্যানসেল করতে চাই।",
        "bl": "amar daily transfer limit er pending change ta cancel korte chai."
      }
    ]
  },
  {
    "intent": "MINI_STATEMENT",
    "options": [
      {
        "label": "13.1 Transaction list",
        "message": "Please show me my recent transactions.",
        "bn": "আমার সাম্প্রতিক ট্রানজেকশনগুলো দেখান প্লিজ।",
        "bl": "amar recent transaction gulo dekhan please."
      },
      {
        "label": "13.2 Account transactions",
        "message": "I want to check all the transactions in my savings account.",
        "bn": "আমার সেভিংস অ্যাকাউন্টের সব ট্রানজেকশন দেখতে চাই।",
        "bl": "amar savings account er shob transaction dekhte chai."
      },
      {
        "label": "13.3 Credit card statement",
        "message": "Can you please provide my credit card statement for last month?",
        "bn": "গত মাসের আমার ক্রেডিট কার্ড স্টেটমেন্টটা দিতে পারবেন প্লিজ?",
        "bl": "gato maser amar credit card statement ta dite parben please?"
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

  function quickLabel(text) {
    const s = document.createElement("span");
    s.className = "quick-label";
    s.textContent = text;
    return s;
  }

  function head(backLabel, onBack, title) {
    const h = document.createElement("div");
    h.className = "quick-head";
    h.append(chip(backLabel, onBack, "quick-back"), quickLabel(title));
    return h;
  }

  function showIntents() {
    bar.replaceChildren();
    const row = document.createElement("div");
    row.className = "quick-row";
    for (const item of QUICK_INTENTS) {
      row.append(chip(item.intent, () => showOptions(item), "quick-intent"));
    }
    bar.append(quickLabel("Quick tests"), row);
  }

  function showOptions(item) {
    bar.replaceChildren();
    const row = document.createElement("div");
    row.className = "quick-row quick-options";
    for (const opt of item.options) {
      row.append(chip(opt.label, () => showVersions(item, opt)));
    }
    bar.append(head("← All intents", showIntents, item.intent), row);
  }

  function showVersions(item, opt) {
    bar.replaceChildren();
    const row = document.createElement("div");
    row.className = "quick-row";
    const versions = [
      ["English", opt.message],
      ["বাংলা", opt.bn],
      ["Banglish", opt.bl],
    ];
    for (const [name, text] of versions) {
      const c = chip(name, () => send(text), "quick-version");
      c.title = text;
      row.append(c);
    }
    bar.append(head("← " + item.intent, () => showOptions(item), opt.label), row);
  }

  showIntents();
})();
