# Backend API conventions

The existing endpoint summary is in `README.md`. This document covers shared API behavior added in Phase 2.

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

Current categories include `VALIDATION_ERROR` (400), `NOT_FOUND` (404), `RATE_LIMITED` (429), `PROVIDER_ERROR` (502), and `INTERNAL_ERROR` (500). Rate-limited responses also include `retry_after_seconds`, `retryable: true`, and a `Retry-After` header. Stack traces are not returned to clients.

## Validation

JSON bodies must be objects no larger than 1 MB. Text fields must actually be strings rather than coerced arrays/objects. Polling timeout/interval fields must be numbers, with provider-level range checks. Conversation content, memory content, tags, and provider selection retain their existing length/type rules.

## Health

`GET /api/health` performs only cheap local checks. It reports application/database status, schema version, app version, non-secret provider configuration booleans, mock email availability, and the local rate-limit window. It never tests an external provider or exposes a key.

## Local rate limits

The in-memory limiter uses client address plus operation bucket. Configure:

```dotenv
RATE_LIMIT_WINDOW_SECONDS=60
CHAT_RATE_LIMIT_REQUESTS=30
EMAIL_RATE_LIMIT_REQUESTS=30
```

Limits cover chat turns, mock inbox creation, demo delivery, and polling. They complement provider quotas and prevent accidental tight loops; they do not authorize bypassing an external limit and do not replace public authentication or a distributed production limiter.

## Schema migrations

`schema_migrations` records ordered migrations. Version 1 is the original conversations/messages/memories schema. Complete pre-migration 0.1 databases are baselined without rebuilding records. A partial legacy schema stops startup rather than risking data loss. Each new migration runs in an immediate transaction and rolls back all statements on failure.
