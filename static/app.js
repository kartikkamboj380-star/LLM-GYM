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
  if (name === "memory") loadMemories();
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

async function createInbox() {
  const button = $("#create-inbox");
  busy(button, true);
  try {
    const inbox = await api("/api/email/mock/inboxes", { method: "POST", body: {} });
    state.inboxId = inbox.id;
    $("#inbox-address").textContent = inbox.address;
    $("#send-demo").disabled = false;
    $("#poll-inbox").disabled = false;
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
    await api(`/api/email/mock/inboxes/${encodeURIComponent(state.inboxId)}/demo`, { method: "POST", body: { code_type: $("#code-type").value } });
    toast("Demo message injected locally. Check the inbox to parse it.");
    $("#verification-result").innerHTML = "<span>Message delivered</span><p>Run the parser to detect its code.</p>";
  } catch (error) { toast(error.message, true); }
}

async function pollInbox() {
  if (!state.inboxId) return;
  const button = $("#poll-inbox");
  busy(button, true, "Checking…");
  try {
    const result = await api(`/api/email/mock/inboxes/${encodeURIComponent(state.inboxId)}/poll`, { method: "POST", body: { timeout_seconds: 0, interval_seconds: 1 } });
    const resultBox = $("#verification-result");
    resultBox.replaceChildren();
    const status = document.createElement("span");
    status.textContent = result.found ? "Code verified" : "No code found";
    const code = document.createElement("strong");
    code.className = "parsed-code";
    code.textContent = result.found ? result.code : "—";
    const detail = document.createElement("p");
    detail.textContent = result.found ? "Parsed from an authorized mock message." : "Inject a demo message, then try again.";
    resultBox.append(status, code, detail);
    renderEmails(result.messages);
  } catch (error) { toast(error.message, true); }
  finally { busy(button, false); }
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
  $("#chat-form").addEventListener("submit", sendMessage);
  $("#provider-select").addEventListener("change", updateProviderNote);
  $("#extract-memory").addEventListener("click", extractMemories);
  $("#memory-form").addEventListener("submit", saveMemory);
  $("#memory-search-form").addEventListener("submit", (event) => { event.preventDefault(); loadMemories($("#memory-search").value).catch((error) => toast(error.message, true)); });
  $("#create-inbox").addEventListener("click", createInbox);
  $("#send-demo").addEventListener("click", sendDemo);
  $("#poll-inbox").addEventListener("click", pollInbox);
  $("#load-arenas").addEventListener("click", loadArenas);
  $("#chat-input").addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") $("#chat-form").requestSubmit();
  });
  try {
    await api("/api/health");
    $("#server-status").textContent = "Local server online";
    await loadProviders();
    await loadConversations();
  } catch (error) {
    $("#server-status").textContent = "Connection failed";
    toast(error.message, true);
  }
}

initialize();
