# Android-only setup and operation

The milestone is designed for Termux with limited storage/RAM. The core uses Python's standard library, a small vanilla-JavaScript frontend, and SQLite. Do not install Playwright/Chromium unless you specifically need authorized browser testing and have enough space.

## 1. Install and clone

Install a currently maintained Termux build from its official distribution source. Avoid abandoned Play Store builds. In Termux:

```bash
pkg update
pkg install python git -y
git clone https://github.com/kartikkamboj380-star/LLM-GYM.git
cd LLM-GYM
cp .env.example .env
```

Storage permission is not required when the project stays under Termux's home directory. Keeping it there also reduces accidental exposure of the database.

## 2. Verify and start

```bash
cd ~/LLM-GYM
python -m unittest discover -s tests -v
python run.py --host 127.0.0.1 --port 8000
```

Open Chrome/Firefox on the same phone at `http://127.0.0.1:8000`. The initial `mock` provider needs no network or key. For a home-screen shortcut, use the browser's **Add to Home screen** command while the app is open.

Keep Termux running. Android may suspend background processes; if the page stops responding, return to Termux and restart the command. Manufacturer battery settings vary, so no universal background-operation guarantee is made.

Stop with Volume Down + C, or `Ctrl+C` on an external keyboard.

## 3. Update the project

Stop the server first:

```bash
cd ~/LLM-GYM
git status
git pull
python -m unittest discover -s tests -v
python run.py
```

If `git status` shows local edits you want to keep, commit them on your working branch before pulling. Do not upload `.env` or `data/`.

## 4. Configure a provider without exposing its key

Use a text editor inside Termux, or Android's safe file editor:

```bash
cd ~/LLM-GYM
nano .env
```

Set one `AI_PROVIDER` and its matching backend key/model. Save and restart. Never paste keys into `static/app.js`, chat messages, memories, Git commits, screenshots, or issues. A key typed into `.env` is loaded only by the Python process.

If `nano` is missing, either `pkg install nano -y` or create `.env` with `cp .env.example .env` and use an editor you trust.

## 5. Backup or reset

Stop the server to get a consistent simple file copy:

```bash
cd ~/LLM-GYM
cp data/llm_gym.db data/llm_gym.backup.db
```

Both files are Git-ignored. To export elsewhere, use Termux storage tools deliberately and protect the copy: it contains your chats and memories.

To reset all persistent app data after backing up anything important:

```bash
rm data/llm_gym.db data/llm_gym.db-shm data/llm_gym.db-wal 2>/dev/null
python run.py
```

Mock email inboxes are ephemeral and cannot be backed up.

## 6. Git workflow from the phone

For the Arena working branch used to build this milestone:

```bash
cd ~/LLM-GYM
git checkout arena/f5937fd2-llm-gym
python -m unittest discover -s tests -v
git add .
git commit -m "Describe your tested change"
git push origin arena/f5937fd2-llm-gym
```

Use GitHub's normal secure authentication flow. Never place a personal access token in source files or this README. GitHub CLI and credential helpers are optional, not app dependencies.

## Troubleshooting

- **`Address already in use`**: stop the previous server or choose another port: `python run.py --port 8001`.
- **Browser cannot connect**: confirm Termux still prints the running URL and use the exact same port.
- **External provider says key needed**: check `.env`, save it, stop/restart the server, and select the provider again.
- **Provider quota/billing error**: this is an account/provider condition, not a memory bug. Return to `AI_PROVIDER=mock`; do not assume a chat subscription supplies API credits.
- **Low storage**: skip Playwright, remove generated reports you no longer need, and avoid cloning large datasets.
- **Corrupt/missing database after experimentation**: stop the server, restore your backup, or reset as above. Tests use temporary databases and do not modify your real data.
