# Phase 1 — Architecture and implementation plan

Status: architecture approved for incremental local-first implementation. This document preserves the existing design and defines acceptance boundaries for later phases. See `PROJECT_AUDIT.md` for the verified baseline.

## 1. Design goals and scope

- **Zero-credential first:** mock chat, persistence, local email simulation, and evaluations run offline.
- **Android friendly:** no mandatory pip packages, JavaScript build, containers, model weights, or external DB.
- **Preserve what works:** extend the existing Python API, vanilla frontend, SQLite database, and provider interfaces.
- **Explicit verification states:** implemented, automated-test passed, external-provider verified, configuration required, and externally unavailable are never conflated.
- **Honest learning:** prompts, memory, retrieval, datasets, evaluation, and fine-tuning are separate. No automatic weight-training claim.
- **Authorized automation only:** local demo and owned/approved test environments; no CAPTCHA or anti-abuse bypass.

Current scope remains a **single-user local application**. Multi-user/public deployment is blocked until authentication, authorization, tenant isolation, rate limiting, and deployment-specific persistence are implemented and verified.

## 2. Current system and data flow

```text
Android/desktop browser
  └── static HTML/CSS/JS, relative same-origin /api URLs
        └── app/api.py — threaded stdlib HTTP + JSON + static files
              ├── ChatService ── MemoryStore ── SQLite
              │       └── AIProvider.generate()
              ├── MockEmailProvider / MailTmProvider ── OTP parser
              ├── Evaluation runner ── JSON/Markdown
              ├── DesignArenaClient ── three documented GETs
              └── optional Playwright CLI (separate from web API)
```

### Chat sequence

1. The browser submits message and provider ID.
2. `ChatService` constructs the provider, failing early on missing configuration.
3. `MemoryStore` persists the user message and loads bounded recent history.
4. Local lexical ranking selects up to `MEMORY_RETRIEVAL_LIMIT` relevant memories.
5. The provider receives ordered history and system context.
6. Normalized text/model/usage returns and the assistant message is persisted.
7. API output includes retrieved memory records for inspection.

External request failure must not fabricate an assistant response or silently switch providers. Configuration failures happen before storing a partial turn; provider request failures may leave the user message for retry/history.

## 3. Persistence and migration decision

Existing tables: `conversations`, `messages`, and `memories`. SQLite remains appropriate for local-first use. Connections are short-lived, foreign keys are enabled, and WAL/busy timeout support the small threaded server.

Phase 2 will add a `schema_migrations` table and ordered, transactional migrations. Existing databases must be detected and preserved. Initial schema creation and upgrades will share one versioned path rather than dropping/recreating records.

Planned later entities, added only when their feature is implemented:

- `settings` for non-secret local preferences;
- `prompts` and `prompt_versions` with immutable version content;
- `datasets` and `dataset_records` with explicit approval metadata;
- `evaluation_runs` and `evaluation_results` with sanitized outputs;
- `test_runs` and `test_steps` with sanitized status/diagnostics.

Secrets and OTPs must not be stored in these tables. Inbox tokens and mock messages remain in process memory unless a later documented threat model justifies otherwise.

Indexes will follow actual lookup patterns. Deletion must use foreign keys or explicit transactional cleanup. Migration tests will start from the current three-table schema, insert representative records, migrate, and verify data preservation.

## 4. Provider contracts

### AI providers

Preserve `AIProvider.generate(messages, system_prompt) -> ChatResponse`. Add optional capabilities and connection testing without forcing every provider to support identical operations:

- provider/model identification;
- configuration validation and non-secret status;
- capabilities such as streaming/system prompts/usage;
- normalized error categories: missing/invalid credentials, network, unavailable, model, quota/rate limit, permission, unsupported;
- explicit connection test that performs no generation and no hidden paid fallback;
- normal generation remains mandatory; streaming is optional and feature-gated.

