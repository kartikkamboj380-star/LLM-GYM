# Email Testing Lab and OTP safety

## Scope

The default **Mock Inbox — Local Testing Only** uses the reserved `.test` domain. It creates no external account and sends no internet email. Inboxes/messages/OTPs live in process memory and disappear on restart or deletion. Do not connect this workflow to Design Arena or use it to bypass third-party account limits.

## Implemented mock capabilities

- Random or validated predictable local addresses.
- Created/active/waiting/message-received/expired/deleted lifecycle.
- Configurable inbox TTL (0–86400 seconds) and per-message TTL.
- Text/HTML delivery simulation and specific-message retrieval.
- Numeric (4–8 digit) and mixed alphanumeric (6–10 character) contextual codes.
- Expected length/characters, sender, subject, maximum age, application, and test-run filters.
- Duplicate-value handling; distinct candidates produce `ambiguous`, never arbitrary selection.
- Bounded timeout, interval, exponential backoff, and cooperative cancellation.
- Explicit `verified`, `not_found`, `timeout`, `expired`, `ambiguous`, and `cancelled` outcomes.
- Provider-error, rate-limit, and timeout simulation.
- Capabilities, health, inbox information, and deletion.
- Sanitized poll reports containing metadata and `code_detected`, never OTP/message bodies.

Expired inboxes stop before the first polling attempt. Expired messages are considered expired only when they contain a matching code; unrelated old newsletters do not block polling. Expected application/run/sender/subject filters are applied before accepting a code.

## Main API additions

- `GET /api/email/mock/capabilities`, `/health`
- `GET/DELETE /api/email/mock/inboxes/{id}`
- `GET /api/email/mock/inboxes/{id}/messages/{message_id}`
- `POST /api/email/mock/inboxes/{id}/failure` with `mode`
- `POST /api/email/mock/inboxes/{id}/cancel`
- Existing create/messages/demo/poll routes now accept validated TTL, HTML, backoff, and OTP rules where applicable.

The web UI exposes TTL, HTML delivery, timeout/interval/backoff, common OTP filters, failure simulation, cancellation, copy, and deletion. OTP display is for the current authorized local test only.

## Mail.tm documentation review

Official sources reviewed on **2026-11-09**:

- [Mail.tm API introduction](https://docs.mail.tm/)
- [Account operations](https://docs.mail.tm/api/accounts)
- [OpenAPI specification linked by the official docs](https://api.mail.tm/)

The docs show `GET /domains`, `POST /accounts`, `POST /token`, bearer-authenticated `GET /messages` and `/messages/{id}`, `GET /me`, and `DELETE /accounts/{id}`. They describe an **8 QPS general per-IP quota**, no API key for initial account creation, and attribution/terms requirements. The adapter uses these documented routes and keeps generated passwords/tokens out of returned inbox models and logs.

Mail.tm support remains optional and authorized-only:

- no live account was created or tested by this project;
- no claim is made that third-party websites accept mail.tm addresses or deliver OTPs;
- account IDs, tokens, and local inbox IDs are process-local;
- provider expiration is not inferred or fabricated;
- polling defaults are conservative, and callers must respect the current 8-QPS quota and terms;
- deletion uses the documented remote account ID and cannot be restored;
- external health checks are explicit operations, never part of the cheap app health endpoint.

Read the current provider documentation and privacy/retention terms before any live test. Do not mass-create accounts, resell/proxy the API, or use it for illegal/unauthorized activity.

## OTP data handling

OTPs are sensitive authentication data. The app does not persist them in SQLite, source, CI artifacts, analytics, or request logs. `sanitize_poll_result()` removes code and body fields. `VerificationCodeParser.redact()` replaces contextual codes in free-text reports. Authorized poll responses still contain the code and mock messages so the local UI can complete its test; protect those responses and do not share them publicly.
