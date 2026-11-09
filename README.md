# LLM-GYM

A local-first, Android-friendly AI learning lab with persistent chat memory, model comparison, a safe mock verification inbox, and strictly authorized automation.

**Milestone status: working offline.** The web app, Python API, SQLite persistence, lexical retrieval, mock chat, mock email verification, evaluation CLI, and tests run without API keys or pip dependencies. External model APIs and the official Design Arena API require separate credentials.

> Memory is retrieval, not retraining. This project does **not** claim to fine-tune GPT, Claude, or Gemini. Fine-tuning is possible only through a provider's own supported interface and is outside this milestone.

## What works now

| Feature | Status | Credentials? |
|---|---|---|
| Live local dashboard and mobile navigation | Working locally | No |
| Mobile web chat and conversation history | Working locally | No, with `mock` |
| Conversation rename, delete, JSON/Markdown export | Working locally | No |
| Persistent SQLite messages and knowledge base | Working locally | No |
| Versioned, data-preserving SQLite migrations | Working locally | No |
| Search and relevant-memory injection into new chats | Working locally | No |
| Explicit fact extraction from your own conversations | Working locally | No |
| Numeric/alphanumeric text/HTML verification, filtering, ambiguity and expiry handling | Working locally | No |
| Mock inbox lifecycle, cancellation, failure simulation, sanitized reports | Working locally | No |
| GPT, Claude, Gemini, OpenAI-compatible adapters | Implemented; HTTP formats unit-tested | Yes, external API |
| Dataset evaluation, comparison, Markdown/JSON reports | Working locally | Only for external providers |
| Design Arena read-only leaderboard client | Implemented against official docs | Approved API key |
| Independent local registration demo and HTTP E2E | Working locally | No |
| Playwright authorized-browser runner + four E2E configs | Implemented; separate required browser CI job | Optional installation |
| mail.tm adapter for authorized API tests | Implemented, not enabled in default UI | External test account |

The `mock` provider is deliberately deterministic. It is useful for development and testing, but it is **not a real generative AI model**.

## Quick start on Android (Termux)

No PC, Docker, Node.js, or mandatory package installation is needed. Install a currently maintained Termux build, then run:

```bash
pkg update
pkg install python git -y
git clone https://github.com/kartikkamboj380-star/LLM-GYM.git
cd LLM-GYM
cp .env.example .env
python -m unittest discover -s tests -v
python run.py
```

Open **http://127.0.0.1:8000** in your phone browser. Keep Termux open while using the app. Press `Ctrl+C` (or Volume Down + C in Termux) to stop.

If you are updating an existing checkout instead of cloning:

```bash
cd ~/LLM-GYM
git pull
cp -n .env.example .env
python run.py --host 127.0.0.1 --port 8000
```

See [docs/android.md](docs/android.md) for updates, backups, phone sleep issues, and troubleshooting.

## Desktop / CI quick start

Python **3.11+** is recommended.

```bash
cp .env.example .env
python -m unittest discover -s tests -v
python run.py
```

The default bind address is loopback (`127.0.0.1`) so the unauthenticated personal-data API is not exposed to the network. To deliberately expose it inside a trusted preview or LAN:

```bash
python run.py --host 0.0.0.0 --port 8000
```

Do not expose this milestone directly to the public internet. It has no multi-user authentication or tenant isolation. Built-in per-client local rate limits bound chat and email operations, but they are not sufficient protection for a public deployment.

## Try persistent memory

1. Start a chat using **Offline mock**.
2. Send: `Remember that my favorite language is Python`.
3. Select **Extract facts**. The conservative extractor saves the explicit fact and rejects likely credentials.
4. Open **Memory** to search or add facts manually.
5. In a new chat, ask: `What is my favorite language?`
6. The matching memory is injected into the provider's system context and returned in `retrieved_memories`. The mock visibly echoes that retrieval for verification.

Data is stored in `data/llm_gym.db`, which is ignored by Git. Mock inbox messages are intentionally in-memory and disappear on restart; conversations and memories remain in SQLite.

## Connect a real AI provider

Edit `.env` **on the backend only**, choose one provider, and restart. Do not put keys in HTML, JavaScript, GitHub files, screenshots, or issue reports.

### OpenAI GPT

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=your_server_side_key
OPENAI_MODEL=gpt-4o-mini
```

### Anthropic Claude

```dotenv
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_server_side_key
ANTHROPIC_MODEL=claude-3-5-haiku-latest
```

### Google Gemini

```dotenv
AI_PROVIDER=gemini
GEMINI_API_KEY=your_server_side_key
GEMINI_MODEL=gemini-2.0-flash
```

### Another OpenAI-compatible API

```dotenv
AI_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_API_KEY=your_server_side_key
OPENAI_COMPATIBLE_BASE_URL=https://authorized-provider.example/v1
OPENAI_COMPATIBLE_MODEL=provider_model_name
```

Remote custom endpoints must use HTTPS; HTTP is accepted only on loopback. Model names are configuration examples, not promises of availability. A ChatGPT, Claude, or Gemini consumer subscription does **not** imply free API access. Check the provider's current API pricing, quotas, and terms before sending requests.

For CI that genuinely calls an external provider, store credentials in **GitHub → Settings → Secrets and variables → Actions**, then pass the specific secret to a separately authorized workflow. The included CI needs no secrets and never calls paid APIs.

## Safe mock email verification

In **Test inbox**:

1. Create an `example.test` inbox. This reserved domain cannot send real internet email.
2. Choose numeric or alphanumeric and inject a demo verification message.
3. Poll immediately. The parser requires authentication-related context and supports 4–8 digit codes and 6–10 character mixed alphanumeric codes.

There is no account creation on a third-party service, CAPTCHA automation, or security-control bypass. `app/email/mailtm.py` also implements mail.tm's documented account/token/messages APIs for separately authorized testing. Temporary inbox providers may reject OTPs; do not repeatedly create accounts or use them to evade service limits.

## Model evaluation and reports

The included dataset is a small example, not a meaningful model benchmark:

```bash
python -m app.evaluation.cli \
  --dataset examples/evaluation.json \
  --providers mock \
  --output data/mock-evaluation.md
