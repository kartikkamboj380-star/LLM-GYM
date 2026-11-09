# Authorized browser automation and local registration E2E

## Safety boundary

The only built-in end-to-end target is `/demo`, owned by this repository and served on loopback. It is independent of Design Arena and every other third-party signup system. No CAPTCHA, anti-bot evasion, mass signup, identity impersonation, or rate-limit bypass is implemented.

## Local demo flow

1. Start `python run.py` and open `http://127.0.0.1:8000/demo`.
2. Create a mock inbox. Its reserved `.test` address fills the email field.
3. Continue to simulate registration and message delivery.
4. Retrieve the message through bounded polling with application/run context filters.
5. Verify the OTP, or replace it to test invalid/retry behavior.
6. Choose the expired scenario before Continue to test expiration.
7. Select **Clean up and start over** to delete the session and ephemeral inbox.

Registration responses never contain the OTP. Sessions and codes are process-local. Verification allows three attempts, uses constant-time code comparison, clears the stored code on success/expiry, and reports invalid/failed/expired/verified states. The email must match the selected mock inbox.

## Playwright runner

Optional installation:

```bash
python -m pip install -r requirements-automation.txt
playwright install chromium
```

Run against the already running local app:

```bash
python -m app.automation.browser examples/local-demo-e2e.json --log data/browser-run.jsonl
```

Or run against a fresh temporary database/server managed by the E2E harness:

```bash
python -m app.automation.local_e2e examples/local-demo-e2e.json --log data/browser-run.jsonl
```

Additional required CI flows:

```bash
python -m app.automation.local_e2e examples/local-demo-invalid-retry-e2e.json
python -m app.automation.local_e2e examples/local-demo-expired-e2e.json
python -m app.automation.local_e2e examples/local-demo-timeout-e2e.json
```

The isolated harness uses a deterministic OTP only for its temporary test server, making the invalid value unambiguous. The normal app generates random codes.

## Readiness and diagnostics

Supported actions are `wait_for`, `fill`, `click`, `wait_for_text`, and `wait_for_value`. Every locator first waits for visibility. Assertions use Playwright `expect` for status text/value rather than arbitrary fixed UI delays. Sleep is limited to exponential backoff after an action failure. Timeouts and retries are bounded.

Logs contain timestamps, action types, selectors, attempt numbers, and exception classes. Fill values, OTPs, message bodies, tokens, and screenshots containing private content are not logged. The demo cleanup action deletes session/inbox data; the harness also shuts down its temporary server/database.

## Verification status

HTTP integration tests cover valid delivery, invalid retry, expiration, mismatched email, and cleanup. The separate GitHub `browser-e2e` job is required to install Chromium and execute all four browser configurations; it is not an optional skipped test. Local sandbox Python package installation succeeded, but Chromium download from `cdn.playwright.dev` failed due to the sandbox network boundary, so local browser execution is not claimed. Check the latest CI run for the actual remote browser result.
