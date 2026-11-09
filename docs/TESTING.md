# Testing guide

## Offline unit and HTTP integration tests

```bash
python -m compileall -q app tests run.py
python -m unittest discover -s tests -v
node --check static/app.js
node --check static/demo.js
```

The suite uses temporary SQLite databases and local ephemeral HTTP servers. External AI/Design Arena/mail.tm HTTP calls are mocked; no API keys or paid requests are needed. Current areas include providers, conversations, memory, migrations, rate limits/errors, dashboard/export, email lifecycle, OTP rules/redaction/cancellation, and local registration integration.

Node is used only for optional JavaScript syntax checks and is not an application dependency.

## Browser end-to-end tests

Install the optional Playwright dependencies as described in `AUTOMATION.md`, then run each required local flow through `app.automation.local_e2e`. The GitHub Actions `browser-e2e` job executes all four flows rather than skipping them. Browser verification is reported separately from offline unit/integration tests.

## Evaluation smoke test

```bash
python -m app.evaluation.cli --dataset examples/evaluation.json --providers mock --output data/mock-evaluation.md
```

The deterministic mock is expected to fail knowledge questions; the purpose is to verify dataset execution and report generation, not to claim model accuracy.

## Real external verification

No default test requires a real GPT/Claude/Gemini/mail.tm/Design Arena credential. A live connection must be separately authorized and reported with provider, model, time, result, and any quota limitation. A mocked adapter test is not evidence of live connectivity.

## Failure reporting

Report the exact command, number run/passed/failed/skipped, duration, and relevant safe error messages. Do not delete, skip, or weaken failing tests to make CI green. OTPs, keys, tokens, private message bodies, and unsanitized reports must not be attached to CI or issue reports.
