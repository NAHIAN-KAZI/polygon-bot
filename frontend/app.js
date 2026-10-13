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
const loginUsername = document.getElementById("loginUsername");
const loginPassword = document.getElementById("loginPassword");
const loginBtn = document.getElementById("loginBtn");
const loginStatus = document.getElementById("loginStatus");
const ctxChip = document.getElementById("ctxChip");
const ctxFill = document.getElementById("ctxFill");
const ctxValue = document.getElementById("ctxValue");
const attachBtn = document.getElementById("attachBtn");
const imageInput = document.getElementById("imageInput");
const attachTray = document.getElementById("attachTray");
const attachThumb = document.getElementById("attachThumb");
const attachName = document.getElementById("attachName");
const attachRemove = document.getElementById("attachRemove");
const micBtn = document.getElementById("micBtn");
const voiceModeBtn = document.getElementById("voiceModeBtn");
const voiceModeLabel = document.getElementById("voiceModeLabel");
const recTimer = document.getElementById("recTimer");

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
  loadDemoLogin();
  loadCapabilities();
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

// Two right-hand drawers share one overlay: the knowledge base and the banking-service test fields.
const testBtn = document.getElementById("testBtn");
const testDrawer = document.getElementById("testDrawer");
const testDrawerClose = document.getElementById("testDrawerClose");

function openPanel(panel) {
  closeDrawer();
  panel.classList.add("open");
  drawerOverlay.classList.add("open");
}
function openDrawer() { openPanel(drawer); }
function closeDrawer() {
  drawer.classList.remove("open");
  testDrawer.classList.remove("open");
  drawerOverlay.classList.remove("open");
}
drawerBtn.addEventListener("click", openDrawer);
testBtn.addEventListener("click", () => openPanel(testDrawer));
drawerClose.addEventListener("click", closeDrawer);
testDrawerClose.addEventListener("click", closeDrawer);
drawerOverlay.addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

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

// Direct client-side login against the bank's own auth endpoint (T-26). No
// backend proxy: the bank's dev environment sends permissive CORS headers
// for this origin, and keeping credentials out of Polygon Bot's backend
// entirely matches ADR-0008's design intent. Confirmed response shape
// (postman/Polygon-Bank-Platform-API.postman_collection.json, T-20 live
// login): { token: { accessToken, refreshToken }, user: {...} }.
const BANK_LOGIN_URL = "https://internet-banking.dev-polygontech.xyz/auth/v1/auth/login";

// Test account from the backend's .env (DEMO_LOGIN_USERNAME / DEMO_LOGIN_PASSWORD), if
// configured. Only the username comes to the browser; with the password left blank, the
// backend logs in itself and returns just the access token.
let demoUsername = "";

async function loadDemoLogin() {
  demoUsername = "";
  if (!getApiKey()) return;
  try {
    const res = await fetch("/demo-login", { headers: headers() });
    if (!res.ok) return;
    const data = await res.json();
    demoUsername = data.username || "";
    if (!demoUsername) return;
    if (!loginUsername.value) loginUsername.value = demoUsername;
    loginPassword.placeholder = "password (blank = saved test account)";
    // Auto-login with the saved account; typing other credentials and pressing Login
    // replaces the token.
    if (!fldAuthToken.value && loginUsername.value === demoUsername && !loginPassword.value) {
      await doLogin();
    }
  } catch (e) {
    // demo login is optional
  }
}

async function doDemoLogin() {
  const res = await fetch("/demo-login", { method: "POST", headers: headers() });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data.accessToken;
}

