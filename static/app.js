"use strict";

const state = { conversationId: null, inboxId: null, providers: [] };
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const request = { ...options, headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } };
  if (request.body && typeof request.body !== "string") request.body = JSON.stringify(request.body);
  const response = await fetch(path, request);
  const data = await response.json().catch(() => ({ error: "Invalid server response" }));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

let toastTimer;
function toast(message, isError = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, 4500);
}

function busy(button, isBusy, label) {
  if (isBusy) {
    button.dataset.originalText = button.textContent;
    button.textContent = label || "Working…";
  } else if (button.dataset.originalText) {
    button.textContent = button.dataset.originalText;
  }
  button.disabled = isBusy;
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== `view-${name}`; view.classList.toggle("active", view.id === `view-${name}`); });
  document.querySelectorAll(".nav-item").forEach((tab) => {
    const selected = tab.dataset.view === name;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", String(selected));
  });
  if (name === "memory") loadMemories().catch((error) => toast(error.message, true));
  if (name === "dashboard") loadDashboard().catch((error) => toast(error.message, true));
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  $("#dashboard-app-status").textContent = `${data.application.status === "ok" ? "Online" : "Unavailable"} · Database ${data.database.status}`;
  $("#dashboard-app-detail").textContent = `App v${data.application.version} · SQLite schema v${data.database.schema_version}`;
  $("#dashboard-provider-count").textContent = String(data.configured_provider_count);
  $("#dashboard-provider-detail").textContent = `External providers configured · Offline mock ${data.providers.find((item) => item.id === "mock")?.configured ? "ready" : "unavailable"}`;
  $("#dashboard-memory-count").textContent = String(data.counts.memories);
  $("#dashboard-message-count").textContent = `${data.counts.messages} messages in ${data.counts.conversations} conversations`;
  $("#dashboard-email-status").textContent = `${data.email.provider === "mock" ? "Mock" : data.email.provider} · ${data.email.status}`;
  $("#dashboard-evaluation-status").textContent = data.evaluation.recent_runs.length ? `${data.evaluation.recent_runs.length} saved runs` : "CLI available; no persisted runs.";
  $("#dashboard-test-status").textContent = data.test_runs.recent_runs.length ? `${data.test_runs.recent_runs.length} saved runs` : "No persisted browser test runs.";
  const container = $("#dashboard-conversations");
  container.replaceChildren();
  if (!data.recent_conversations.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No conversations yet. Open chat to begin.";
    container.append(empty);
    return;
  }
  data.recent_conversations.forEach((conversation) => {
    const button = document.createElement("button");
    button.className = "dashboard-conversation";
    const title = document.createElement("strong");
    title.textContent = conversation.title;
    const meta = document.createElement("small");
    meta.textContent = `${conversation.message_count} messages · ${conversation.updated_at}`;
    button.append(title, meta);
    button.addEventListener("click", async () => {
      state.conversationId = conversation.id;
      showView("chat");
      await Promise.all([loadConversations(), loadConversation()]);
    });
    container.append(button);
  });
}

async function loadProviders() {
  const data = await api("/api/providers");
  state.providers = data.providers;
  const select = $("#provider-select");
  select.replaceChildren();
  data.providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = `${provider.label}${provider.configured ? "" : " · key needed"}`;
    option.disabled = !provider.configured;
    select.append(option);
  });
  select.value = data.providers.some((p) => p.id === data.default && p.configured) ? data.default : "mock";
  updateProviderNote();
}

function updateProviderNote() {
  const provider = state.providers.find((item) => item.id === $("#provider-select").value);
  if (!provider) return;
  $("#provider-note").textContent = provider.external
    ? `${provider.model} · External API charges/limits depend on your provider account.`
    : "The mock runs offline and makes no external request.";
}

async function createConversation() {
  const conversation = await api("/api/conversations", { method: "POST", body: {} });
  state.conversationId = conversation.id;
  await Promise.all([loadConversations(), loadConversation()]);
  $("#chat-input").focus();
}

async function loadConversations() {
  const data = await api("/api/conversations");
  const container = $("#conversation-list");
  container.replaceChildren();
  if (!data.conversations.length) {
    await createConversation();
    return;
  }
  data.conversations.forEach((conversation) => {
    const button = document.createElement("button");
    button.className = `conversation-item${conversation.id === state.conversationId ? " selected" : ""}`;
    button.type = "button";
    const title = document.createElement("span");
    title.textContent = conversation.title;
    const count = document.createElement("small");
    count.textContent = `${conversation.message_count} messages`;
    button.append(title, count);
    button.addEventListener("click", async () => {
      state.conversationId = conversation.id;
      await Promise.all([loadConversations(), loadConversation()]);
    });
    container.append(button);
  });
  if (!state.conversationId) {
    state.conversationId = data.conversations[0].id;
    await loadConversation();
    await loadConversations();
  }
}

