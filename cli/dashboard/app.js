"use strict";

const token = new URLSearchParams(location.hash.slice(1)).get("token") || "";
const names = {overview: "Overview", approvals: "Approvals", pairing: "Pair phone", settings: "Settings", logs: "Live logs"};
let currentSection = "overview";
let logOffset = 0;
let pairingUri = "";
let toastTimer;

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? {"Content-Type": "application/json"} : {}),
      ...options.headers,
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function showToast(message, isError = false) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 4200);
}

function openSection(section) {
  if (!names[section]) return;
  currentSection = section;
  document.querySelectorAll(".page").forEach((page) => page.classList.toggle("active", page.id === `section-${section}`));
  document.querySelectorAll(".nav-link").forEach((button) => button.classList.toggle("active", button.dataset.section === section));
  document.querySelector("#page-title").textContent = names[section];
  if (section === "pairing") loadPairing();
  if (section === "settings") loadSettings();
  if (section === "approvals") loadTasks();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderTasks(tasks, target) {
  target.replaceChildren();
  if (!tasks.length) {
    target.append(el("div", "empty-state", "No requests waiting for approval. Your Mac is all caught up."));
    return;
  }
  for (const task of tasks) {
    const card = el("article", "task-card");
    const head = el("div", "task-head");
    head.append(el("span", "task-provider", task.provider === "claude" ? "Claude Code" : "Antigravity"));
    head.append(el("span", "task-status", (task.status || "pending").replaceAll("_", " ")));
    card.append(head, el("p", "task-prompt", task.prompt || ""));
    if (task.result) card.append(el("pre", "task-result", task.result));
    if (task.status === "pending") {
      const actions = el("div", "task-actions");
      const reject = el("button", "reject-button", "Reject");
      reject.type = "button";
      reject.addEventListener("click", () => updateTask(task.id, "reject"));
      const approve = el("button", "approve-button", "Approve & run");
      approve.type = "button";
      approve.addEventListener("click", () => updateTask(task.id, "approve"));
      actions.append(reject, approve);
      card.append(actions);
    }
    target.append(card);
  }
}

async function updateTask(id, action) {
  try {
    await api(`/api/tasks/${encodeURIComponent(id)}/${action}`, {method: "POST", body: "{}"});
    showToast(action === "approve" ? "Task approved. The host agent will run it." : "Task rejected.");
    await loadTasks();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadTasks() {
  try {
    const {tasks} = await api("/api/tasks");
    const pending = tasks.filter((task) => task.status === "pending");
    document.querySelector("#pending-count").textContent = String(pending.length);
    document.querySelector("#approval-stat").textContent = String(pending.length);
    renderTasks(pending, document.querySelector("#overview-tasks"));
    renderTasks(tasks, document.querySelector("#tasks"));
  } catch (error) {
    showToast(`Could not load approval queue: ${error.message}`, true);
  }
}

async function loadStatus() {
  try {
    const status = await api("/api/status");
    const online = status.agent_running;
    const configured = status.connection_configured;
    document.querySelector("#host-indicator").classList.toggle("online", online);
    document.querySelector("#host-state").textContent = online ? "Host online" : configured ? "Connecting" : "Setup required";
    document.querySelector("#agent-stat").textContent = online ? "Running" : configured ? "Starting" : "Set up connection";
    document.querySelector("#platform-stat").textContent = status.platform;
    const setupNotice = document.querySelector("#setup-notice");
    setupNotice.hidden = online;
    document.querySelector("#setup-title").textContent = configured
      ? "The host agent is not connected"
      : "Finish your one-time connection setup";
    document.querySelector("#setup-description").textContent = configured
      ? status.connection_message || "Check Live logs and your connection settings."
      : "Choose Telegram or enter your HTTPS relay details. The dashboard stays open while you set this up.";
    document.querySelector("#hero-action").dataset.openSection = configured ? "approvals" : "settings";
    document.querySelector("#hero-action").innerHTML = configured
      ? 'Review approvals <span>→</span>'
      : 'Set up connection <span>→</span>';
    const relay = status.relay_url || "";
    document.querySelector("#relay-stat").textContent = relay ? new URL(relay).host : "Not set up";
  } catch (error) {
    document.querySelector("#host-state").textContent = "Connection error";
    showToast(`Could not read host status: ${error.message}`, true);
  }
}

async function loadPairing() {
  const wrap = document.querySelector("#qr-wrap");
  const copy = document.querySelector("#copy-pairing");
  try {
    const data = await api("/api/pairing");
    wrap.replaceChildren();
    pairingUri = data.uri || "";
    if (data.configured && data.svg) {
      wrap.innerHTML = data.svg;
      copy.disabled = false;
    } else {
      wrap.append(el("span", "empty-qr", "Set relay URL, host ID, and phone token in Settings."));
      copy.disabled = true;
    }
  } catch (error) {
    wrap.replaceChildren(el("span", "empty-qr", error.message));
    copy.disabled = true;
  }
}

async function loadSettings() {
  try {
    const config = await api("/api/config");
    const form = document.querySelector("#settings-form");
    for (const key of ["relay_url", "relay_host_id", "relay_host_token", "relay_phone_token", "working_directory", "claude_bin", "antigravity_bin", "bot_token"]) {
      form.elements[key].value = config[key] || "";
    }
    form.elements.allowed_user_ids.value = Array.isArray(config.allowed_user_ids) ? config.allowed_user_ids.join(", ") : "";
    form.elements.keep_awake.checked = Boolean(config.keep_awake);
  } catch (error) {
    showToast(`Could not load settings: ${error.message}`, true);
  }
}

async function loadLogs() {
  if (currentSection !== "logs") return;
  try {
    const data = await api(`/api/logs?offset=${logOffset}`);
    const output = document.querySelector("#log-output");
    output.textContent += data.text;
    logOffset = data.offset;
    if (output.textContent.length > 200000) output.textContent = output.textContent.slice(-150000);
    output.scrollTop = output.scrollHeight;
  } catch (error) {
    showToast(`Could not read logs: ${error.message}`, true);
  }
}

document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", () => openSection(button.dataset.section)));
document.querySelectorAll("[data-open-section]").forEach((button) => button.addEventListener("click", () => openSection(button.dataset.openSection)));
document.querySelector("#copy-pairing").addEventListener("click", async () => {
  if (!pairingUri) return;
  try {
    await navigator.clipboard.writeText(pairingUri);
    showToast("Pairing link copied. Treat it like a password.");
  } catch (error) {
    showToast(`Could not copy pairing link: ${error.message}`, true);
  }
});
document.querySelector("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const ids = form.elements.allowed_user_ids.value.split(",").map((value) => value.trim()).filter(Boolean);
  if (ids.some((value) => !/^\d+$/.test(value))) {
    showToast("Allowed Telegram user IDs must be comma-separated numbers.", true);
    return;
  }
  const updates = {
    relay_url: form.elements.relay_url.value.trim(),
    relay_host_id: form.elements.relay_host_id.value.trim(),
    relay_host_token: form.elements.relay_host_token.value,
    relay_phone_token: form.elements.relay_phone_token.value,
    working_directory: form.elements.working_directory.value.trim(),
    claude_bin: form.elements.claude_bin.value.trim(),
    antigravity_bin: form.elements.antigravity_bin.value.trim(),
    bot_token: form.elements.bot_token.value,
    allowed_user_ids: ids,
    keep_awake: form.elements.keep_awake.checked,
  };
  try {
    await api("/api/config", {method: "POST", body: JSON.stringify(updates)});
    showToast("Settings saved securely.");
    await loadPairing();
    await loadStatus();
  } catch (error) {
    showToast(`Settings were not saved: ${error.message}`, true);
  }
});

if (!token) {
  document.querySelector("#host-state").textContent = "Open with `macremote ui`";
  showToast("Dashboard access token is missing. Open this page using `macremote ui`.", true);
} else {
  loadStatus();
  loadTasks();
  setInterval(loadStatus, 5000);
  setInterval(loadTasks, 4000);
  setInterval(loadLogs, 1000);
}