async function doLogin() {
  const username = loginUsername.value.trim();
  const password = loginPassword.value;
  if (demoUsername && username === demoUsername && !password) {
    loginBtn.disabled = true;
    loginStatus.textContent = "Logging in with saved test account...";
    loginStatus.className = "login-status full";
    try {
      fldAuthToken.value = await doDemoLogin();
      loginStatus.textContent = "Logged in — Authorization field populated.";
      loginStatus.className = "login-status full ok";
    } catch (err) {
      loginStatus.textContent = `Login failed: ${err.message}`;
      loginStatus.className = "login-status full error";
    } finally {
      loginBtn.disabled = false;
    }
    return;
  }
  if (!username || !password) {
    loginStatus.textContent = "Enter username and password.";
    loginStatus.className = "login-status full error";
    return;
  }

  loginBtn.disabled = true;
  loginStatus.textContent = "Logging in...";
  loginStatus.className = "login-status full";

  try {
    const res = await fetch(BANK_LOGIN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      loginStatus.textContent = `Login failed: ${data.message || res.statusText}`;
      loginStatus.className = "login-status full error";
      return;
    }

    const accessToken = data && data.token && data.token.accessToken;
    if (!accessToken) {
      loginStatus.textContent = "Login response missing token.accessToken.";
      loginStatus.className = "login-status full error";
      return;
    }

    fldAuthToken.value = accessToken;
    loginPassword.value = "";
    loginStatus.textContent = "Logged in — Authorization field populated.";
    loginStatus.className = "login-status full ok";
  } catch (err) {
    loginStatus.textContent = `Error: ${err.message}`;
    loginStatus.className = "login-status full error";
  } finally {
    loginBtn.disabled = false;
  }
}

loginBtn.addEventListener("click", doLogin);

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

  const badge = document.createElement("span");
  badge.className = "result-type" + (result.type === "BANKING_SERVICE" ? "" : " warn");
  badge.textContent = result.type;
  addMetaChip([badge], panel);
  return panel;
}

// Reply details sit in one row of collapsed chips under the answer (routing result, response
// time); opening a chip shows its content full-width under the row.
function metaRow() {
  const last = messages.lastElementChild;
  if (last && last.classList.contains("reply-meta")) return last;
  const meta = el("div", "reply-meta");
  meta.append(el("div", "meta-chips"));
  messages.appendChild(meta);
  return meta;
}

function addMetaChip(labelNodes, body) {
  const meta = metaRow();
  const chip = el("button", "meta-chip");
  chip.type = "button";
  chip.setAttribute("aria-expanded", "false");
  chip.append(...labelNodes);
  body.hidden = true;
  chip.addEventListener("click", () => {
    body.hidden = !body.hidden;
    chip.setAttribute("aria-expanded", String(!body.hidden));
    chip.classList.toggle("open", !body.hidden);
    messages.scrollTop = messages.scrollHeight;
  });
  meta.querySelector(".meta-chips").appendChild(chip);
  meta.appendChild(body);
  messages.scrollTop = messages.scrollHeight;
}

function formatTokens(n) {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function formatSeconds(ms) {
  return `${(ms / 1000).toFixed(1)}s`;
}

// Header gauge: how full the model's context window got on the last message.
function updateContextChip(stats) {
  if (!stats || !stats.context_window) return;
  const pct = Math.min(100, (stats.context_tokens / stats.context_window) * 100);
  ctxChip.hidden = false;
  ctxFill.style.width = `${pct}%`;
  const level = contextLevel(pct);
  ctxChip.classList.toggle("warning", level.cls === "warning");
  ctxChip.classList.toggle("critical", level.cls === "critical");
  ctxValue.textContent = `${formatTokens(stats.context_tokens)} / ${formatTokens(stats.context_window)}`;
  ctxChip.title = `Largest prompt sent to ${stats.model || "the model"} for the last message: ` +
    `${stats.context_tokens.toLocaleString()} of ${stats.context_window.toLocaleString()} tokens (${pct.toFixed(0)}%)` +
    (level.label ? ` · ${level.label}` : "");
}

// --- reply stats -------------------------------------------------------------------
// A row of small tiles under each reply: response time (model vs everything else, with
// when the first word arrived), context used (meter), tokens and model calls. Every value
// a tooltip shows is also printed in the tile, so hovering is never required.

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function compactNumber(n) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(n);
}

// Context severity, shared by the header meter and the tile: label is never color-only.
function contextLevel(pct) {
  if (pct >= 90) return { cls: "critical", label: "Almost full" };
  if (pct >= 70) return { cls: "warning", label: "Getting full" };
  return { cls: "ok", label: "" };
}

const statTooltip = el("div", "stat-tooltip");
statTooltip.setAttribute("role", "tooltip");
statTooltip.hidden = true;
document.body.appendChild(statTooltip);