OpenAI, Anthropic, Gemini, compatible endpoints, and mock remain separate adapters. Model names come from backend configuration, not fabricated discovery responses. External generation requires an explicit user action and visible warning.

### Email providers

Extend the existing interface with capability reporting, inbox information, specific-message retrieval, health, and delete/expire where supported. Not every operation is mandatory for every provider; unsupported capabilities must be reported honestly.

The mock remains the only default web UI provider. Mail.tm remains optional, authorized-only, and never assumed to receive third-party OTPs.

### Browser automation

Preserve bounded Playwright actions and JSONL logs. Add visible-result waiting and sanitized diagnostics. The default E2E target will be this repository's own local registration demo, never Design Arena signup.

## 5. Memory and retrieval design

Current lexical retrieval scans at most 1,000 recent entries, ranks phrase/token coverage, and needs no embedding service. It is appropriate for explicit facts but not semantic synonym matching or enterprise scale.

Later changes must preserve user control:

- categories for preferences, project context, decisions, tasks, notes, summaries;
- explicit create/edit/delete/export operations;
- a non-secret setting to disable retrieval;
- sensitive-data rejection shared by automatic and manual creation;
- retrieval metadata and bounded context/truncation reporting;
- user/tenant keys only if multi-user authentication is later introduced.

Deleting a record means actual database deletion. Export must exclude secrets and OTPs by design. No conversation enters a dataset without an explicit approval action.

## 6. Learning and evaluation design

Prompt versions are immutable once created; editing a prompt creates a new version. Duplication creates a distinct prompt lineage. Comparison must show both prompt versions, outputs, metrics, and failures without automatically declaring a winner.

Datasets contain input, expected behavior/answer, optional criteria, tags, approval, and timestamps. Evaluation runs reference a dataset, provider/model, and prompt version. Results retain only sanitized outputs needed for review. Initial metrics remain transparent exact/contains/regex and JSON validity; human/rubric fields are optional and never converted into unexplained scores.

Fine-tuning is outside the verified milestone. A future implementation must use an official provider fine-tuning interface and separate live verification.

## 7. API and error design

Existing routes remain backward compatible. New logical groups may include `/api/prompts`, `/api/datasets`, `/api/evaluations`, `/api/tests`, `/api/logs`, and `/api/settings` only when backed by working services.

Validation covers JSON types, required fields, lengths, UUIDs, allowed operations, and provider configuration. Error responses will evolve to a consistent envelope containing stable `code`, safe `message`, optional `request_id`, and retry guidance. Existing `error` text can remain during migration for frontend compatibility.

Health checks remain cheap and local; they never call paid providers. Connection tests are separate explicit endpoints.

## 8. Frontend architecture

Preserve the same-origin vanilla JS application. Add views only with real backing APIs:

1. Dashboard — real health/count/recent-run data.
2. Chat — existing chat plus rename/delete/export and context status.
3. Memory Lab — existing memory plus edit/toggle/export.
4. Email Lab — clearly labeled local mock lifecycle and sanitized outcomes.
5. Providers — configured booleans, capabilities, explicit connection tests.
6. Prompt Library — CRUD/version/duplicate/export.
7. Evaluation Lab — datasets, runs, comparisons, reports.
8. Test Runs / Logs — local authorized runs and sanitized events.
9. Settings / Help — non-secret preferences and accurate documentation.

Mobile navigation should use a compact accessible menu rather than an ever-growing horizontal tab row. Controls require loading, empty, error, success, disabled, validation, and duplicate-submission handling. No fabricated metrics or inactive placeholder buttons.

## 9. Security architecture

- Environment/backend secret storage only; no key in frontend/localStorage/repository.
- Loopback by default. `0.0.0.0` only for a trusted preview/LAN.
- Configurable local rate limits for costly/sensitive operations; these supplement rather than bypass provider limits.
- Sanitized structured logs with request/run IDs, no message bodies, credentials, inbox tokens, or OTP values.
- Explicit retention documentation: SQLite persists until user deletion/reset; mock inbox data is process-lifetime; external retention follows the selected provider.
- Authentication/authorization and tenant isolation are prerequisites for untrusted deployment, not optional post-deploy polish.
- CI remains offline and secret-free for normal unit/integration/E2E tests.

