"use strict";

const demoState = { inbox: null, session: null };
const demo$ = (selector) => document.querySelector(selector);
const demoParams = new URLSearchParams(window.location.search);
if (demoParams.get("scenario") === "expired") demo$("#demo-scenario").value = "expired";

async function demoAPI(path, options = {}) {
  const request = { ...options, headers: { "Content-Type": "application/json" } };
  if (request.body && typeof request.body !== "string") request.body = JSON.stringify(request.body);
  const response = await fetch(path, request);
  const data = await response.json().catch(() => ({ error: "Invalid demo response" }));
  if (!response.ok) throw new Error(data.error || `Demo request failed (${response.status})`);
  return data;
}

function demoStatus(title, detail) {
  const status = demo$("#demo-status");
  status.replaceChildren();
  const strong = document.createElement("strong");
  strong.textContent = title;
  const text = document.createElement("p");
  text.textContent = detail;
  status.append(strong, text);
}

function demoBusy(button, busy, busyLabel) {
  if (busy) { button.dataset.label = button.textContent; button.textContent = busyLabel; }
  else if (button.dataset.label) button.textContent = button.dataset.label;
  button.disabled = busy;
}

demo$("#create-demo-inbox").addEventListener("click", async () => {
  const button = demo$("#create-demo-inbox");
  demoBusy(button, true, "Creating…");
  try {
    demoState.inbox = await demoAPI("/api/email/mock/inboxes", { method: "POST", body: { ttl_seconds: 900 } });
    if (["timeout", "provider_error", "rate_limit"].includes(demoParams.get("failure"))) {
      await demoAPI(`/api/email/mock/inboxes/${encodeURIComponent(demoState.inbox.id)}/failure`, { method: "POST", body: { mode: demoParams.get("failure") } });
    }
    demo$("#email").value = demoState.inbox.address;
    demo$("#demo-continue").disabled = false;
    demoStatus("Inbox active", `${demoState.inbox.address} · process-local only`);
  } catch (error) { demoStatus("Inbox error", error.message); }
  finally { demoBusy(button, false); }
});

demo$("#demo-register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!demoState.inbox) return;
  const button = demo$("#demo-continue");
  demoBusy(button, true, "Sending…");
  try {
    demoState.session = await demoAPI("/api/demo/register", {
      method: "POST",
      body: { email: demo$("#email").value, inbox_id: demoState.inbox.id, scenario: demo$("#demo-scenario").value },
    });
    demo$("#demo-otp-form").hidden = false;
    demoStatus("Message simulated", "Retrieve the message from the mock inbox or test an invalid code.");
  } catch (error) { demoStatus("Registration error", error.message); }
  finally { demoBusy(button, false); }
});

demo$("#retrieve-otp").addEventListener("click", async () => {
  if (!demoState.session) return;
  const button = demo$("#retrieve-otp");
  demoBusy(button, true, "Polling…");
  try {
    const result = await demoAPI(`/api/email/mock/inboxes/${encodeURIComponent(demoState.inbox.id)}/poll`, {
      method: "POST",
      body: {
        timeout_seconds: 2,
        interval_seconds: 0.2,
        rules: { expected_length: 6, expected_application: "LLM-GYM Local Demo", expected_test_run: demoState.session.session_id },
      },
    });
    if (result.found) {
      demo$("#otp").value = result.code;
      demoStatus("OTP retrieved", "Code filled from the authorized mock message. Verify it or replace it to test failure.");
    } else {
      demoStatus(`Email ${result.status}`, result.error || "No usable code found.");
    }
  } catch (error) { demoStatus("Polling error", error.message); }
  finally { demoBusy(button, false); }
});

demo$("#demo-otp-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!demoState.session) return;
  const button = demo$("#verify-otp");
  demoBusy(button, true, "Verifying…");
  try {
    const result = await demoAPI(`/api/demo/sessions/${encodeURIComponent(demoState.session.session_id)}/verify`, {
      method: "POST", body: { code: demo$("#otp").value },
    });
    demoStatus(`Verification ${result.status}`, `${result.attempts_remaining} attempts remaining.`);
  } catch (error) { demoStatus("Verification error", error.message); }
  finally { demoBusy(button, false); }
});

demo$("#demo-reset").addEventListener("click", async () => {
  if (demoState.session) {
    try { await demoAPI(`/api/demo/sessions/${encodeURIComponent(demoState.session.session_id)}/cleanup`, { method: "POST", body: {} }); }
    catch (error) { demoStatus("Cleanup error", error.message); return; }
  } else if (demoState.inbox) {
    try { await demoAPI(`/api/email/mock/inboxes/${encodeURIComponent(demoState.inbox.id)}`, { method: "DELETE" }); }
    catch (error) { demoStatus("Cleanup error", error.message); return; }
  }
  window.location.reload();
});