function showTooltip(target, value, label) {
  statTooltip.replaceChildren(el("strong", null, value), el("span", null, label));
  statTooltip.hidden = false;
  const box = target.getBoundingClientRect();
  const tip = statTooltip.getBoundingClientRect();
  const left = Math.min(window.innerWidth - tip.width - 8, Math.max(8, box.left + box.width / 2 - tip.width / 2));
  statTooltip.style.left = `${left}px`;
  statTooltip.style.top = `${box.top - tip.height - 8}px`;
}

function hideTooltip() {
  statTooltip.hidden = true;
}

function withTooltip(node, value, label) {
  node.tabIndex = 0;
  node.setAttribute("aria-label", `${label}: ${value}`);
  node.addEventListener("pointerenter", () => showTooltip(node, value, label));
  node.addEventListener("pointerleave", hideTooltip);
  node.addEventListener("focus", () => showTooltip(node, value, label));
  node.addEventListener("blur", hideTooltip);
  return node;
}

function statTile(label, value, extraClass) {
  const tile = el("div", `stat${extraClass ? " " + extraClass : ""}`);
  tile.append(el("div", "stat-label", label), el("div", "stat-value", value));
  return tile;
}

function timeTile(timing, stats) {
  const total = timing.totalMs;
  const tile = statTile("Response time", formatSeconds(total), "stat-time");
  if (!stats) {
    if (timing.firstTokenMs != null) tile.append(el("div", "stat-sub", `first word at ${formatSeconds(timing.firstTokenMs)}`));
    return tile;
  }
  const modelMs = Math.min(stats.llm_ms, total);
  const otherMs = Math.max(0, total - modelMs);
  const bar = el("div", "time-bar");
  const model = el("span", "seg seg-model");
  model.style.flexGrow = modelMs;
  const other = el("span", "seg seg-other");
  other.style.flexGrow = otherMs;
  const pct = (ms) => `${Math.round((ms / total) * 100)}%`;
  bar.append(
    withTooltip(model, `${formatSeconds(modelMs)} · ${pct(modelMs)}`, "Model working"),
    withTooltip(other, `${formatSeconds(otherMs)} · ${pct(otherMs)}`, "App + network"),
  );
  if (timing.firstTokenMs != null) {
    const tick = el("i", "first-word");
    tick.style.left = `${Math.min(100, (timing.firstTokenMs / total) * 100)}%`;
    bar.append(withTooltip(tick, formatSeconds(timing.firstTokenMs), "First word appeared"));
  }
  const legend = el("div", "stat-legend");
  const key = (cls, text) => {
    const item = el("span");
    item.append(el("i", `key ${cls}`), document.createTextNode(text));
    return item;
  };
  legend.append(
    key("key-model", `Model ${formatSeconds(modelMs)}`),
    key("key-other", `Other ${formatSeconds(otherMs)}`),
  );
  if (timing.firstTokenMs != null) legend.append(key("key-first", `First word ${formatSeconds(timing.firstTokenMs)}`));
  tile.append(bar, legend);
  return tile;
}

function contextTile(stats) {
  const pct = (stats.context_tokens / stats.context_window) * 100;
  const level = contextLevel(pct);
  const tile = statTile("Context used", `${pct < 1 && pct > 0 ? "<1" : Math.round(pct)}%`, `stat-context ${level.cls}`);
  const meter = el("div", "meter");
  const fill = el("i");
  fill.style.width = `${Math.min(100, pct)}%`;
  meter.append(fill);
  withTooltip(meter, `${stats.context_tokens.toLocaleString()} of ${stats.context_window.toLocaleString()} tokens`,
    "Largest prompt this reply");
  const sub = `${compactNumber(stats.context_tokens)} of ${compactNumber(stats.context_window)} tokens` +
    (level.label ? ` · ${level.label}` : "");
  tile.append(meter, el("div", "stat-sub", sub));
  return tile;
}

