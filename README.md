# 📬 AI Email Assistant

You never open your mailbox, only this app. It reads your mail and turns it into a queue of **jobs**: specific
actions worded for that exact email, such as "Send Jason the list of apps you're working on" or "This podcast
wants to interview you: yes / no / maybe later." Each email stays in your real inbox until its jobs are done,
then the app archives it in the real mailbox.

Think: a 1950s secretary triaging your morning mail. The full design is in
[`docs/specs/2026-11-01-email-assistant-v1-design.md`](docs/specs/2026-11-01-email-assistant-v1-design.md).

---

## 🧠 How it works

- **Mailbox plugins.** Each mail account is reached through a plugin that speaks the `mailbox/1` contract over
  MCP ([`docs/contracts/mailbox-1.md`](docs/contracts/mailbox-1.md)). The reference IMAP/SMTP plugin lives in
  `packages/imap-mailbox`. The Proton plugin (`plugins/proton`) runs through Proton Mail Bridge, and a watchdog
  restarts Bridge when it stops. The Gmail plugin (`plugins/gmail`) uses IMAP with an app password.
- **Pipeline.** New mail is synced, minimized, and checked first against learned **rules** (they outrank the AI).
  Otherwise the AI proposes a job, with similar past decisions (**examples**) as context. Mail the AI can't
  classify becomes an ask-owner card: "What do you want to do with this?"
- **Verbs.** `reply`, `forward`, `digest`, `snooze`, `follow_up`, `todo`, `archive_noise`, `unsubscribe`.
- **Permissions.** Each verb is `autonomous`, `ask` or `never_auto`, set on the settings screen and mirrored in a
  readable `permissions.yaml`. Every verb has a ceiling: a `forward` never goes out on its own, and `unsubscribe`
  always needs your tap.
- **Learning.** Your corrections, ask-owner answers ("always do this for this sender/list") and restores of mail
  the app archived become rules and examples, so similar mail is handled your way next time.
- **Never losing mail.** Mail is only archived once its jobs are done. Every action is logged in History, and
  archives can be undone. Noise the app filtered stays in the Filtered view for 30 days, one tap from restore.

## 📱 Screens

| Screen | What it's for |
|---|---|
| Jobs (home) | The job queue: approve, edit, choose another action, dismiss; ask-owner cards |
| History | Timeline of everything the app and you did, with undo |
| Filtered | The last 30 days of noise the app archived, with one-tap restore |
| Connections | Mailbox plugin status and connection checks |
| Settings | AI provider and model, poll interval, first-connect window, per-verb permissions |

## 🚧 Status

v1 is in progress; see the [open issues](https://github.com/frankbria/email-assistant/issues).

- **Done:** Proton plugin, the `mailbox/1` contract, sync, the AI pipeline, the job queue, ask-owner, all v1
  verbs, rules and examples, History with undo, Filtered view, settings and permissions, sign-in.
- **Next:** calibration and quality metrics, the Gmail plugin, the redacted-cloud privacy mode, and the v1
  release gate.

---

## 🚀 Tech stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 + Tailwind CSS (Node.js 24) |
| Backend | FastAPI + Beanie (MongoDB ODM), Python 3.14+ |
| Database | MongoDB (Atlas, or a local container) |
| Auth | Better Auth (single owner); the API verifies its JWTs |
| AI | Anthropic Claude behind a provider interface |
| Mail | `mailbox/1` plugins over MCP |
| Packages | uv (backend), npm (frontend) |

## 📁 Project structure

```
email-assistant/
├── backend/                # FastAPI app: api/routers, pipeline, executor, sync, models
├── frontend/               # Next.js app (src/app, src/components, e2e/)
├── packages/
│   ├── mailbox-contract/   # mailbox/1 contract types and JSON schemas
│   └── imap-mailbox/       # reference IMAP/SMTP plugin
├── plugins/proton/         # Proton plugin (via Proton Mail Bridge) and its watchdog
├── plugins/gmail/          # Gmail plugin (IMAP + app password)
├── docs/                   # spec, contract, deployment
├── docker-compose.yml      # deployment
└── docker-compose.test.yml # MongoDB + GreenMail for the test suites
```

---

## 🧪 Running locally

### Prerequisites
- [uv](https://docs.astral.sh/uv/)
- Node.js 24.12.0+ (`nvm use` in `frontend/` reads `.nvmrc`)
- MongoDB (or `docker compose -f docker-compose.test.yml up -d mongo`)

### Backend
```bash
cd backend
cp .env.example .env   # fill in ANTHROPIC_API_KEY and MongoDB
uv sync
uv run uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
cp .env.example .env.local   # BETTER_AUTH_SECRET: openssl rand -base64 32
nvm use
npm install
npm run dev   # http://localhost:3200
```

To connect a Proton account, follow [`plugins/proton/README.md`](plugins/proton/README.md); for Gmail,
[`plugins/gmail/README.md`](plugins/gmail/README.md).

## ⚙️ Configuration

The `.env.example` files list every setting with comments:

- `backend/.env.example`: MongoDB, `ANTHROPIC_API_KEY`, default AI provider/model, sync interval, first-connect
  window, optional monthly AI cap, permissions file, Better Auth URL.
- `frontend/.env.example`: API base URL, MongoDB for the Better Auth collections, `BETTER_AUTH_SECRET`,
  `BETTER_AUTH_URL`.
- `.env.example` (repo root): Docker Compose deployment.

The AI provider/model, poll interval and first-connect window in the backend env are defaults; the settings
screen overrides them.

## 🐳 Deployment

Docker Compose on a tailnet host, with images from GHCR. See [`docs/deployment.md`](docs/deployment.md). With
Atlas, stored mail lives off your own machines.

## 🧪 Testing

```bash
docker compose -f docker-compose.test.yml up -d   # MongoDB + GreenMail (IMAP/SMTP)

# Backend: real MongoDB and a real mail server, no mocks
cd backend
uv run pytest

# Frontend
cd frontend
npm run test   # Vitest
npm run e2e    # Playwright
```

Tests that call the paid AI API are marked `integration` and run only locally with `ANTHROPIC_API_KEY` set.
