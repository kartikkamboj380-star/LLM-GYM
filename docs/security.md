# Security and responsible-use notes

## Secrets

- `.env`, database files, key files, runtime reports, and JSONL logs are Git-ignored.
- Provider keys are read by backend adapters only. `/api/providers` returns booleans, not credentials.
- Custom OpenAI-compatible remote endpoints require HTTPS.
- Gemini's key is sent in the `x-goog-api-key` header, not a URL query parameter.
- Browser automation does not log fill values; use `${ENV_VAR}` placeholders in flow JSON.
- Check `git diff --cached` before every commit. Rotate any key that was accidentally shared.

GitHub Secrets are appropriate for explicitly authorized CI calls, not a substitute for API billing/quota approval. The default CI uses no secrets and makes no external model calls.

## Local-server boundary

This is a single-user development application without login, CSRF tokens, per-user authorization, or tenant isolation. Configurable in-memory rate limits bound chat and sensitive email operations per client/bucket, but they reset on restart and are not a public-security boundary. Same-origin responses and a restrictive content security policy reduce exposure, but they do not make the app safe as a public multi-user service. Keep the default `127.0.0.1` binding. Using `0.0.0.0` is for a trusted preview/LAN only.

Do not store sensitive personal information or credentials in memories. The extractor rejects common credential phrases, but that heuristic is not a guarantee. Manual memory creation accepts any non-empty text by design.

## Third-party authorization

Only automate systems you own or have explicit permission to test. Respect provider terms, quotas, robots/access restrictions, and API documentation. No module in this repository should be used to bypass CAPTCHA, authentication, anti-abuse systems, rate limits, account restrictions, or service limits.

Temporary email does not guarantee OTP delivery. Do not create multiple accounts to evade limits. The mock email flow is the default because it exercises parsing without involving a third party.

## Reporting and data

Evaluation and automation outputs can contain prompts, responses, URLs, and selectors. Although error reports contain exception types rather than raw exception messages, review generated files before sharing. Database backups also contain full chat content and must be protected.

## Dependency scope

The core has no third-party runtime dependencies, reducing supply-chain and storage overhead. Optional Playwright brings its own dependency and browser supply chain; install it only when needed and keep it updated.