function addReplyStats(timing, stats) {
  const row = el("div", "reply-stats");
  row.setAttribute("role", "group");
  row.setAttribute("aria-label", "Reply stats");
  row.append(timeTile(timing, stats));
  if (stats) {
    if (stats.context_window) row.append(contextTile(stats));
    const tokens = statTile("Tokens", compactNumber(stats.prompt_tokens + stats.completion_tokens));
    tokens.append(el("div", "stat-sub",
      `${stats.prompt_tokens.toLocaleString()} in · ${stats.completion_tokens.toLocaleString()} out`));
    const calls = statTile("Model calls", String(stats.llm_calls));
    calls.append(el("div", "stat-sub",
      stats.llm_calls ? `avg ${formatSeconds(stats.llm_ms / stats.llm_calls)} each` : "none needed"));
    row.append(tokens, calls);
  }
  addMetaChip([el("span", "meta-chip-label", "Response time"),
               el("span", "meta-chip-value", formatSeconds(timing.totalMs))], row);
}

// --- voice mode: what the model works from for a spoken message ------------------------
const VOICE_MODES = {
  both: "Voice: audio + transcript",
  transcript: "Voice: transcript only",
  audio: "Voice: audio only",
  nemo: "Voice: Titu STT",
};
// The modes this backend offers (GET /chat/capabilities); older backends don't say, so
// they get the three model modes.
let voiceModes = ["both", "transcript", "audio"];
let preferredVoiceMode = "transcript"; // the viewer's pick; used whenever it's offered
let voiceMode = "transcript";
try {
  const saved = localStorage.getItem("voiceMode");
  if (saved in VOICE_MODES) preferredVoiceMode = saved;
} catch (e) { /* private mode */ }
function showVoiceMode() {
  voiceMode = voiceModes.includes(preferredVoiceMode) ? preferredVoiceMode
    : voiceModes.includes("transcript") ? "transcript" : voiceModes[0];
  voiceModeLabel.textContent = VOICE_MODES[voiceMode];
  voiceModeBtn.classList.toggle("on", voiceMode !== "transcript");
}
voiceModeBtn.addEventListener("click", () => {
  preferredVoiceMode = voiceModes[(voiceModes.indexOf(voiceMode) + 1) % voiceModes.length];
  try { localStorage.setItem("voiceMode", preferredVoiceMode); } catch (e) { /* optional */ }
  showVoiceMode();
});
showVoiceMode();

// --- read aloud: a reply spoken by the server (POST /tts) --------------------------------
// Offered only when GET /chat/capabilities says read_aloud. One reply plays at a time.
let readAloud = false;
let playing = null; // { audio, chip, label } of the reply being read

function stopReading() {
  if (!playing) return;
  playing.audio.pause();
  playing.chip.classList.remove("playing");
  playing.label.textContent = "Read aloud";
  playing = null;
}

function addReadAloudChip(text) {
  if (!readAloud || !text) return;
  const chip = el("button", "meta-chip read-aloud");
  const label = el("span", "meta-chip-value", "Read aloud");
  chip.type = "button";
  chip.append(el("span", "meta-chip-label", "🔊"), label);
  let url = null; // fetched once, replayed from memory
  chip.addEventListener("click", async () => {
    if (playing && playing.chip === chip) { stopReading(); return; }
    stopReading();
    const audio = new Audio();
    playing = { audio, chip, label };
    chip.classList.add("playing");
    label.textContent = "Loading…";
    try {
      if (!url) {
        const res = await fetch("/tts", {
          method: "POST",
          headers: headers({ "Content-Type": "application/json" }),
          body: JSON.stringify({ text }),
        });
        if (!res.ok) throw new Error(res.statusText);
        url = URL.createObjectURL(await res.blob());
      }
      if (!playing || playing.audio !== audio) return; // stopped while loading
      audio.src = url;
      audio.addEventListener("ended", stopReading);
      label.textContent = "Stop";
      await audio.play();
    } catch (err) {
      if (playing && playing.audio === audio) {
        stopReading();
        label.textContent = "Couldn't read aloud";
      }
    }
  });
  metaRow().querySelector(".meta-chips").appendChild(chip);
}

// --- image input ------------------------------------------------------------------
// Shown only when the backend says its model reads images (GET /chat/capabilities).
let pendingImage = null; // data: URL, downscaled
let maxImageMb = 5;
const MAX_IMAGE_SIDE = 1280;

