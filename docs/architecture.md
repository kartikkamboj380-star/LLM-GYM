# Architecture and data flow

## Design goals

- Zero-credential first: the mock provider and all persistence run offline.
- Phone friendly: no mandatory pip packages, JavaScript build, containers, or external DB.
- Modular: providers implement one small interface; infrastructure does not leak into the frontend.
- Honest boundaries: retrieval is not training, mocks are not external delivery, and documented APIs only.

## Chat sequence

1. Browser sends message and provider ID to the same-origin Python API.
2. `ChatService` constructs the selected provider, failing early if credentials/config are absent.
3. `MemoryStore` persists the user message and reads recent conversation history.
4. The store tokenizes the new message, removes common stop words, and ranks matching memories using phrase/token coverage and bounded frequency boosts.
5. `ChatService` places up to `MEMORY_RETRIEVAL_LIMIT` entries in system context. Recent history is capped by `CHAT_HISTORY_LIMIT`.
6. The provider adapter returns normalized text/model/usage.
7. The assistant message is persisted. API output includes the actual retrieved memory records for inspection.

If the external request fails, the user's message may remain as conversation history but no fabricated assistant response is stored. Configuration failures happen before the user message is saved.

## Persistence

`conversations` and `messages` have foreign keys and chronological indexes. `memories` optionally references the exact source conversation/message. SQLite foreign keys, WAL journaling, busy timeout, and short-lived connections support the small threaded HTTP server without sharing connections across threads.

The database is a local file. This milestone has no migrations beyond idempotent `CREATE TABLE/INDEX IF NOT EXISTS`, no multi-user tenancy, and no distributed concurrency support.

## Search trade-off

The initial knowledge base scans at most 1,000 recent entries and uses deterministic lexical ranking. It needs no embedding model or paid vector database and works well for explicit facts such as preferences. It does not understand synonyms semantically and is not designed for millions of records. A future milestone can add local embeddings or FTS5 behind the same `MemoryStore.search()` contract after measuring memory/storage costs.

## Extraction

`MemoryExtractor` reads only user messages in the selected local conversation. It looks for explicit `remember`/`note` statements and simple `my ... is/are ...` profile facts. It skips likely credential content and per-conversation duplicates. This is intentionally conservative rather than an unbounded autonomous memory writer. The user can review and delete every memory.

## Provider boundary

`AIProvider.generate(messages, system_prompt)` returns `ChatResponse`. Adapters use documented HTTPS APIs and environment credentials. The browser receives model names and configured booleans, never keys. Provider errors are bounded and common environment secrets are redacted.

## Email and automation boundaries

`EmailProvider` defines inbox creation, message reads, and bounded polling. The web UI exposes only `MockEmailProvider`, using reserved `.test` addresses and process-memory messages. Verification parsing requires authentication context and validates code shape.

The optional Playwright runner is not part of the web API. It accepts only visible-element waits, fills, and clicks, with timeout/retry constraints and JSONL logs. There is no arbitrary sleep action or CAPTCHA handling.

## Evaluation

Evaluation datasets are local JSON. `evaluate_provider` runs the same provider interface used by chat, scores exact/contains/regex matches, measures latency, isolates per-case failures, and emits JSON or Markdown. This is response evaluation, not gradient updates, hidden fine-tuning, or automatic model modification.
