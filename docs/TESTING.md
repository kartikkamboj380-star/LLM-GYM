# Testing guide

## Offline unit and HTTP integration tests

```bash
python -m compileall -q app tests run.py
python -m unittest discover -s tests -v
node --check static/app.js
node --check static/demo.js
```

The suite uses temporary SQLite databases and local ephemeral HTTP servers. External AI/Design Arena/mail.tm HTTP calls are mocked; no API keys or paid requests are needed. Current areas include provider adapters and capabilities, connection tests, every provider HTTP error category, secret redaction, no silent fallback, provider/model selection, response/context metadata, conversations, memory, migrations, rate limits/errors, dashboard/export, email lifecycle, OTP rules/redaction/cancellation, and local registration integration.

On **2026-11-09**, the Phase 6 local verification run was:

```text
python3 -m unittest discover -s tests -v
→ Ran 98 tests in 8.008s — OK
python -m compileall -q app tests run.py — passed
node --check static/app.js — passed
node --check static/demo.js — passed
```

Node is used only for optional JavaScript syntax checks and is not an application dependency. The 98-test count is the local offline suite; browser E2E is reported separately.

## Provider contract coverage

Provider tests mock `urllib` and adapter transport. They assert that OpenAI-compatible, Anthropic, and Gemini connection tests use documented model `GET` paths with no generation payload; that the mock test is local; that external confirmation and persisted status work through the HTTP API; that missing keys are categorized without fallback; and that all HTTP status/network categories, retry metadata, and secret redaction are safe. Normalized usage, finish reasons, truncation, bounded context, and export metadata are covered by adapter, service, migration, and API integration tests. See `PROVIDERS.md`.

## Browser end-to-end tests

Install the optional Playwright dependencies as described in `AUTOMATION.md`, then run each required local flow through `app.automation.local_e2e`. The GitHub Actions `browser-e2e` job executes all four flows rather than skipping them. Browser verification is reported separately from offline unit/integration tests. The new Providers view currently has JavaScript syntax and HTTP contract checks, but no dedicated real-browser flow; do not describe it as browser-verified until one runs.

## Evaluation smoke test

```bash
python -m app.evaluation.cli --dataset examples/evaluation.json --providers mock --output data/mock-evaluation.md
```

The deterministic mock is expected to fail knowledge questions; the purpose is to verify dataset execution and report generation, not to claim model accuracy.

## Real external verification

No default test requires a real GPT/Claude/Gemini/mail.tm/Design Arena credential. A live connection must be separately authorized and reported with provider, model, time, result, and any quota limitation. A mocked adapter test is not evidence of live connectivity. A confirmed model-inspection `GET` is not evidence that generation works or that streaming is supported.

## Failure reporting

Report the exact command, number run/passed/failed/skipped, duration, and relevant safe error messages. Do not delete, skip, or weaken failing tests to make CI green. OTPs, keys, tokens, private message bodies, and unsanitized reports must not be attached to CI or issue reports.