async function loadCapabilities() {
  attachBtn.hidden = true;
  if (!getApiKey()) return;
  try {
    const res = await fetch("/chat/capabilities", { headers: headers() });
    if (!res.ok) return;
    const caps = await res.json();
    attachBtn.hidden = !caps.image_input;
    maxImageMb = caps.max_image_mb || maxImageMb;
    // voice_modes lists every way this backend takes a voice message; audio_input only says
    // whether the model itself hears audio (older backends send just that).
    const offered = (caps.voice_modes || (caps.audio_input ? voiceModes : []))
      .filter((m) => m in VOICE_MODES);
    // Recording needs a secure page (https or localhost) and a browser that can record.
    micBtn.hidden = !(offered.length && navigator.mediaDevices && window.MediaRecorder);
    voiceModeBtn.hidden = micBtn.hidden;
    if (offered.length) voiceModes = offered;
    showVoiceMode();
    maxAudioSeconds = caps.max_audio_seconds || maxAudioSeconds;
    readAloud = Boolean(caps.read_aloud);
  } catch (e) {
    // optional
  }
}

// Large photos are scaled down (longest side MAX_IMAGE_SIDE) and re-encoded as JPEG:
// the model sees images at low resolution anyway, and it keeps requests small.
async function toDataUrl(file) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_IMAGE_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff"; // transparent PNGs get a white background, not black
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.85);
}

async function setPendingImage(file) {
  if (!file || !/^image\/(png|jpeg|webp|gif)$/.test(file.type)) {
    addMessage("bot error", "Attach a PNG, JPEG, WebP or GIF image.");
    return;
  }
  try {
    const dataUrl = await toDataUrl(file);
    if (dataUrl.length * 0.75 > maxImageMb * 1024 * 1024) {
      addMessage("bot error", `The image is larger than ${maxImageMb} MB.`);
      return;
    }
    pendingImage = dataUrl;
    attachThumb.src = dataUrl;
    attachName.textContent = file.name || "Pasted image";
    attachTray.hidden = false;
    chatInput.focus();
  } catch (e) {
    addMessage("bot error", "That image couldn't be opened.");
  }
}

function clearPendingImage() {
  pendingImage = null;
  imageInput.value = "";
  attachTray.hidden = true;
  attachThumb.removeAttribute("src");
}

attachBtn.addEventListener("click", () => imageInput.click());
imageInput.addEventListener("change", () => setPendingImage(imageInput.files[0]));
attachRemove.addEventListener("click", clearPendingImage);
chatInput.addEventListener("paste", (e) => {
  if (attachBtn.hidden) return;
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (item) {
    e.preventDefault();
    setPendingImage(item.getAsFile());
  }
});

// --- voice input --------------------------------------------------------------------
// Click the mic to record, click again (or wait for the limit) to send. The recording is
// converted to 16 kHz mono WAV in the browser -- what the model expects -- and the backend
// answers its transcript like typed text.
let maxAudioSeconds = 30;
let recorder = null;
let recordStartedAt = 0;
let recordTick = null;
let pendingAudio = null;

function formatClock(seconds) {
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset, str) => [...str].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const v = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return buffer;
}

async function toWavDataUrl(blob) {
  const decodeCtx = new AudioContext();
  const decoded = await decodeCtx.decodeAudioData(await blob.arrayBuffer());
  decodeCtx.close();
  const rate = 16000;
  const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * rate), rate);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  const bytes = new Uint8Array(encodeWav(rendered.getChannelData(0), rate));
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return `data:audio/wav;base64,${btoa(binary)}`;
}

function setRecordingUi(on) {
  micBtn.classList.toggle("recording", on);
  micBtn.setAttribute("aria-label", on ? "Stop and send voice message" : "Record a voice message");
  micBtn.title = on ? "Stop and send" : "Record a voice message";
  recTimer.hidden = !on;
  chatInput.placeholder = on ? "Listening… click stop to send" : "Message Polygon Bot...";
}

