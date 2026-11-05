# 📬 AI Email Assistant

You never open your mailbox, only this app. It reads your mail and turns it into a queue of **jobs**: specific
actions worded for that exact email, such as "Send Jason the list of apps you're working on" or "This podcast
wants to interview you: yes / no / maybe later." Each email stays in your real inbox until its jobs are done,
then the app archives it in the real mailbox.

Think: a 1950s secretary triaging your morning mail. The full design is in
[`docs/specs/2026-11-01-email-assistant-v1-design.md`](docs/specs/2026-11-01-email-assistant-v1-design.md).

---

## 🧠 How it works

```
mailbox plugin (MCP) → sync → minimize → (redact) → rules → AI proposal → validate → job queue
                                                                                   ↘ ask-owner card
```

- **Job queue.** Every email the app keeps becomes one or more jobs on the **Do** screen. You approve, edit, pick
  another action or dismiss each one. When all of an email's jobs are done, the app archives it in your real
  mailbox. Mail it can't handle confidently becomes an ask-owner card: "What do you want to do with this?"
- **Mailbox plugins.** The app never talks IMAP itself. Each mail account is reached through a plugin, an MCP
  server that speaks the `mailbox/1` contract ([`docs/contracts/mailbox-1.md`](docs/contracts/mailbox-1.md)).
  Plugins are listed in a `plugins.yaml`. There are two:
  - **Proton** (`plugins/proton`), through Proton Mail Bridge on the machine where Bridge runs.
  - **Gmail** (`plugins/gmail`), over IMAP with an app password.

  Both are built on the reference IMAP/SMTP plugin in `packages/imap-mailbox`.
- **Watchdog.** Bridge stops now and then. The Proton plugin ships a small always-on watchdog for the Bridge
  machine that checks Bridge every minute, restarts it (with back-off), and stops to ask you when only you can fix
  it (for example, Bridge needs you to sign in again). The Connections screen shows plugin health and what failed.
- **Pipeline.** New mail is synced, minimized (quoted history, signatures and trackers stripped), and checked
  first against learned **rules**, which outrank the AI. Otherwise the AI proposes a job, with similar past
  decisions (**examples**) as context. A deterministic validator then checks that the proposal quotes the email,
  carries something useful (a draft, options, a link or a deadline), and doesn't act on instructions inside the
  email. If it fails, you get an ask-owner card; the app never guesses.
- **Verbs.** `reply`, `forward`, `digest`, `snooze`, `follow_up`, `todo`, `archive_noise`, `unsubscribe`.
- **Permissions.** Each verb is `autonomous`, `ask` or `never_auto`, set on the Settings screen and mirrored in a
  readable `permissions.yaml`. Every verb has a ceiling: a `forward` never goes out on its own, and `unsubscribe`
  always needs your tap.
- **Learning.** Your corrections, ask-owner answers ("always do this for this sender/list") and restores of mail
  the app archived become rules and examples, so similar mail is handled your way next time.
- **Never losing mail.** Mail is only archived once its jobs are done. Every action is logged in History, and
  archives can be undone. Noise the app filtered stays in the Filtered view for 30 days, one tap from restore.

## 📱 Screens

| Screen | What it's for |
|---|---|
| Do (home) | The job queue: approve, edit, choose another action, dismiss; ask-owner cards |
| History | Timeline of everything the app and you did, with undo |
| Filtered | The last 30 days of noise the app archived, with one-tap restore |
| Train | Calibration: the app proposes for recent mail without acting, and your reactions teach it |
| Connections (Settings → Mailbox connections) | Mailbox plugin status, connection checks and the guided setup checklist |
| Settings | Privacy mode, AI provider and model, poll interval, first-connect window, per-verb permissions |

---

## 🐳 Install (Docker Compose)

