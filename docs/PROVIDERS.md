# AI provider contracts

Phase 6 extends the existing adapters without replacing the standard-library server, SQLite persistence, or the `AIProvider.generate()` contract. All provider credentials stay on the backend. The browser receives model names, booleans, capabilities, and safe error metadata—never a key.

## Verification states

| State | Meaning |
|---|---|
| Implemented, mocked-tested | Request/response contracts and error categories pass automated tests with mocked HTTP. |
| Configured | A required server-side key and, for custom endpoints, a base URL are present. This does **not** verify the key, model, billing, quota, or network. |
| Verified connection | An explicit, non-generation model-inspection request returned successfully. The result is saved in SQLite. |
| Failed connection | An explicit connection test returned a categorized failure. No chat generation was attempted. |
| Live provider verified | A separately authorized request with owner credentials was made and recorded. **No live GPT, Claude, Gemini, or custom provider verification has been performed in this repository.** |

The default offline suite makes no real external provider calls. A mocked adapter test is not evidence of live connectivity.

## Catalog and capabilities

`GET /api/providers` returns:

```json
{
  "default": "mock",
  "streaming": false,
  "providers": [
    {
      "id": "mock",
      "label": "Offline mock",
      "configured": true,
      "model": "mock-1",
      "external": false,
      "connection_status": "not_tested",
      "capabilities": {
        "chat": true,
        "system_prompt": true,
        "usage": true,
        "streaming": false,
        "connection_test": "local"
      }
    }
  ]
}
```

`connection_status` and `last_test` come from the most recent saved connection test. `configured` means server configuration is present, not that it is valid. Capabilities currently advertise non-streaming chat, system-prompt support, a normalized usage field, and either a local or model-`GET` connection test.

**Streaming is not implemented.** There is no server-sent event endpoint, token-by-token UI, cancellation of an in-flight generation, or partial-response persistence. A response is saved only after the provider returns a complete result. The UI and API report `streaming: false` rather than showing a placeholder control. This is the one Phase 6 task intentionally left as an explicit unsupported capability; Phase 7+ can add it only end to end and behind a real feature check.

## Model selection

- `POST /api/conversations` accepts an optional `provider`. The conversation stores the normalized provider ID and its configured model.
- `PATCH /api/conversations/{id}` accepts `title` and/or `provider`. Selecting a provider in the UI persists that choice before the next message.
- `POST /api/conversations/{id}/messages` accepts an optional `provider` for an individual turn.
- Unknown or unconfigured providers are rejected before a message is saved. A missing external key never silently falls back to the mock.

The configured models come from `OPENAI_MODEL`, `ANTHROPIC_MODEL`, `GEMINI_MODEL`, and `OPENAI_COMPATIBLE_MODEL`. Those names are examples in `.env.example`, not promises of availability. Check the current provider documentation, account access, pricing, and quotas before a live request.

## Explicit connection tests

`POST /api/providers/test` is separate from health checks and chat. External tests require `{"confirm_external": true}`; without it, the API returns `409 EXTERNAL_CONFIRMATION_REQUIRED` and makes no external request. The endpoint is rate-limited in its own per-client bucket.

```bash
curl -X POST http://127.0.0.1:8000/api/providers/test \
  -H 'Content-Type: application/json' \
  -d '{"provider":"mock"}'

curl -X POST http://127.0.0.1:8000/api/providers/test \
  -H 'Content-Type: application/json' \
  -d '{"provider":"openai","confirm_external":true}'
```

Documented model-inspection operations:

| Provider | Connection test |
|---|---|
| Mock | Local capability check; no network. |
| OpenAI / OpenAI-compatible | `GET {base_url}/models/{model}` with `Authorization: Bearer …`. |
| Anthropic | `GET /v1/models/{model}` with `x-api-key` and `anthropic-version`. |
| Gemini | `GET /v1beta/models/{model}` with `x-goog-api-key`. |

These are `GET` requests with no chat payload. They never call `/chat/completions`, `/messages`, or `:generateContent`. A custom OpenAI-compatible service must actually implement the documented model-retrieval endpoint; a failed `model-get` does not prove that its chat endpoint is broken. Model-inspection requests can still be subject to provider authentication, quota, and terms.