async function startRecording() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    addMessage("bot error", "Microphone access was blocked. Allow it in the browser to send voice messages.");
    return;
  }
  const chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    clearInterval(recordTick);
    setRecordingUi(false);
    const seconds = (performance.now() - recordStartedAt) / 1000;
    recorder = null;
    if (seconds < 0.5) return; // a stray click, not a message
    try {
      pendingAudio = await toWavDataUrl(new Blob(chunks, { type: chunks[0]?.type || "audio/webm" }));
      chatForm.requestSubmit();
    } catch (e) {
      addMessage("bot error", "That recording couldn't be processed. Please try again.");
    }
  };
  recorder.start();
  recordStartedAt = performance.now();
  recTimer.textContent = "0:00";
  setRecordingUi(true);
  recordTick = setInterval(() => {
    const elapsed = (performance.now() - recordStartedAt) / 1000;
    recTimer.textContent = formatClock(elapsed);
    if (elapsed >= maxAudioSeconds) recorder?.stop();
  }, 250);
}

micBtn.addEventListener("click", () => {
  if (recorder) recorder.stop();
  else startRecording();
});

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
  if (recorder) return; // still recording: the stop button sends
  const image = pendingImage;
  const audio = pendingAudio;
  pendingAudio = null;
  const typed = chatInput.value.trim();
  const question = typed || (image && !audio ? "Please look at this image." : "");
  if (!question && !audio) return;

  const extras = readRoutingExtras();
  if (extras.error) {
    addMessage("user", question);
    chatInput.value = "";
    addMessage("bot error", `Error: ${extras.error}`);
    return;
  }

  const userDiv = addMessage("user", question);
  let voiceLine = null;
  if (audio) {
    voiceLine = el("div", "voice-line", voiceMode === "audio" ? "🎤 Voice message (audio only)" : "🎤 Voice message · transcribing…");
    if (!question) userDiv.textContent = "";
    userDiv.appendChild(voiceLine);
  }
  if (image) {
    const thumb = document.createElement("img");
    thumb.className = "msg-image";
    thumb.src = image;
    thumb.alt = "Attached image";
    userDiv.appendChild(thumb);
    clearPendingImage();
  }
  chatInput.value = "";

  const botDiv = addTypingBubble();
  let botText = "";
  let gotFirstToken = false;
  let result = null;
  let stats = null;
  const startedAt = performance.now();
  let firstTokenMs = null;

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: headers({ "Content-Type": "application/json", ...extras.headers }),
      body: JSON.stringify({
        ...(question ? { message: question } : {}),
        include_stats: true,
        ...(image ? { image } : {}),
        ...(audio ? { audio, audio_mode: voiceMode } : {}),
        ...extras.body,
      }),
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
            firstTokenMs = performance.now() - startedAt;
          }
          botText += payload.token;
          botDiv.textContent = botText;
          messages.scrollTop = messages.scrollHeight;
        } else if (eventName === "result") {
          result = payload;
        } else if (eventName === "transcript") {
          // What the model heard, shown in the customer's own bubble so they can check it.
          if (voiceLine) voiceLine.textContent = `🎤 “${payload.text}”`;
        } else if (eventName === "image") {
          // What the model read from the image, shown so the customer can check it.
          const caption = document.createElement("div");
          caption.className = "image-read";
          caption.textContent = `Image read as: ${payload.text}`;
          messages.insertBefore(caption, botDiv);
        } else if (eventName === "stats") {
          stats = payload;
          updateContextChip(stats);
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
    if (!botDiv.classList.contains("error")) addReadAloudChip(botDiv.textContent.trim());
    addReplyStats({ totalMs: performance.now() - startedAt, firstTokenMs }, stats);
  } catch (err) {
    botDiv.className = "msg bot error";
    botDiv.textContent = `Error: ${err.message}`;
  }
});

// Dev servers with DEMO_PORTAL_AUTOFILL_API_KEY=true hand out the API key, so nobody
// has to type it; a key already stored (or typed via the key button) wins.
async function autofillApiKey() {
  if (getApiKey()) return;
  try {
    const res = await fetch("/demo-config");
    if (!res.ok) return;
    const data = await res.json();
    if (data.apiKey) setApiKey(data.apiKey);
  } catch (e) {
    // autofill is optional
  }
}

(async () => {
  await autofillApiKey();
  updateKeyBtn();
  refreshDocs();
  loadDemoLogin();
  loadCapabilities();
})();
checkHealth();
setInterval(checkHealth, 15000);