## 10. External dependencies and verification boundary

| Dependency | Status | Verification approach |
|---|---|---|
| Python 3.11+ / SQLite | Required, already used | Unit + HTTP integration + migration tests |
| Vanilla browser APIs | Required | JavaScript syntax + HTTP + browser E2E when available |
| Playwright/Chromium | Optional, large | Install only in automation phase; local demo E2E |
| OpenAI/Anthropic/Gemini | Optional, credentials/possible charges | Mocked contract tests; live test only with owner credentials |
| mail.tm | Optional external test provider | Mocked API tests; live test only with authorization |
| Design Arena API | Optional approved read-only key | Mocked paths; live test only with approved key |
| Hosted database/server | Not selected | No deployment claim; evaluate current terms when chosen |

## 11. Ordered phase plan and acceptance criteria

Each phase requires a focused commit, regression suite, honest completion note, and clean failure handling.

### Phase 2 — Core backend

- **Files:** `app/database.py`, new migrations/service modules, `app/api.py`, validation tests.
- **Work:** versioned migrations, consistent errors, request IDs, input bounds, health/config status, local rate-limit foundation.
- **Automated acceptance:** legacy-schema upgrade preserves records; invalid inputs get stable safe errors; all prior API contracts pass.
- **Manual:** start server, inspect health, restart and confirm existing chat/memory remain.

### Phase 3 — Functional frontend

- **Files:** `static/`, backend read-only dashboard endpoints/tests.
- **Work:** responsive navigation, real dashboard, conversation rename/delete/export, provider/config status surfaces, complete form states.
- **Automated acceptance:** API interactions and JS syntax pass; controls have backing routes.
- **Manual:** narrow Android viewport, keyboard forms, long lists/logs, touch targets, empty/error states.

### Phase 4 — Email and OTP lab

- **Files:** `app/email/`, related APIs/UI, provider docs/tests.
- **Work:** capabilities/lifecycle, mock expiry/error/rate-limit simulation, configurable OTP context, HTML/ambiguity handling, cancellation and redaction.
- **Automated acceptance:** all master OTP cases, bounded polling, wrong context, sensitive redaction, no expired polling.
- **Manual:** complete local mock numeric/alphanumeric flows and failure simulations; no real third-party signup.

### Phase 5 — Authorized local browser E2E

- **Files:** local demo module/page, `app/automation/`, E2E config/tests/docs.
- **Work:** email continue → mock delivery → bounded wait → OTP submit → result; invalid/expired/retry/timeout/cleanup; sanitized report.
- **Automated acceptance:** unit/integration tests plus real Playwright local E2E if installation succeeds; otherwise mark browser execution unverified and keep unit results separate.
- **Manual:** run documented local demo and inspect sanitized run report.

### Phase 6 — AI provider hardening

- **Files:** `app/providers/`, chat/API/provider UI/tests.
- **Work:** capabilities, connection tests, normalized errors, model metadata/usage, bounded context reporting; optional streaming only if implemented end to end.
- **Automated acceptance:** every error category and adapter contract mocked; no silent paid fallback.
- **Manual:** offline mock chat; live provider checks only when owner supplies credentials.

### Phase 7 — Memory controls

- **Files:** `app/memory.py`, migrations/API/UI/tests/docs.
- **Work:** categories, editing, sensitive manual-entry checks, retrieval disable/export, context controls.
- **Automated acceptance:** save/update/delete/relevance/exclusion/sensitive/DB failures and single-user access boundaries.
- **Manual:** disable retrieval and confirm later mock/provider request contains no memory context.

### Phase 8 — Prompt, dataset, evaluation lab

