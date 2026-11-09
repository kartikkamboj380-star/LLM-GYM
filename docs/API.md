# Backend API conventions

The endpoint summary is in `README.md`; provider-specific contracts are in `PROVIDERS.md`. This document covers shared API behavior and the Phase 2/6 additions.

## Request and response metadata

Every HTTP response includes an `X-Request-ID` header. Clients should include this value when reporting a problem. Request logs contain method, normalized path without query parameters, status, client address, and request ID; message bodies, memory search queries, credentials, and OTPs are not logged.

Successful responses retain their existing JSON shapes. Error responses retain the original `error` string for compatibility and add stable fields:

```json
{
  "error": "Conversation not found",
  "code": "NOT_FOUND",
  "message": "Conversation not found",
  "request_id": "request identifier",
  "retryable": false
}
```

General categories include `VALIDATION_ERROR` (400), `NOT_FOUND` (404), `RATE_LIMITED` (429), `EXTERNAL_CONFIRMATION_REQUIRED` (409), and `INTERNAL_ERROR` (500). Provider failures use `PROVIDER_{CATEGORY}` codes:

| API code | Status | Retryable | Cause |
|---|---:|---|---|
| `PROVIDER_MISSING_KEY`, `PROVIDER_MISSING_CONFIGURATION` | 400 | No | Required server configuration is absent. |
| `PROVIDER_UNSUPPORTED_OPERATION`, `PROVIDER_INVALID_REQUEST` | 400 | No | Unknown provider, insecure custom URL, or bad local request. |
| `PROVIDER_RATE_LIMIT` | 429 | Yes | Upstream HTTP 429; `Retry-After` is forwarded when supplied. |
| `PROVIDER_INVALID_KEY`, `PROVIDER_PERMISSION_DENIED`, `PROVIDER_MODEL_UNAVAILABLE` | 502 | No | Upstream 401, 403, or 404. |
| `PROVIDER_NETWORK`, `PROVIDER_UPSTREAM_UNAVAILABLE` | 502 | Yes | Timeout/network failure or upstream 5xx. |

Rate-limited responses also include `retry_after_seconds` and a `Retry-After` header. Upstream error text is bounded and known environment secrets are redacted. Stack traces are not returned to clients.

## Provider catalog and connection tests

`GET /api/providers` returns the default ID, `streaming: false`, and a non-secret catalog. Each item contains `id`, `label`, `configured`, `model`, `external`, `connection_status`, optional `last_test`, and `capabilities`. `configured` reports the presence of server-side configuration, not its validity. No key value is returned.

`POST /api/providers/test` accepts:

```json
{"provider": "openai", "confirm_external": true}
```

External providers require `confirm_external: true`; otherwise the response is `409 EXTERNAL_CONFIRMATION_REQUIRED` with no external request. Tests use a documented model `GET`, never a chat generation. The mock performs a local check. Results are persisted in `connection_tests` and surfaced by the catalog. The endpoint has its own per-client rate-limit bucket using the configured sensitive-operation limit.

Provider selection is validated before persistence. `POST /api/conversations`, `PATCH /api/conversations/{id}`, and `POST /api/conversations/{id}/messages` accept a known, configured `provider`; unconfigured external choices are rejected with `PROVIDER_MISSING_CONFIGURATION`. There is no silent fallback to the mock.

## Chat response metadata

A successful chat response includes `model`, normalized `usage`, `truncated`, `finish_reason`, `streaming: false`, `retrieved_memories`, and `context`. `context` reports exact `history_limit`, `history_messages`, `history_truncated`, `retrieval_limit`, and `retrieved_memories`. Assistant messages and conversation exports retain model, token counts where reported, output truncation, finish reason, supplied-history count, earlier-history omission, and retrieved-memory count.

Streaming is not implemented; there is no partial-response endpoint. A response is persisted after the provider returns a complete result.

## Dashboard and conversation management

`GET /api/dashboard` returns current application/database status, real conversation/message/memory counts, non-secret provider configuration, recent conversations, and empty evaluation/test-run lists until persistent run storage is implemented. It does not invent activity.

Conversations can be renamed and their selected provider/model changed with `PATCH /api/conversations/{id}` and `{"title":"New title","provider":"mock"}`. Either field may be supplied alone. Deletion uses `DELETE`; JSON/Markdown exports use `GET /api/conversations/{id}/export?format=json` or `format=markdown`. Deletion cascades to messages; sourced memories remain with their source references cleared.

## Validation

JSON bodies must be objects no larger than 1 MB. Text fields must actually be strings rather than coerced arrays/objects. Polling timeout/interval fields must be numbers, with provider-level range checks. Conversation content, memory content, tags, and provider selection retain their existing length/type rules. `confirm_external` must be a boolean; a missing value means no external confirmation.

## Health

`GET /api/health` performs only cheap local checks. It reports application/database status, schema version, app version, non-secret provider configuration booleans, mock email availability, and the local rate-limit window. It never tests an external provider or exposes a key. The current schema version is 2.

## Local rate limits

The in-memory limiter uses client address plus operation bucket. Configure:

```dotenv
RATE_LIMIT_WINDOW_SECONDS=60
CHAT_RATE_LIMIT_REQUESTS=30
EMAIL_RATE_LIMIT_REQUESTS=30
```

Limits cover chat turns, provider connection tests, mock inbox creation, demo delivery, and polling. Each operation has its own bucket; the provider-test bucket currently shares the numeric `EMAIL_RATE_LIMIT_REQUESTS` setting. These limits complement provider quotas and prevent accidental tight loops; they do not authorize bypassing an external limit and do not replace public authentication or a distributed production limiter.

## Schema migrations

`schema_migrations` records ordered migrations. Version 1 is the original conversations/messages/memories schema. Version 2 adds conversation provider/model, message model/token/output-truncation/finish/context metadata, and connection-test history. Complete pre-migration 0.1 databases are baselined without rebuilding records. A partial legacy schema stops startup rather than risking data loss. Each new migration runs in an immediate transaction and rolls back all statements on failure.
