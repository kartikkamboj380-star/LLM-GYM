# Deployment instructions

## Recommended: local Android deployment

This is the only deployment exercised by this milestone:

```bash
cd ~/LLM-GYM
cp -n .env.example .env
python run.py --host 127.0.0.1 --port 8000
```

The app is then available at `http://127.0.0.1:8000` on that phone. Persistent state is `data/llm_gym.db`.

## Trusted preview or LAN

```bash
python run.py --host 0.0.0.0 --port 8000
```

Use the preview URL or trusted device address supplied by that environment. The frontend calls relative `/api/...` URLs, so it does not hard-code localhost and works through a same-origin reverse proxy. There is no separate development server or CORS configuration to maintain.

This mode still has no user authentication. Do not port-forward it to the public internet.

## GitHub Actions

CI is defined in `.github/workflows/ci.yml`. It runs on pushes and pull requests with Python 3.11 and 3.12:

```bash
python -m compileall -q app tests run.py
python -m unittest discover -s tests -v
```

No installation step is necessary because `requirements.txt` intentionally has no dependencies. GitHub Actions usage is subject to the repository/account's current plan and limits. Actions is a test runner, not a persistent application host.

## Remote Python host (not preconfigured)

A static host alone cannot protect API keys, run SQLite, or serve this backend. If you later choose a Python-capable host:

1. Verify its **current** free-tier limits, sleep behavior, persistent-disk support, and whether a credit card is mandatory. Do not infer this from marketing or an old tutorial.
2. Set provider keys in the host's secret environment settings, never in the repository.
3. Start with `python run.py --host 0.0.0.0 --port $PORT` after loading the environment. If the platform does not expand `$PORT` in its start-command field, supply the assigned port through a small platform-specific configuration.
4. Put the app behind the host's TLS proxy and use persistent storage for `data/`.
5. Add authentication, CSRF protection where applicable, request rate limits, backups, monitoring, and multi-user data isolation before allowing other users.
6. Run the full offline tests in deployment CI. Test any real provider with a small, explicitly billed/authorized request.

No paid server, Docker image, or specific third-party free tier is required or claimed by this repository.

## Production hardening still required

The development server is intentionally small. A public production version should use a maintained ASGI/WSGI server/framework, structured authentication, security headers adapted to the deployment, database migrations, encrypted backups, secret rotation, rate limiting, logging/privacy controls, and a defined data-retention policy. Those features are not represented as already complete.