function renderMessage(message) {
  const article = document.createElement("article");
  article.className = `message ${message.role}`;
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = message.role === "user" ? "You" : `Assistant${message.provider ? ` · ${message.provider}` : ""}`;
  const content = document.createElement("p");
  content.textContent = message.content;
  article.append(meta, content);
  return article;
}

async function loadConversation() {
  if (!state.conversationId) return;
  const conversation = await api(`/api/conversations/${encodeURIComponent(state.conversationId)}`);
  $("#conversation-title").textContent = conversation.title;
  const container = $("#messages");
  container.replaceChildren();
  if (!conversation.messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const heading = document.createElement("h2");
    heading.textContent = "Train your workflow, not the model.";
    const text = document.createElement("p");
    text.textContent = "Start with the offline mock. Your conversation and selected memories persist in SQLite.";
    empty.append(heading, text);
    container.append(empty);
  } else {
    conversation.messages.forEach((message) => container.append(renderMessage(message)));
  }
  container.scrollTop = container.scrollHeight;
}

async function renameConversation() {
  if (!state.conversationId) return;
  const proposed = window.prompt("Conversation name", $("#conversation-title").textContent);
  if (proposed === null) return;
  if (!proposed.trim()) { toast("Conversation name cannot be empty.", true); return; }
  const button = $("#rename-chat");
  busy(button, true);
  try {
    await api(`/api/conversations/${encodeURIComponent(state.conversationId)}`, { method: "PATCH", body: { title: proposed } });
    await Promise.all([loadConversations(), loadConversation()]);
    toast("Conversation renamed.");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
}

async function deleteConversation() {
  if (!state.conversationId || !window.confirm("Delete this conversation and its messages? Sourced memories will remain without the conversation link.")) return;
  const button = $("#delete-chat");
  busy(button, true);
  try {
    await api(`/api/conversations/${encodeURIComponent(state.conversationId)}`, { method: "DELETE" });
    state.conversationId = null;
    await loadConversations();
    toast("Conversation deleted.");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
}

async function exportConversation() {
  if (!state.conversationId) return;
  const button = $("#export-chat");
  busy(button, true, "Exporting…");
  try {
    const response = await fetch(`/api/conversations/${encodeURIComponent(state.conversationId)}/export?format=markdown`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: "Export failed" }));
      throw new Error(error.error || "Export failed");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `conversation-${state.conversationId}.md`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    toast("Markdown export downloaded.");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
}

async function sendMessage(event) {
  event.preventDefault();
  const input = $("#chat-input");
  const button = $("#send-message");
  if (!input.value.trim() || !state.conversationId) return;
  busy(button, true, "Thinking…");
  $("#messages").setAttribute("aria-busy", "true");
  try {
    const result = await api(`/api/conversations/${encodeURIComponent(state.conversationId)}/messages`, {
      method: "POST",
      body: { content: input.value, provider: $("#provider-select").value },
    });
    input.value = "";
    await Promise.all([loadConversation(), loadConversations()]);
    if (result.retrieved_memories.length) toast(`Response used ${result.retrieved_memories.length} retrieved memor${result.retrieved_memories.length === 1 ? "y" : "ies"}.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    busy(button, false);
    $("#messages").setAttribute("aria-busy", "false");
  }
}

async function extractMemories() {
  if (!state.conversationId) return;
  const button = $("#extract-memory");
  busy(button, true, "Extracting…");
  try {
    const result = await api("/api/memory/extract", { method: "POST", body: { conversation_id: state.conversationId } });
    toast(result.count ? `Saved ${result.count} new memor${result.count === 1 ? "y" : "ies"}.` : "No new explicit facts found. Try ‘Remember that…’. ");
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
}

function memoryCard(memory) {
  const article = document.createElement("article");
  article.className = "memory-item";
  const content = document.createElement("p");
  content.textContent = memory.content;
  const footer = document.createElement("div");
  const tags = document.createElement("span");
  tags.className = "tags";
  tags.textContent = memory.tags.length ? memory.tags.map((tag) => `#${tag}`).join(" ") : "untagged";
  const remove = document.createElement("button");
  remove.className = "text-button";
  remove.textContent = "Delete";
  remove.addEventListener("click", async () => {
    if (!window.confirm("Delete this memory?")) return;
    try { await api(`/api/memory/${encodeURIComponent(memory.id)}`, { method: "DELETE" }); await loadMemories(); }
    catch (error) { toast(error.message, true); }
  });
  footer.append(tags, remove);
  article.append(content, footer);
  return article;
}

async function loadMemories(query = "") {
  const data = await api(`/api/memory${query ? `?q=${encodeURIComponent(query)}` : ""}`);
  const container = $("#memory-results");
  container.replaceChildren();
  if (!data.memories.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = query ? "No matching memories." : "No memories yet. Add one or extract facts from a chat.";
    container.append(empty);
    return;
  }
  data.memories.forEach((memory) => container.append(memoryCard(memory)));
}

async function saveMemory(event) {
  event.preventDefault();
  try {
    await api("/api/memory", { method: "POST", body: { content: $("#memory-content").value, tags: $("#memory-tags").value } });
    $("#memory-form").reset();
    await loadMemories($("#memory-search").value);
    toast("Memory saved.");
  } catch (error) { toast(error.message, true); }
}

function setInboxControls(enabled) {
  ["#send-demo", "#poll-inbox", "#apply-failure", "#copy-inbox", "#delete-inbox"].forEach((selector) => { $(selector).disabled = !enabled; });
}

function renderInbox(inbox) {
  $("#inbox-address").textContent = inbox.address;
  $("#inbox-status").textContent = `Status: ${inbox.status}`;
  $("#inbox-expiry").textContent = `Expiration: ${inbox.expires_at || "not supplied"}`;
}

async function createInbox() {
  const button = $("#create-inbox");
  busy(button, true);
  try {
    const inbox = await api("/api/email/mock/inboxes", { method: "POST", body: { ttl_seconds: Number($("#inbox-ttl").value) } });
    state.inboxId = inbox.id;
    renderInbox(inbox);
    setInboxControls(true);
    $("#email-messages").replaceChildren();
    $("#verification-result").innerHTML = "<span>Inbox ready</span><p>Send a demo verification message.</p>";
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
}

function renderEmails(messages) {
  const container = $("#email-messages");
  container.replaceChildren();
  messages.forEach((message) => {
    const article = document.createElement("article");
    const heading = document.createElement("strong");
    heading.textContent = message.subject || "(No subject)";
    const sender = document.createElement("small");
    sender.textContent = message.sender;
    const body = document.createElement("p");
    body.textContent = message.text;
    article.append(heading, sender, body);
    container.append(article);
  });
}

async function sendDemo() {
  if (!state.inboxId) return;
  try {
    await api(`/api/email/mock/inboxes/${encodeURIComponent(state.inboxId)}/demo`, { method: "POST", body: { code_type: $("#code-type").value, html: $("#demo-html").checked } });
    renderInbox(await api(`/api/email/mock/inboxes/${encodeURIComponent(state.inboxId)}`));
    toast("Demo message injected locally. Check the inbox to parse it.");
    $("#verification-result").innerHTML = "<span>Message delivered</span><p>Run the parser to detect its code.</p>";
  } catch (error) { toast(error.message, true); }
}

function selectedOTPRules() {
  const rules = { max_age_seconds: Number($("#otp-max-age").value) };
  if ($("#otp-length").value) rules.expected_length = Number($("#otp-length").value);
  const textRules = { sender: "#otp-sender", subject: "#otp-subject", expected_application: "#otp-application", expected_test_run: "#otp-run" };
  Object.entries(textRules).forEach(([name, selector]) => { if ($(selector).value.trim()) rules[name] = $(selector).value.trim(); });
  return rules;
}

async function pollInbox() {
  if (!state.inboxId) return;
  const button = $("#poll-inbox");
  busy(button, true, "Checking…");
  $("#cancel-poll").disabled = false;
  try {
    const result = await api(`/api/email/mock/inboxes/${encodeURIComponent(state.inboxId)}/poll`, {
      method: "POST",
      body: {
        timeout_seconds: Number($("#poll-timeout").value),
        interval_seconds: Number($("#poll-interval").value),
        backoff_multiplier: Number($("#poll-backoff").value),
        rules: selectedOTPRules(),
      },
    });
    const resultBox = $("#verification-result");
    resultBox.replaceChildren();
    const status = document.createElement("span");
    status.textContent = result.found ? "Code verified" : `Status: ${result.status}`;
    const code = document.createElement("strong");
    code.className = "parsed-code";
    code.textContent = result.found ? result.code : "—";
    const detail = document.createElement("p");
    detail.textContent = result.found ? "Parsed from an authorized mock message; not saved permanently." : (result.error || "No code found.");
    resultBox.append(status, code, detail);
    renderEmails(result.messages);
    renderInbox(await api(`/api/email/mock/inboxes/${encodeURIComponent(state.inboxId)}`));
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); $("#cancel-poll").disabled = true; }
}

async function cancelPolling() {
  if (!state.inboxId) return;
  try {
    const result = await api(`/api/email/mock/inboxes/${encodeURIComponent(state.inboxId)}/cancel`, { method: "POST", body: {} });
    toast(result.cancelled ? "Polling cancellation requested." : "No active poll to cancel.");
  } catch (error) { toast(error.message, true); }
}

async function applyFailureMode() {
  if (!state.inboxId) return;
  try {
    const result = await api(`/api/email/mock/inboxes/${encodeURIComponent(state.inboxId)}/failure`, { method: "POST", body: { mode: $("#failure-mode").value } });
    toast(`Mock behavior set to ${result.failure_mode}.`);
  } catch (error) { toast(error.message, true); }
}

async function copyInboxAddress() {
  if (!state.inboxId) return;
  try {
    await navigator.clipboard.writeText($("#inbox-address").textContent);
    toast("Mock address copied.");
  } catch (error) { toast("Clipboard unavailable; select the displayed address manually.", true); }
}

async function deleteInbox() {
  if (!state.inboxId || !window.confirm("Delete this mock inbox and its ephemeral messages?")) return;
  try {
    await api(`/api/email/mock/inboxes/${encodeURIComponent(state.inboxId)}`, { method: "DELETE" });
    state.inboxId = null;
    setInboxControls(false);
    $("#inbox-address").textContent = "No inbox created";
    $("#inbox-status").textContent = "Status: deleted";
    $("#inbox-expiry").textContent = "Expiration: —";
    $("#email-messages").replaceChildren();
    toast("Mock inbox and messages deleted.");
  } catch (error) { toast(error.message, true); }
}

async function loadArenas() {
  const button = $("#load-arenas");
  const output = $("#arena-output");
  busy(button, true, "Loading…");
  output.textContent = "Requesting the documented /arenas endpoint through the backend…";
  try { output.textContent = JSON.stringify(await api("/api/designarena/arenas"), null, 2); }
  catch (error) { output.textContent = `${error.message}\n\nApply for API access through the official documentation, then set DESIGNARENA_API_KEY in .env and restart.`; }
  finally { busy(button, false); }
}

async function initialize() {
  document.querySelectorAll(".nav-item").forEach((tab) => tab.addEventListener("click", () => showView(tab.dataset.view)));
  $("#new-chat").addEventListener("click", () => createConversation().catch((error) => toast(error.message, true)));
  $("#rename-chat").addEventListener("click", renameConversation);
  $("#delete-chat").addEventListener("click", deleteConversation);
  $("#export-chat").addEventListener("click", exportConversation);
  $("#refresh-dashboard").addEventListener("click", () => loadDashboard().then(() => toast("Dashboard refreshed.")).catch((error) => toast(error.message, true)));
  document.querySelectorAll("[data-open-view]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.openView)));
  $("#chat-form").addEventListener("submit", sendMessage);
  $("#provider-select").addEventListener("change", updateProviderNote);
  $("#extract-memory").addEventListener("click", extractMemories);
  $("#memory-form").addEventListener("submit", saveMemory);
  $("#memory-search-form").addEventListener("submit", (event) => { event.preventDefault(); loadMemories($("#memory-search").value).catch((error) => toast(error.message, true)); });
  $("#create-inbox").addEventListener("click", createInbox);
  $("#send-demo").addEventListener("click", sendDemo);
  $("#poll-inbox").addEventListener("click", pollInbox);
  $("#cancel-poll").addEventListener("click", cancelPolling);
  $("#apply-failure").addEventListener("click", applyFailureMode);
  $("#copy-inbox").addEventListener("click", copyInboxAddress);
  $("#delete-inbox").addEventListener("click", deleteInbox);
  $("#load-arenas").addEventListener("click", loadArenas);
  $("#chat-input").addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") $("#chat-form").requestSubmit();
  });
  try {
    await api("/api/health");
    $("#server-status").textContent = "Local server online";
    await loadProviders();
    await loadConversations();
    await loadDashboard();
  } catch (error) {
    $("#server-status").textContent = "Connection failed";
    toast(error.message, true);
  }
}

initialize();