- **Files:** new learning modules/migrations/API/UI, existing evaluation package/tests/docs.
- **Work:** prompt CRUD/version/duplicate/export, approved datasets, persistent sanitized runs, transparent comparison.
- **Automated acceptance:** immutable versions, dataset approval, run metrics/comparison/export, sensitive-output redaction.
- **Manual:** create two prompt versions, evaluate offline mock, inspect failures without claiming quality improvement.

### Phase 9 — Security review

- **Files:** all auth/rate-limit/log/retention boundaries and `docs/SECURITY_REVIEW.md`.
- **Work:** secret/OTP/log scans, rate-limit tests, deployment threat model, auth decision.
- **Acceptance:** no secrets in tracked files/logs; sensitive endpoints bounded; untrusted deployment remains blocked unless authz/authn and isolation pass.
- **Manual:** inspect responses/logs and attempt over-limit requests.

### Phase 10 — CI and deployment

- **Files:** workflows, deployment docs/report, only necessary config.
- **Work:** supported actions, syntax/tests/E2E/security checks, deployment readiness checklist.
- **Acceptance:** GitHub matrix and local E2E results reported exactly; hosted deployment only with explicit target authorization and persistent storage.
- **Manual:** fresh Android setup from README and health/restart checks.

### Phase 11 — Final QA

- **Files:** `docs/FINAL_QA_REPORT.md` and any regression fixes.
- **Work:** full unit/integration/E2E/syntax/build/security/docs/Git verification.
- **Acceptance:** exact counts/durations/failures/skips and provider status reported; unresolved features keep final status below “complete and verified.”

## 12. Unresolved questions and safe defaults

- **Public multi-user deployment?** Default no. Keep local single-user until the owner selects and authorizes a target.
- **Live paid provider testing?** Default no. Requires owner credentials, explicit request, and current quota/pricing review.
- **Real mail.tm/OTP testing?** Default no. Use mock; third-party OTP acceptance is not guaranteed.
- **Actual fine-tuning?** Not in current scope; requires a supported provider operation and separate verification.
- **Hosted PostgreSQL?** Not needed locally. Re-evaluate only with a concrete multi-user/hosting target.
- **Streaming?** Optional, only after normal provider/error behavior is hardened; never advertise unsupported streaming.

## 13. Phase 6 implementation status — 2026-11-09

The phase plan above remains the ordered roadmap. Phase 6 has now been implemented locally as follows:

- `AIProvider` retains `generate()` and adds opt-in `capabilities()` / `test_connection()` methods. Capabilities honestly report `streaming: false`; no SSE or incremental persistence path was added.
- `app/providers/factory.py` exposes a non-secret catalog with configured booleans, models, capability flags, and connection status. `app/providers/_http.py` categorizes upstream HTTP/network failures, carries retry metadata, and redacts known environment secrets.
- OpenAI-compatible, Anthropic, and Gemini adapters perform documented model `GET` connection tests; the mock performs a local check. None of those tests generate chat. External calls require explicit API/UI confirmation.
- `app/api.py` adds `POST /api/providers/test`, confirmation enforcement, categorized error responses, per-client rate limiting, persisted test results, and validated provider selection for conversation create/update/chat. There is no silent fallback to mock.
- Migration 2 adds persistent provider/model/usage/finish/truncation/bounded-context metadata and connection-test history. `ChatService` returns exact history/retrieval counts and flags omitted earlier history; assistant messages and exports retain safe metadata.
- The vanilla frontend adds a real Providers view, persistent model selection, connection-test controls, response metadata chips, and a bounded-context status line. JavaScript syntax and HTTP contracts are verified; a dedicated real-browser Providers flow is not yet present.
- Local verification: 98 offline tests passed, plus Python compilation and both JavaScript syntax checks. All external HTTP was mocked; no live provider verification is claimed.

Streaming remains the only Phase 6 task not implemented, intentionally reported as unsupported. Phases 7–11 remain outstanding, so the overall product status is still **partially implemented**, not “complete and verified.” See `PROVIDERS.md` for the exact contracts and verification boundary.