```

With explicitly configured external providers:

```bash
python -m app.evaluation.cli \
  --dataset examples/evaluation.json \
  --providers openai,anthropic,gemini \
  --output data/model-comparison.json
```

Each case supports `exact`, `contains`, or `regex` matching. Reports include pass rate, per-case results, latency, and sanitized error types. Network requests can incur charges. A failing offline mock on knowledge questions is expected.

## Design Arena integration and limits

The public site and official docs were inspected on **2026-11-09**. Design Arena documents an API-key-protected, read-only leaderboard API:

```text
GET https://www.designarena.ai/api/v1/arenas
GET https://www.designarena.ai/api/v1/models
GET https://www.designarena.ai/api/v1/leaderboard/{arena}/{category}
```

After receiving approval, set `DESIGNARENA_API_KEY` in `.env`, restart, and use **Arena API → Load arenas**. The backend sends the bearer token; frontend code never receives it.

No documented login, prompt-generation, voting, or project-creation API was found. Accordingly, this repository does not invent endpoints or automate those actions. The safe alternative is to use the local chat application for your own authorized workflows and Design Arena only for its documented read-only data. Read [docs/design-arena.md](docs/design-arena.md) for the inspection notes and source links.

## Authorized browser automation (optional)

The core phone setup stays small. Playwright and Chromium are optional and comparatively large:

```bash
python -m pip install -r requirements-automation.txt
playwright install chromium
python -m app.automation.browser examples/authorized-flow.json --log data/run.jsonl
```

The runner supports `wait_for`, `fill`, and `click`; bounded retries and timeouts; environment-variable expansion for test credentials; and JSONL execution logs. It waits for element readiness rather than using fixed UI delays. Sleep is used only as bounded exponential backoff after failures. Use it only on sites you own or have explicit permission to test. It contains no CAPTCHA bypass, anti-abuse evasion, or account-restriction workaround.

## Architecture

```text
static/                       Mobile-first HTML/CSS/vanilla JS (no secrets)
app/api.py                    Same-origin JSON API + static server
app/chat.py                   History → retrieval → provider → persistence
app/memory.py                 SQLite conversations, knowledge, ranking, extraction
app/providers/                Mock, GPT, Claude, Gemini, compatible adapters
app/email/                    Email interface, parser, mock, optional mail.tm
app/designarena/              Official read-only API client only
app/automation/               Optional Playwright authorized-flow runner
app/evaluation/               Dataset runner, comparison, reports
tests/                        Offline unit and live HTTP integration tests
data/                         Ignored runtime DB/reports
.github/workflows/ci.yml       Python 3.11 and 3.12 offline CI
```

All core runtime functionality uses Python's standard library. SQLite is included with Python; there is no vector database, embedding service, Docker image, frontend build, or large framework. Retrieval uses bounded local lexical ranking over up to 1,000 recent memories. That is appropriate for this lightweight milestone, not unlimited enterprise-scale semantic search.

More detail: [architecture and phased plan](docs/ARCHITECTURE.md) · [repository audit](docs/PROJECT_AUDIT.md) · [API conventions](docs/API.md) · [email/OTP lab](docs/EMAIL.md) · [automation](docs/AUTOMATION.md) · [testing](docs/TESTING.md) · [security](docs/security.md) · [deployment](docs/deployment.md).

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Server and database health |
| GET | `/api/providers` | Model names and configured booleans, never keys |
| GET | `/api/dashboard` | Real local status, counts, recent activity |
| GET/POST | `/api/conversations` | List/create conversations |
| GET/PATCH/DELETE | `/api/conversations/{id}` | Retrieve, rename, or delete a conversation |
| GET | `/api/conversations/{id}/export?format=json\|markdown` | Export a conversation |
| POST | `/api/conversations/{id}/messages` | Chat with selected provider |
| GET/POST | `/api/memory` | Search/list or add knowledge |
| POST | `/api/memory/extract` | Extract explicit facts from owned chat |
| DELETE | `/api/memory/{id}` | Delete knowledge |
| POST | `/api/email/mock/inboxes` | Create a local simulated inbox |
| POST | `/api/email/mock/inboxes/{id}/demo` | Inject numeric/alphanumeric demo |
| POST | `/api/email/mock/inboxes/{id}/poll` | Bounded polling and code parsing |
| GET | `/api/designarena/{arenas\|models}` | Official read-only proxy |

## Development

```bash
# Use your session's dedicated branch; do not commit secrets or runtime data.
git status
python -m compileall -q app tests run.py
python -m unittest discover -s tests -v

# Optional JavaScript syntax check, if Node already exists (not required):
node --check static/app.js

git add .
git commit -m "Describe the tested change"
```

Run small increments: add unit tests, run them, fix failures, then test the HTTP flow. Do not claim external provider delivery, Playwright execution, mail.tm delivery, or Design Arena API access has been verified unless it was actually exercised with authorization.

## Deployment

This repository is primarily a **single-user local app**. GitHub Actions runs tests; it is not a persistent web host. A static-only host cannot run the Python backend or protect provider keys. For a remote deployment, use a Python-capable host whose current free tier and card requirements you have independently verified, attach persistent storage, add authentication/TLS/rate limiting, and keep the database off Git. See [deployment instructions](docs/deployment.md).

## License

MIT — see [LICENSE](LICENSE).
