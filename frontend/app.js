const keyBtn = document.getElementById("keyBtn");
const introKeyBtn = document.getElementById("introKeyBtn");
const healthChip = document.getElementById("healthChip");
const healthLabel = document.getElementById("healthLabel");
const drawerBtn = document.getElementById("drawerBtn");
const drawerClose = document.getElementById("drawerClose");
const drawer = document.getElementById("drawer");
const drawerOverlay = document.getElementById("drawerOverlay");
const uploadForm = document.getElementById("uploadForm");
const fileInput = document.getElementById("fileInput");
const dzText = document.getElementById("dzText");
const uploadStatus = document.getElementById("uploadStatus");
const docList = document.getElementById("docList");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const messages = document.getElementById("messages");
const fldCategory = document.getElementById("fldCategory");
const fldService = document.getElementById("fldService");
const fldSubservice = document.getElementById("fldSubservice");
const fldPayload = document.getElementById("fldPayload");
const fldAuthToken = document.getElementById("fldAuthToken");

const KEY_STORAGE = "chatbot_api_key";

function getApiKey() {
  try {
    return localStorage.getItem(KEY_STORAGE) || "";
  } catch (e) {
    return "";
  }
}

function setApiKey(key) {
  try {
    localStorage.setItem(KEY_STORAGE, key);
  } catch (e) {
    // ignore (private browsing etc.)
  }
}

function updateKeyBtn() {
  const hasKey = !!getApiKey();
  keyBtn.classList.toggle("set", hasKey);
  if (introKeyBtn) introKeyBtn.hidden = hasKey;
}

function promptForKey() {
  const current = getApiKey();
  const next = prompt("API key:", current);
  if (next === null) return;
  setApiKey(next.trim());
  updateKeyBtn();
  refreshDocs();
}

keyBtn.addEventListener("click", promptForKey);
if (introKeyBtn) introKeyBtn.addEventListener("click", promptForKey);

function nudgeKeyBtn() {
  keyBtn.classList.remove("attn");
  // restart the animation even if it's already mid-run
  void keyBtn.offsetWidth;
  keyBtn.classList.add("attn");
}

function headers(extra = {}) {
  const key = getApiKey();
  return key ? { "X-API-Key": key, ...extra } : extra;
}

function openDrawer() {
  drawer.classList.add("open");
  drawerOverlay.classList.add("open");
}
function closeDrawer() {
  drawer.classList.remove("open");
  drawerOverlay.classList.remove("open");
}
drawerBtn.addEventListener("click", openDrawer);
drawerClose.addEventListener("click", closeDrawer);
drawerOverlay.addEventListener("click", closeDrawer);

async function checkHealth() {
  try {
    const res = await fetch("/health");
    const data = await res.json();
    const ok = res.ok && data.status === "ok";
    healthChip.classList.toggle("ok", ok);
    healthChip.classList.toggle("down", !ok);
    healthLabel.textContent = ok ? "Online" : "Degraded";
  } catch (e) {
    healthChip.classList.remove("ok");
    healthChip.classList.add("down");
    healthLabel.textContent = "Offline";
  }
}

fileInput.addEventListener("change", () => {
  dzText.textContent = fileInput.files[0] ? fileInput.files[0].name : "Add document";
});

async function refreshDocs() {
  try {
    const res = await fetch("/documents", { headers: headers() });
    if (!res.ok) return;
    const docs = await res.json();
    if (docs.length === 0) {
      docList.replaceChildren(
        Object.assign(document.createElement("li"), {
          className: "empty",
          textContent: "Empty. Add a document to begin.",
        })
      );
      return;
    }
    docList.replaceChildren(
      ...docs.map((d, i) => {
        const li = document.createElement("li");
        li.className = "doc-tab";
        const idx = document.createElement("span");
        idx.className = "idx";
        idx.textContent = String(i + 1).padStart(2, "0");
        const name = document.createElement("span");
        name.className = "name";
        name.textContent = d.filename;
        name.title = d.filename;
        li.append(idx, name);
        return li;
      })
    );
  } catch (e) {
    // ignore
  }
}

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);

  uploadStatus.textContent = "Uploading...";
  try {
    const res = await fetch("/documents", {
      method: "POST",
      headers: headers(),
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 401) {
        uploadStatus.textContent = "Set your API key first (top right).";
        nudgeKeyBtn();
      } else {
        uploadStatus.textContent = `Error: ${data.detail || res.statusText}`;
      }
      return;
    }
    uploadStatus.textContent = `Added ${data.filename}`;
    fileInput.value = "";
    dzText.textContent = "Add document";
    refreshDocs();
  } catch (err) {
    uploadStatus.textContent = `Error: ${err.message}`;
  }
});