Successful and failed test statuses, model names, timestamps, and safe categories are stored in `connection_tests`. The response contains no secret values. The catalog is read-only and does not expose a key entry form or allow a browser-specified endpoint.

## Normalized generation metadata

`ChatResponse` carries `content`, `model`, `usage`, `truncated`, and `finish_reason`. Adapters normalize input/output token names where the provider reports them:

- OpenAI-compatible: `prompt_tokens` → `input_tokens`, `completion_tokens` → `output_tokens`; `finish_reason: "length"` is truncation.
- Anthropic: `input_tokens`/`output_tokens`; `stop_reason: "max_tokens"` is truncation.
- Gemini: `promptTokenCount` → `input_tokens`, `candidatesTokenCount` → `output_tokens`; `finishReason: "MAX_TOKENS"` is truncation.
- Mock: reports `input_messages` only. It does not invent token counts; the UI says “Tokens not reported.”

Each assistant message persists model, token counts, output truncation, finish reason, number of supplied history messages, whether earlier history was omitted, and number of retrieved memories. Chat responses also return a `context` object with the exact history/retrieval limits and counts:

```json
{
  "streaming": false,
  "context": {
    "history_limit": 20,
    "history_messages": 4,
    "history_truncated": false,
    "retrieval_limit": 4,
    "retrieved_memories": 1
  }
}
```

`CHAT_HISTORY_LIMIT` bounds messages supplied to the provider; `MEMORY_RETRIEVAL_LIMIT` bounds retrieved memories. The UI distinguishes **output truncation** from **earlier history omitted**. JSON and Markdown conversation exports include the safe metadata.

## Error normalization

Provider failures are categorized before they reach the API. Upstream detail is bounded to 500 characters and any known environment secret is redacted. Codes use the `PROVIDER_{CATEGORY}` form.

| Category | Typical meaning | API status | Retryable |
|---|---|---:|---|
| `missing_key`, `missing_configuration` | Required server configuration absent | 400 | No |
| `unsupported_operation`, `invalid_request` | Unknown provider, insecure custom URL, bad request | 400 | No |
| `rate_limit` | HTTP 429 or equivalent quota condition | 429 | Yes; `Retry-After` when supplied |
| `invalid_key` | Upstream HTTP 401 | 502 | No |
| `permission_denied` | Upstream HTTP 403 | 502 | No |
| `model_unavailable` | Upstream HTTP 404 | 502 | No |
| `network` | Timeout, connection error, HTTP 408/409/425 | 502 | Yes |
| `upstream_unavailable` | Upstream HTTP 5xx | 502 | Yes |

Errors retain the existing `error`, `code`, `message`, `request_id`, and `retryable` envelope. Provider request failures do not fabricate assistant text. Configuration failures occur before a partial user turn is stored; transport failures after a user turn may leave that turn for a deliberate retry.

## Local verification

On **2026-11-09**, these checks passed on the working branch:

```text
python3 -m compileall -q app tests run.py
node --check static/app.js
node --check static/demo.js
python3 -m unittest discover -s tests -v
→ Ran 98 tests in 8.008s, OK
```

The suite covers all adapter contracts, all documented model `GET` tests, every HTTP error category, secret redaction, no silent fallback, confirmation, persistence, local/external test separation, normalized usage/truncation, model selection, context reporting, and export metadata. External HTTP is mocked. A real-browser interaction with the new Providers view is not yet part of those 98 tests; the HTTP frontend and JavaScript syntax are checked separately.

## Owner-authorized live check

1. Set one provider key/model in the backend `.env` and restart.
2. Review the provider's current model documentation, access, pricing, and quota.
3. Open **Providers** and choose **Test external connection**, or call the test endpoint with explicit confirmation.
4. Record provider, model, UTC time, result, and any quota limitation.
5. If desired, send one small chat message. Do not confuse a successful model `GET` with a successful generation.

No live provider check, paid generation, streaming connection, or public deployment is claimed here.
