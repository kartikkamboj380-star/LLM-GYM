# Phase 0 — Repository audit

Audit date: **2026-11-09**. This audit covers the actual GitHub repository and the existing implementation, not the original one-line initial commit.

## 1. Repository identity and state

| Item | Observed value |
|---|---|
| Repository | `kartikkamboj380-star/LLM-GYM` |
| URL | https://github.com/kartikkamboj380-star/LLM-GYM |
| Visibility | Public (`isPrivate: false`) |
| Default branch | `main` |
| Working branch | `arena/f5937fd2-llm-gym` |
| Remote working branch | Present and synchronized before this audit |
| Audited commit | `dd759b5980f9640b9a47784ce8b5d203ab291fea` |
| Initial commit | `b3bcbb8` (one-line README) |
| Tags/releases | No tags found |
| Working tree | Clean before this report |
| Existing workflows | `.github/workflows/ci.yml` only |
| Deployment manifests | None |
| Formatter/linter/type-checker configuration | None |

The existing implementation is preserved. No reset, force-push, branch switch, or deletion of working source was performed.

## 2. Existing architecture and reusable code

The project is a small Python 3.11+ standard-library application. `run.py` starts a threaded same-origin HTTP server. `app/api.py` serves JSON endpoints and the vanilla HTML/CSS/JavaScript frontend in `static/`. SQLite connections are short-lived and use foreign keys, WAL mode, and a busy timeout.

Reusable modules:

- `app/chat.py`: history → retrieval → selected provider → persistence.
- `app/database.py`, `app/memory.py`: conversations, messages, memories, lexical search, conservative extraction.
- `app/providers/`: mock, OpenAI, Anthropic, Gemini, and OpenAI-compatible adapters with server-side credentials.
- `app/email/`: provider interface, contextual code parser, local mock, optional mail.tm adapter.
- `app/automation/browser.py`: optional Playwright visible-element waits, fill/click actions, bounded retries, JSONL logs.
- `app/designarena/client.py`: three documented read-only GET operations only.
- `app/evaluation/`: JSON datasets, exact/contains/regex metrics, provider comparison, JSON/Markdown reports.
- `tests/`: unit tests and real local HTTP integration tests using temporary databases.

There is no technical reason to replace the backend framework, SQLite, or frontend architecture for the current single-user Android-first scope.

## 3. Current API and schema

Existing API groups:

- `/api/health`, `/api/providers`
- `/api/conversations`, `/api/conversations/{id}`, `/api/conversations/{id}/messages`
- `/api/memory`, `/api/memory/extract`, `/api/memory/{id}`
- `/api/email/mock/inboxes`, `/messages`, `/demo`, `/poll`
- `/api/designarena/arenas`, `/models`, `/leaderboard`

Existing tables are `conversations`, `messages`, and `memories`. Foreign keys and chronological indexes exist. Schema creation is idempotent, but there is **no versioned migration table or migration runner**.

## 4. Feature status audit

Statuses deliberately distinguish implementation, automated verification, and real external verification.

| Area | Implemented and automatically tested | Partial / missing | Real external verification |
|---|---|---|---|
| Chat | Create/list/get, send, provider selection, persistence, errors | Rename, delete, export, truncation metadata, streaming, cancellation absent | No paid provider request made |
| Memory | Add/search/rank/retrieve/extract/delete, persistence | Categories, edit, retrieval toggle, export, multi-user isolation absent | Local only |
| Mock email | Inbox/message simulation, bounded polling, numeric/mixed codes | Expiration, failure/rate-limit simulation, lifecycle/capabilities, cancellation absent | Intentionally local; no real email |
| mail.tm | Documented account/token/message flow with mocked HTTP tests | Capabilities/lifecycle UI and live verification absent | Not tested against mail.tm |
| OTP parser | Contextual plain-text numeric and mixed codes | HTML, ambiguity, configurable filters/rules, expiry, redaction reports incomplete | No third-party OTP used |
| AI providers | Request/response formats and missing-key behavior unit-tested | Connection tests, normalized error categories, capabilities, streaming absent | No credentials configured or calls made |
| Automation | Config validation and logs tested; optional runner implemented | Local registration demo, visible-result actions, sanitized screenshots, end-to-end flow absent | No browser launch performed |
| Evaluation | CLI dataset loading, scoring, comparison, reports tested | Persistent datasets/runs, prompt library/versioning, web UI, human/rubric metrics absent | Mock evaluation executed |
| Design Arena | Official read-only client paths unit-tested | No approved-key UI result beyond arenas request | No API-key request made |
| Frontend | Four functional sections, mobile CSS, loading/empty/error states | Dashboard, Providers, Prompts, Evaluation, Runs, Logs, Settings, Help absent | HTTP frontend verified; no real-device browser audit |
| Backend | Validation basics, safe generic 500, health/database status | Consistent coded errors, auth, rate limits, request IDs, run/log/settings APIs absent | Local preview only |
| CI | Syntax plus 48 offline tests on Python 3.11/3.12 | No configured lint/type/security scans or browser E2E | Latest GitHub run passed |