function addMessage(role, text) {
  const intro = messages.querySelector(".intro");
  if (intro) intro.remove();

  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

// Reads the optional "banking-service test fields" panel and builds the
// extra /chat request body fields + Authorization header, if any are set.
// Returns { body: {...}, headers: {...}, error: string|null }.
function readRoutingExtras() {
  const body = {};
  const category = fldCategory.value.trim();
  const service = fldService.value.trim();
  const subservice = fldSubservice.value.trim();
  const payloadRaw = fldPayload.value.trim();
  const token = fldAuthToken.value.trim();

  if (category) body.category = category;
  if (service) body.service = service;
  if (subservice) body.subservice = subservice;

  let payload = null;
  if (payloadRaw) {
    try {
      payload = JSON.parse(payloadRaw);
    } catch (e) {
      return { body: null, headers: null, error: `payload is not valid JSON: ${e.message}` };
    }
    body.payload = payload;
  }

  const extraHeaders = {};
  if (token) extraHeaders["Authorization"] = `Bearer ${token}`;

  return { body, headers: extraHeaders, error: null };
}

function prettyOrDash(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

// Renders the structured `result` SSE event (type/category/service/
// subservice/payload/routing) as a small panel under the bot reply, for
// demo/verification purposes — not shown for plain KB answers.
function addResultPanel(result) {
  const panel = document.createElement("div");
  panel.className = "result-panel";

  const badge = document.createElement("span");
  badge.className = "result-type" + (result.type === "BANKING_SERVICE" ? "" : " warn");
  badge.textContent = result.type;
  panel.appendChild(badge);

  const dl = document.createElement("dl");
  const rows = [
    ["category", result.category],
    ["service", result.service],
    ["subservice", result.subservice],
    ["payload", result.payload],
    ["routing", result.routing],
  ];
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = prettyOrDash(value);
    dl.append(dt, dd);
  }
  panel.appendChild(dl);

  messages.appendChild(panel);
  messages.scrollTop = messages.scrollHeight;
  return panel;
}

function addTypingBubble() {
  const intro = messages.querySelector(".intro");
  if (intro) intro.remove();

  const div = document.createElement("div");
  div.className = "msg bot";
  div.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

// Strips any inline "[filename.ext ...]" style citation the model may add,
// so the knowledge-base's internal file/page names never surface in the UI.
function stripCitations(text) {
  return text
    .replace(/\s*\[[^[\]]*\.(pdf|docx|txt|md)[^[\]]*\]/gi, "")
    .replace(/\s+([.,!?])/g, "$1")
    .trim();
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = chatInput.value.trim();
  if (!question) return;

  const extras = readRoutingExtras();
  if (extras.error) {
    addMessage("user", question);
    chatInput.value = "";
    addMessage("bot error", `Error: ${extras.error}`);
    return;
  }

  addMessage("user", question);
  chatInput.value = "";

  const botDiv = addTypingBubble();
  let botText = "";
  let gotFirstToken = false;
  let result = null;

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: headers({ "Content-Type": "application/json", ...extras.headers }),
      body: JSON.stringify({ message: question, ...extras.body }),
    });

    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => ({}));
      botDiv.className = "msg bot error";
      if (res.status === 401) {
        botDiv.textContent = "Set your API key first (top right) to chat.";
        nudgeKeyBtn();
      } else {
        botDiv.textContent = `Error: ${data.detail || res.statusText}`;
      }
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        const eventMatch = rawEvent.match(/^event: (.+)$/m);
        const dataMatch = rawEvent.match(/^data: (.+)$/m);
        if (!eventMatch || !dataMatch) continue;

        const eventName = eventMatch[1];
        const payload = JSON.parse(dataMatch[1]);

        if (eventName === "token") {
          if (!gotFirstToken) {
            botDiv.textContent = "";
            gotFirstToken = true;
          }
          botText += payload.token;
          botDiv.textContent = botText;
          messages.scrollTop = messages.scrollHeight;
        } else if (eventName === "result") {
          result = payload;
        } else if (eventName === "error") {
          botDiv.className = "msg bot error";
          botDiv.textContent = `Error: ${payload.detail}`;
        }
      }
    }

    if (gotFirstToken) {
      botDiv.textContent = stripCitations(botText) || botDiv.textContent;
    }

    // Only banking-service outcomes send a `result` event — a plain KB
    // answer never does, so this leaves that path completely unchanged.
    if (result) {
      addResultPanel(result);
    }
  } catch (err) {
    botDiv.className = "msg bot error";
    botDiv.textContent = `Error: ${err.message}`;
  }
});

updateKeyBtn();
refreshDocs();
checkHealth();
setInterval(checkHealth, 15000);