The app runs as two containers, `backend` (FastAPI) and `frontend` (Next.js), plus an optional MongoDB container.
You need Docker with Compose v2 and `git`. [`docs/deployment.md`](docs/deployment.md) covers running it on a
tailnet host, GHCR images and updates; the steps below get a working job queue on one machine.

1. **Get the code.**
   ```bash
   git clone https://github.com/frankbria/email-assistant.git
   cd email-assistant
   ```
2. **Pick free ports.** The defaults are 3200 (web) and 8000 (API). On a shared host, check first:
   `ss -ltn | grep -E ':(3200|8000) '`. If either is taken, pick others.
3. **Configure.** `cp .env.example .env`, then set in `.env`:
   - `MONGODB_URI`: `mongodb://mongo:27017` for the local MongoDB container, or your Atlas connection string
     (read [Privacy](#-privacy) first).
   - `BETTER_AUTH_SECRET`: the output of `openssl rand -base64 32`.
   - `BIND_ADDRESS`: leave `127.0.0.1` on your own machine; on a tailnet host, its Tailscale IP. **Never
     `0.0.0.0`**: Docker's published ports bypass firewalls such as UFW.
   - `BACKEND_PORT`, `FRONTEND_PORT`: your ports from step 2.
   - `PUBLIC_API_BASE`, `FRONTEND_ORIGIN`: the URLs the browser uses, e.g. `http://localhost:8000` and
     `http://localhost:3200`. Change the ports in them if you changed them above. A mismatch shows up as
     sign-in or CORS errors.
   - `ANTHROPIC_API_KEY`: needed to propose jobs from mail. The queue opens without it.
4. **Create the config directory** the backend writes `permissions.yaml` to (the container runs as `nobody`):
   ```bash
   mkdir -p config && sudo chown 65534 config
   ```
5. **Start it.** With the local MongoDB container:
   ```bash
   docker compose --profile local-mongo up -d --build
   ```
   With Atlas, leave out `--profile local-mongo`. Keep the profile flag on every later `docker compose` command
   (including `down`), or Compose ignores the MongoDB container. The first build takes a few minutes.
6. **Sign up.** Open `FRONTEND_ORIGIN` (e.g. http://localhost:3200). The first visit asks you to create the owner
   account; after that, sign-up is closed and the app shows the sign-in form. You land on the **Do** screen (the
   job queue), empty until a mailbox is connected.

To stop it: `docker compose --profile local-mongo down` (add `-v` to delete the database too).

## 🔌 Connecting mail

Connect a mailbox by listing its plugin in a `plugins.yaml`. In the Docker install, put it in `config/` (owned by
uid 65534 now, so `sudo cp plugins.yaml config/`), add `PLUGINS_CONFIG=/app/config/plugins.yaml` to `.env`, and
run the `up -d` command from step 5 again. Secrets never go in `plugins.yaml`: it names environment variables,
which you set in `.env`.

- **Proton:** follow [`plugins/proton/README.md`](plugins/proton/README.md). The plugin and its watchdog run on
  the machine where Proton Mail Bridge runs; when the app runs elsewhere (as in Docker), the plugin serves MCP over
  HTTP on your tailnet and `plugins.yaml` points at it.
- **Gmail:** follow [`plugins/gmail/README.md`](plugins/gmail/README.md): turn on 2-Step Verification, create an
  app password, and check IMAP is allowed (personal accounts always have it; on Google Workspace the admin
  must allow it). The plugin ships with the backend, in the Docker image too; its `plugins.yaml` entry runs
  `command: gmail-plugin` over stdio.

Then open **Settings → Mailbox connections → Setup checklist**. It checks each step live and says what to fix.
For Gmail it also checks **Auto-Expunge** (Settings → Forwarding and POP/IMAP in Gmail), which can send archived
mail to the Trash; the checklist warns when it's on. On first connect the app only syncs recent mail (the
first-connect window on the Settings screen, 14 days by default); older mail is left alone.

## 🔒 Privacy

Choose a privacy mode on the Settings screen. It decides what is sent to the AI provider:

- **Full cloud** (the default): the minimized email goes to the AI, along with a few of your sent emails (so
  drafts sound like you), your forwarding history and similar past decisions.
- **Redacted cloud**: before anything leaves the server, email addresses, phone numbers, URLs, account and card
  numbers, one-time codes, and names the app can see (from the From/To/Cc display names and from greetings and
  sign-offs) become placeholders such as `PERSON_1` or `URL_2`. The mapping stays on the server, and your jobs
  show the real values. **What it doesn't hide:** a name that appears only mid-sentence and in no header ("ask
  Maria about it"), lower-case names, and postal addresses still reach the AI (tracked in
  [#183](https://github.com/frankbria/email-assistant/issues/183)).

**The privacy modes only cover what goes to the AI, not where mail is stored.** With MongoDB Atlas (the default
database), stored mail content lives in Atlas, off your own machines. If you don't want that, use the local
MongoDB container (`--profile local-mongo`).

## 🎯 Calibration and metrics

- **Train screen.** Calibration runs the pipeline over recent mail without acting on it. For each proposal you
  pick the action you'd want; that teaches the app and is appended to a local calibration test set
  (`config/test_set.jsonl` in the Docker install). That file is your real mail; it is never committed.
- **Metrics command.** `cd backend && uv run python -m app.metrics [test-set.jsonl]` (in the Docker install, pass
  `../config/test_set.jsonl`) re-decides every line of a
  test set in a scratch database and prints each quality metric with PASS or FAIL against its threshold (exit
  code 1 if any fails). It calls the paid AI, so it needs `ANTHROPIC_API_KEY`.
- **Weekly metrics workflow.** `.github/workflows/metrics.yml` runs the command every Monday (and on demand) over
  the committed synthetic test set, `backend/tests/fixtures/synthetic_test_set.jsonl`. It needs the
  `ANTHROPIC_API_KEY` repository secret (Settings → Secrets and variables → Actions) and fails if it's missing.

## 🚧 Status

v1 is in progress; see the [open issues](https://github.com/frankbria/email-assistant/issues).

- **Done:** the `mailbox/1` contract, the Proton plugin and watchdog, the Gmail plugin and its setup checklist,
  sync, the AI pipeline, the job queue, ask-owner, all v1 verbs, rules and examples, History with undo, the
  Filtered view, settings and permissions, sign-in, calibration and quality metrics, and redacted-cloud mode.
- **Awaiting live runs on a disposable Gmail account:** the Gmail half of the conformance suite (AC-C.3,
  [#96](https://github.com/frankbria/email-assistant/issues/96)) and the Auto-Expunge check
  ([#97](https://github.com/frankbria/email-assistant/issues/97)). Both pass against the test mail server, which
  has no Gmail extensions; neither has been run against real Gmail yet.
- **Next:** the v1 release gate.
- **After v1:** local-only AI mode, Outlook and generic IMAP plugins.

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
├── backend/                # FastAPI app: api/routers, pipeline, executor, sync, models, metrics
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

## 🧪 Developing

### Prerequisites
- [uv](https://docs.astral.sh/uv/) and Python 3.14+
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

Outside Docker, `plugins.yaml` is read from `backend/` (or `PLUGINS_CONFIG`).

### Configuration

The `.env.example` files list every setting with comments:

- `.env.example` (repo root): the Docker Compose install (the backend also reads any `backend/.env.example`
  setting from this `.env`).
- `backend/.env.example`: MongoDB, `ANTHROPIC_API_KEY`, default AI provider/model, sync interval, first-connect
  window, optional monthly AI cap, permissions file, calibration test set, Better Auth URL.
- `frontend/.env.example`: API base URL, MongoDB for the Better Auth collections, `BETTER_AUTH_SECRET`,
  `BETTER_AUTH_URL`.

The AI provider/model, poll interval and first-connect window in the backend env are defaults; the Settings
screen overrides them.

### Testing

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