## 5. Baseline execution

No dependency installation was necessary: `requirements.txt` contains no mandatory third-party packages. Playwright was deliberately not installed during this lightweight baseline.

Commands actually run:

```bash
python -m compileall -q app tests run.py
python -m unittest discover -s tests -v
node --check static/app.js
# Against the already running local server:
GET http://127.0.0.1:8000/api/health
GET http://127.0.0.1:8000/api/providers
GET http://127.0.0.1:8000/
```

Baseline result:

- Python compilation: **passed**.
- Tests: **48 run, 48 passed, 0 failed, 0 skipped**, approximately **2.720 seconds**.
- JavaScript syntax: **passed** with Node `v22.22.3` (Node is not an app dependency).
- Health: **HTTP 200**, application `ok`, database `true`, version `0.1.0`.
- Providers endpoint: **HTTP 200**; only mock configured, no secret values returned.
- Frontend: **HTTP 200**, 8,792 response bytes.
- Local Python: **3.11.2**.
- GitHub CI run `42620868787`: **success on both matrix jobs** at commit `dd759b5`.

No lint or type-check command was run because no such configuration exists; this is recorded as missing tooling rather than a pass. Warnings from the earlier successful CI run concern deprecated Node 20 action runners and the future `ubuntu-latest` migration; they do not currently fail tests.

## 6. Security and privacy findings

### Existing controls

- `.env`, databases, key files, logs, and reports are Git-ignored.
- Provider credentials remain server-side; provider status exposes booleans only.
- Remote custom AI endpoints require HTTPS except loopback.
- Static responses use a restrictive CSP, no-store, nosniff, and no-referrer headers.
- API errors do not intentionally return stack traces.
- Browser fill values are not logged; OTP/email content is not written to permanent application logs.
- Design Arena integration has no arbitrary endpoint or write operation.

### Gaps and risks

1. The app has no authentication, authorization, per-user isolation, or rate limiting. It must remain single-user loopback/trusted-preview only until those controls exist.
2. Binding to `0.0.0.0` makes the unauthenticated API reachable in that environment; a public deployment is not safe.
3. API errors lack stable codes/request IDs, and provider failures are all mapped to HTTP 502 without distinguishing quota, permission, network, or model errors.
4. Manual memory entry accepts arbitrary text. Automatic extraction rejects common credential phrases but is not a complete data-loss-prevention mechanism.
5. Mock OTPs and full mock messages are returned to the local UI and held in process memory. Future exports/reports must redact them explicitly.
6. Schema changes currently have no transactional versioned migration strategy or migration-preservation tests.
7. Conversation/message records do not retain normalized model/usage metadata or context-truncation details.
8. CI warnings should be resolved by moving to supported action versions after confirming compatibility.

## 7. Dependencies

### Unnecessary dependencies

No mandatory third-party runtime dependency exists, so none needs removal. There is no Docker, Node build chain, ORM, vector DB, or frontend framework to prune.

### Missing dependencies

No package is required for the next backend/docs phases. Playwright remains optional and should be installed only for the authorized browser phase. Adding a linter/type checker should be weighed against Android storage; standard-library checks can remain the default.

## 8. Required modifications and new work

Preserve existing files and APIs while incrementally adding:

1. Versioned SQLite migrations and migration tests.
2. Consistent validation/error envelopes and configurable local rate limits.
3. Conversation rename/delete/export and memory edit/toggle/export.
4. Provider capabilities and explicit connection-test endpoints.
5. Expanded mock lifecycle, OTP rules/ambiguity/HTML handling, cancellation and sanitization.
6. A completely local registration demo plus authorized E2E runner.
7. Prompt/version, dataset, evaluation-run, and sanitized report persistence.
8. Dashboard and functional lab/settings/log/help sections using real API data.
9. Authentication/authorization before any untrusted deployment; no premature public-hosting claim.
10. Dedicated API/provider/email/memory/testing/troubleshooting documentation and final QA reports.

## 9. Audit conclusion

The repository has a useful, tested foundation, not a superficial demo. It is **partially implemented relative to the master prompt**. The core chat/memory/mock-email milestone is reusable and healthy. The largest missing product areas are prompt/dataset management, full evaluation persistence/UI, local browser E2E, lifecycle/security controls, and dashboard/settings surfaces. External-provider functionality remains implemented-but-not-live-verified.
