# Email Assistant v1: Design

**Status:** Draft for review · **Date:** 2026-11-01 · **Supersedes:** `docs/sprint-1-user-stories.md`, `docs/sprint-2-user-stories.md`, `docs/sprint-3-user-stories.md`. They move to `docs/archive/` and are kept only as a scope reference.

This document marks where each decision came from:
- **[Frank]**: decided by the project owner.
- **[Call]**: the designer's call. The owner can overrule it.
- **[Builder]**: left to whoever implements it.

---

## 1. Intent

The owner never opens their mailbox, only this app. **[Frank]**

The app turns incoming mail into a queue of **jobs**. A job is a specific action, worded for this exact email, that removes steps the owner would otherwise take, including the decision about whether to respond at all. Examples:
- "Update this login, it's about to expire."
- "Send Jason a list of the apps you're working on."
- "Review the summary of this week's newsletters."
- "This podcast wants to interview you: yes / no / maybe later."

Each email stays in the real inbox until its jobs are done, then it is archived in the real mailbox. Mail the app can't classify arrives as "What do you want to do with this?" The owner's answer is stored and applied to similar mail next time.

The reason for building it: a 1950s secretary triaging the morning mail, for someone whose mail lives in Proton and Gmail. Without the specificity, it is "just an expensive mail forwarder." **[Frank]**

## 2. Audience and distribution

- **Open source, single user.** One install serves one owner. **[Frank]**
- **Multi-user and multi-tenant come later.** The data model keeps owner-scoped records so they stay possible, but nothing is built for them now. **[Frank]**
- **Runs in one of two places:** **[Frank]**
  - on the owner's machine next to Proton Bridge, or
  - on a VPS inside the owner's Tailscale network, reaching the Proton plugin on the Bridge machine by a tailnet URL.

## 3. Goals, non-goals, anti-goals

### Goals (v1)
1. **Two mailbox plugins, Proton and Gmail,** behind one plugin contract built on MCP. **[Frank]**
2. **A job queue that replaces the inbox,** with archive-on-done. **[Frank]**
3. **A permission level for each action verb:** autonomous, ask first, or never automatic. **[Frank]**
4. **Learning from the owner's choices,** both on unclassified mail and on corrections. **[Frank]**
5. **Noise filtering:** mail that doesn't need the owner is recognized. It starts cautious and improves with corrections. **[Frank]**
6. **Self-diagnosing, self-healing Proton connectivity.** Never "unreachable, we'll check tomorrow." **[Frank]**
7. **Privacy modes:** full cloud (the default) and redacted cloud (optional). **[Frank]**
8. **Single-owner authentication with Better Auth.** Clerk is dropped. **[Frank]**
9. **A modernized platform,** covered in §12.

### Non-goals (v1)
- Outlook and generic IMAP plugins. **[Frank]**
- Local-only AI. It ships after v1, and the pipeline must leave room for it (§8). **[Frank]**
- A sender × action permission matrix. **[Frank]**
- Multi-user and multi-tenant. **[Frank]**
- Native mobile apps, calendar integration, and push notifications outside the app. **[Call]**
- Forwarding-based ingestion (MailSlurp, the `/email/incoming` webhook, per-user provisioned inboxes). It is removed. **[Call]**

### Anti-goals: things that destroy trust even when the app "works" **[Frank]**
- **A1. Losing mail.** Mail is never deleted. Archive only.
- **A2. Archiving before the job is handled,** or corrections and training that don't stop it from happening again.
- **A3. Useless or disconnected suggestions:**
  - the same verb applied to every email regardless of context (e.g. "reply" on everything), or
  - actions with no basis in the email (e.g. "schedule a meeting" when nothing mentions a meeting).
- **A4. Failing to filter noise,** after a reasonable amount of correction.

Each anti-goal has acceptance criteria in §11.

## 4. Core concepts

| Concept | Meaning |
|---|---|
| **Mailbox plugin** | An MCP server that gives the app access to one mail account through the contract in §5. |
| **Message ref** | A stable, plugin-scoped ID for one message. It is opaque to the app. The RFC 822 `Message-ID` is also stored. |
| **Job** | One action the owner needs to take or approve. It references one or more messages. |
| **Verb** | The kind of action: `reply`, `forward`, `digest`, `snooze`, `follow_up`, `todo`, `archive_noise`, `unsubscribe`. |
| **Permission** | Per verb: `autonomous`, `ask`, or `never_auto`. |
| **Rule** | A stored, deterministic decision learned from the owner, e.g. "mail from this sender or list → this verb." Rules outrank the AI. |
| **Example** | A past owner decision. Examples are fed to the AI as context for similar mail. |
| **Privacy mode** | `full_cloud`, `redacted_cloud`, or later `local_only`. Applied before any content leaves the server. |

### Verbs (v1) and their default permissions **[Call]**

Every verb must remove at least one step, as listed in "What it does for the owner."

| Verb | What it does for the owner | Default | Highest allowed level |
|---|---|---|---|
| `reply` | Drafts a reply, or offers 2–3 drafted options (yes / no / later), in the owner's voice | ask | autonomous, but only to the original sender with no new recipients (see injection rules in §8) |
| `forward` | Drafts the forward and suggests a recipient from history | ask | ask (never autonomous: new recipients come from AI judgment) |
| `digest` | Groups several low-priority messages (e.g. newsletters) into one summary job; finishing it archives all of them | ask | autonomous |
| `snooze` | Hides the job until a date pulled from the email, then shows it again | ask | autonomous |
| `follow_up` | Reminds the owner if a sent reply gets no answer by a date | ask | autonomous |
| `todo` | A task outside email ("update this login") with the extracted link or deadline | ask | ask (completing it needs the owner) |
| `archive_noise` | Archives mail that doesn't need the owner | ask | autonomous |
| `unsubscribe` | Opens the sender's unsubscribe mechanism | never_auto | never_auto (links in email are untrusted) |

New verbs must be added to this table along with their "removes a step" rationale. **[Call]**

## 5. Mailbox plugin contract: `mailbox/1` over MCP **[Frank: MCP; Call: tool set]**

### 5.1 Principles
- **A plugin is an MCP server.** The app is an MCP client. No plugin code is imported into the app.
- **Plugins are listed in a config file,** one entry each (§5.4). Adding, swapping or removing a plugin is a config change plus a restart at most. Never a code change. **[Frank]**
- **The contract has no delete tool,** and no tool may permanently remove a message (e.g. by expunging). This is enforced by the conformance suite (§5.5). **[Frank via A1]**
- **The contract is versioned.** `mailbox_info` reports `contract_version`. The app refuses plugins with an unsupported major version and says so in the UI.

### 5.2 Tools

| Tool | Input | Output | Notes |
|---|---|---|---|
| `mailbox_info` | none | `contract_version`, `plugin_name`, `plugin_version`, `account` (address), `capabilities[]` (e.g. `push`, `repair`), `folders` (`inbox`, `archive`, `sent`) | Called on connect |
| `health` | none | `status` (`ok` / `degraded` / `down`); `checks[]` each with `{layer, ok, detail}`; `repair_actions[]` | Generic plugins return one check; Proton returns layered checks (§6) |
| `list_messages` | `folder` (`inbox` or `sent`), `cursor?`, `since?`, `limit` | `messages[]` (ref, Message-ID, from, to, cc, date, subject, snippet, `list_id?`, `in_reply_to?`), `next_cursor` | The cursor survives restarts, so a plugin that was offline can catch up. Reading `sent` supplies the owner's voice, forward-recipient history and `follow_up` for replies sent outside the app **[Call]** |
| `inbox_contains` | `refs[]` | `{ref: bool}` | Inbox-membership check used for sync (§5.3) **[Call]** |
| `get_message` | `ref` | headers, `text` body (converted from HTML if there's no text part), attachment metadata (name, type, size) | Attachment contents are not fetched in v1 |
| `archive` | `ref` | `{ok, verified}` | Must move the message to the archive location (Gmail: remove the INBOX label) **and** re-read to confirm. `verified=false` counts as failure |
| `restore` | `ref` | `{ok, verified}` | Moves the message back to the inbox. Used for undo |
| `send` | `to[]`, `cc[]`, `subject`, `body_text`, `in_reply_to_ref?` | `{ok, sent_message_id}` | Replies set `In-Reply-To` and `References` so the thread stays intact |
| `repair` (optional) | `action` | `{ok, detail}` | Only when the plugin lists the `repair` capability |

The exact JSON schemas, error codes and pagination details are **[Builder]**, within the rules above.

### 5.3 New-mail detection
- **The app polls `list_messages` with the stored cursor.** The default interval is 2 minutes, configurable. **[Call]**
- **Plugins can signal new mail instead.** A plugin with the `push` capability may send an MCP notification so the app polls immediately. For example, Proton could use IMAP IDLE if Bridge supports it: **[Builder: verify]**.
- **Target:** new mail shows up as a job within 5 minutes while the plugin is healthy. **[Call]**
- **First connect.** Only mail from the last 14 days becomes jobs, and noise in that window is never auto-archived on the first pass (all of it is `ask`). Older mail is left untouched in the inbox. The 14-day window is configurable. **[Call]**
- **Changes made outside the app.** Every poll, the app calls `inbox_contains` for messages with open jobs. When a message has left the inbox (archived on a phone, moved by a filter), its jobs close as "handled elsewhere," and nothing is archived twice. **[Call]**
- **The same message in two accounts** (e.g. Gmail forwards to Proton, or the owner is CC'd at both). Messages with the same `Message-ID` share one job. On done, the message is archived in every account where it is still in the inbox. **[Call]**
- **AI spend cap.** An optional monthly cap on AI calls. When it's reached, new mail falls back to the ask-owner card and the app warns once. No cap by default. **[Call]**

### 5.4 Plugin configuration
There is one file, e.g. `plugins.yaml`. **[Builder: format]** Each entry has:
- `id`
- `transport`: either `stdio` with a command and arguments, or `http` with a URL and a bearer-token reference
- `enabled`

Secrets (the Bridge password, OAuth tokens, plugin tokens) are referenced by name from environment variables or a secrets file outside the repo. Secrets are never stored inline. **[Call]**

### 5.5 Conformance suite
- **A test suite any plugin can be run against.** It covers every tool and checks that `archive` → `restore` is a round trip.
- **It proves no tool removes a message.** After running every tool, every seeded message still exists somewhere in the account.
- **It checks error shapes.**
- **A plugin is "supported" only when it passes.** The Proton and Gmail plugins must pass against a disposable test account or folder. **[Call]**

## 6. Proton plugin

### 6.0 Prior art on the owner's machine
`D:\protonmail-gateway` already runs the setup this plugin generalizes:
- **`protonmail_gateway.py`:** a stdlib REST gateway to Bridge over IMAP/SMTP, bound to loopback only.
- **`proton_mcp.py`:** a Streamable HTTP MCP adapter with a single-user OAuth 2.1 server, published through Tailscale Funnel as a claude.ai connector.
  - Tools: `health`, `list_folders`, `search_messages`, `read_message`, `send_message`, `reply_message`, `forward_message`, `mark_message`, `move_message`, `trash_message`.
  - It has no permanent delete.
- **`run_logged.pyw` plus two Task Scheduler tasks:** these run at logon, delayed so Bridge starts first, and the supervisor restarts the scripts if they crash. This is the reboot story §6.3 builds on.
- **Gap this design closes:** if Bridge itself is down, the gateway returns 502. Nothing diagnoses or restarts Bridge, and the client just sees "unreachable."
- **Decision: start fresh in this repo** (`plugins/proton/`), porting the proven pieces. **[Frank: "build on it if the background is good"; Call: fresh]** Reasons:
  - the gateway isn't version-controlled
  - its two-hop layout (REST gateway + MCP adapter + OAuth server) is heavier than one `mailbox/1` server
  - its MOVE fallback calls a folder-wide `EXPUNGE`, which can permanently remove unrelated messages flagged as deleted (violates A1)
- **Ported pieces:**
  - STARTTLS connect and the plain-language login and reachability errors
  - MUTF-7 folder-name decoding
  - plain/HTML body extraction
  - the Task Scheduler at-logon and supervisor pattern
- **Rules for the new plugin:**
  - any copy-and-delete fallback must use `UID EXPUNGE` scoped to the one message, or fail instead
- **Migration:** the existing claude.ai connector keeps running until the plugin replaces it.

### 6.1 Connection **[Frank: Proton-specific because of setup; Call: details]**
- **It talks to Proton Mail Bridge over IMAP and SMTP.** Bridge's defaults are 127.0.0.1, IMAP 1143 and SMTP 1025, both with STARTTLS. The username is the Proton address, and the password is the one Bridge generates, not the account password. **[Builder: verify current Bridge defaults]**
- **It trusts Bridge's self-signed certificate** by pinning the certificate Bridge exports. It does not disable verification wholesale.
- **It maps Proton's folder layout** (`Folders/…`, `Labels/…`, `Archive`, `All Mail`). `archive` means a move to `Archive`.
- **It runs on the Bridge machine.** Transport is stdio when the app is on the same machine, or HTTP bound only to the Tailscale interface when the app is on a VPS.

### 6.2 Guided setup
A checklist in the app's settings, with live checks:
1. Install Bridge.
2. Sign in to Bridge.
3. Copy Bridge's IMAP/SMTP settings and password.
4. Install the plugin and watchdog.
5. Test connection: each step goes green or shows the specific fix.

### 6.3 Diagnosis and self-healing **[Frank]**
- **Layered health checks.** In order:
  1. Is the Bridge machine reachable on the tailnet (remote mode only)?
  2. Does the plugin answer?
  3. Is Bridge's IMAP port open?
  4. Does IMAP login succeed?
  5. Does SMTP authentication succeed?

  The app shows the **first failing layer** in plain words, e.g. "Bridge isn't running on DESKTOP-X. Restarting it now."
- **A watchdog runs on the Bridge machine.** It is a separate, small, always-on process, installed as an OS service so it starts at boot regardless of the plugin. It:
  - checks Bridge and the plugin every 60 seconds **[Call]**
  - restarts whichever is down, waiting longer between each attempt (30 s, 1 m, 2 m, 5 m, then every 15 m) **[Call]**
  - exposes a token-protected status endpoint on the tailnet. The app uses it when the plugin itself is unreachable, which is how the app can tell "plugin down" from "machine down."
- **Supported OS:** Windows with Bridge on the Windows host, because that's the owner's setup. Bridge is a desktop app that runs in the user's session and keychain, so on Windows the watchdog is a scheduled task triggered at logon, not a system service. "After a reboot" therefore means "after the owner logs in," or Windows auto-logon if the owner enables it. **[Call]** If there's no extra cost, also Linux (systemd user unit) and macOS (launchd). Windows mechanism (service or Task Scheduler): **[Builder]**.
- **Escalation.** After repeated failed repairs, or on a failure only the owner can fix (Bridge needs re-login, keychain locked, Bridge update pending), the app stops retrying. It shows one specific instruction and re-checks automatically once the owner acts.
- **Catch-up.** When the plugin recovers, mail is picked up from the stored cursor. Nothing is lost or duplicated (duplicates are detected by message ref plus Message-ID).
- **Proton only.** Other plugins report `health` without repair. **[Frank]**

## 7. Gmail plugin **[Frank: IMAP, so every mail plugin works the same way]**
- **Access:** IMAP (`imap.gmail.com:993`) and SMTP (`smtp.gmail.com:587` or `465`), signing in with the account address and a Google **app password**. The account needs 2-Step Verification.
- **Archive** means `UID MOVE` from `INBOX` to `[Gmail]/All Mail`, i.e. removing the Inbox label. **Restore** moves it back. The plugin uses the Gmail IMAP extensions:
  - `X-GM-MSGID` for stable refs
  - `X-GM-THRID` for threads
  - `X-GM-LABELS` for verification
- **Gmail's "auto-expunge" setting:** setup checks it and warns if it's set so that deleting from a folder could remove mail. The plugin never issues `EXPUNGE` anyway.
- **New mail:** polling, with IDLE as the `push` capability.
- **Nothing is lost compared with the Gmail API for v1:**
  - labels, threads and search (`X-GM-RAW`) are all available over IMAP
  - Pub/Sub push is unusable without a public endpoint anyway
- **Fallback if app passwords stop being available** for an account (Advanced Protection, or a Workspace admin policy): OAuth (XOAUTH2) **over the same IMAP/SMTP connection**. That only changes the sign-in, not the plugin. **[Call]**

## 8. AI pipeline

```
message → minimize → (redact if redacted_cloud) → rules → AI proposal (structured)
        → validate (grounding, specificity, schema, injection) → job | ask-owner
```

1. **Minimize** (in both modes). Strip quoted history, signatures, tracking links and pixels, and cap the length. **[Call]**
2. **Redact** (redacted_cloud only). Deterministic, on the server:
   - names, email addresses, phone numbers, account and card numbers, URLs and one-time codes become typed placeholders (`PERSON_1`, `URL_2`, …)
   - the mapping stays on the server, and placeholders in the AI's output are replaced with the real values
   - library choice (e.g. Microsoft Presidio) is **[Builder]**

   It is one pipeline stage, independent of plugins, so `local_only` can later swap the provider without touching the rest. **[Frank: redacted optional, full default]**
3. **Rules first.** If a stored rule matches, its verb wins and the AI is only used to fill in details such as the draft text. **[Frank via A2]**
4. **AI proposal.** The provider is set in config, with Claude (current model) as the default. **[Call]**
   - The AI returns a structured result: `needs_owner` (bool), `verb`, `title` (specific), `evidence[]` (verbatim quotes), `draft?`, `options?`, `due?`, `confidence`.
   - Similar past examples are included as context. Similarity method: **[Builder]**.
5. **Validate.** Deterministic, after the AI:
   - **Grounding:** every `evidence` quote must appear in the message text (after minimizing and, in redacted mode, with placeholders swapped back).
   - **Specificity:** the job must carry at least one step-saving artifact (draft, options, extracted link or deadline, digest content, or a noise rationale). A bare verb with nothing attached is rejected.
   - **Injection:** email content is untrusted. Autonomous actions can't send to recipients or open links that came from email content, except for replying to the original sender. Instructions inside the email are never followed as instructions.

   If validation fails, the owner is asked "What do you want to do with this?". The app never guesses. **[Frank via A3]**

## 9. Permissions **[Frank: per-verb, three levels; Call: details]**
- **Storage.** One setting per verb, kept as a readable, editable file (e.g. `permissions.yaml`) and mirrored on a settings screen. The two stay in sync.
- **Unknown or new verbs** default to `ask`.
- **Promotion is offered, never automatic.** After 10 approvals in a row of the same verb with no edits **[Call]**, the app offers to make that verb autonomous. It never promotes on its own.
- **Ceilings.** The "Highest allowed level" column in §4 can't be exceeded.
- **History and undo.** Every action, autonomous or approved, is written to the history (§10.6) with undo where possible: `restore` after an archive. A sent email can't be unsent; the history says so.

## 10. Features

**Platform.** A mobile-first web app that also works well on desktop (Next.js), backed by FastAPI and MongoDB. **[Call]** UI follows the owner's standards: Shadcn/UI, Tailwind, Hugeicons. lucide-react is replaced. **[Call]**

1. **Job queue (home screen).** Open jobs, newest or most urgent first. Each card shows:
   - the specific title and the sender
   - the evidence quote
   - the step-saving artifact (draft, options, digest or link)
   - one-tap approve, edit, choose another action, or dismiss
2. **Ask-owner card.** For mail with no confident, valid proposal, the card shows the message gist and the suggested verbs with "something else." The owner's choice becomes an example, and optionally a rule ("always do this for this sender or list").
3. **Archive on done.** A message is archived only when **every** job that references it has reached a final state (done or dismissed) **and** the action succeeded (the send returned ok). The archive must be verified. **[Frank via A2]**
4. **Corrections.** On any job the owner can choose "wrong action," "this is noise," or "this isn't noise." A correction creates or updates a rule that takes effect on the next matching message. Restoring an archived message counts as a "this isn't noise" correction.
5. **Noise handling.** Mail judged not to need the owner either becomes an `archive_noise` job or is pulled into a `digest`, subject to permissions. A "Filtered" view shows everything handled as noise in the last 30 days, with one-tap restore. **[Call]**
6. **History.** A timeline of every action (what, which message, by app or owner, permission level used, result) with undo where possible.
7. **Calibration and test set.** **[Frank: AI tags first, owner reacts]**
   - "Calibrate" takes a sample of recent mail (default 100 **[Call]**) and runs the pipeline in dry-run mode: no actions are taken.
   - The owner reacts to each proposal: 👍, a fix, or "noise." This uses the same card as the ask-owner flow.
   - Reactions become (a) examples and rules and (b) a stored test set.
   - The test set holds real mail. It stays local and is never committed (gitignored path). **[Call]**
8. **Connections screen.** One row per plugin with its health status, the first failing layer, the repair in progress and the last successful sync.
9. **Settings.** Privacy mode, the AI provider and model, the poll interval and permissions.
10. **Authentication.** Better Auth in the Next.js app. **[Frank]**
    - First run creates the single owner account, and sign-up is then disabled.
    - FastAPI verifies Better Auth–issued tokens against Better Auth's public keys. It never trusts a caller-supplied user ID. **[Call; Builder: verify Better Auth JWT/JWKS plugin API before use]**
    - Passkey support is optional and nice to have. **[Call]**

## 11. Acceptance criteria

Written as Given / When / Then. Each maps to a pytest-bdd or Playwright scenario. **[Call]**

### Anti-goal A1: never lose mail
- **AC-1.1** **Given** any plugin, **when** the conformance suite runs every tool, **then** every seeded message still exists in the account.
- **AC-1.2** **Given** the plugin contract, **then** no tool named or behaving like delete or expunge exists, and the app source has no code path that permanently removes a message.
- **AC-1.3** **Given** `archive` returns `verified=false`, **then** the job stays open, the message stays in the inbox and the owner sees an error naming the plugin.

### Anti-goal A2: archive only when handled, and corrections stick
- **AC-2.1** **Given** a message referenced by two jobs, **when** one job is done, **then** the message stays in the inbox until the second job is done or dismissed.
- **AC-2.2** **Given** an approved `reply` whose `send` fails, **then** the message is not archived and the job shows "send failed — retry."
- **AC-2.3** **Given** the owner corrects a message from sender S to "noise," **when** another message from S arrives with similar content, **then** it is handled as noise, and this holds across 10 repeats.
- **AC-2.4** **Given** the owner restores a message the app archived, **then** a rule is created that prevents archiving the next similar message without asking.

### Anti-goal A3: specific, step-saving suggestions
- **AC-3.1** **Given** any created job, **then** every evidence quote appears verbatim in the source message.
- **AC-3.2** **Given** any non-noise job, **then** it carries at least one step-saving artifact (§8 step 5). Jobs without one are never shown; the ask-owner card appears instead.
- **AC-3.3** **Given** the test set, **then**:
  - no single verb accounts for more than 50% of non-noise proposals **[Call: threshold]**
  - at least 70% of non-noise proposals are accepted unchanged or with only a draft edit **[Call: threshold]**
- **AC-3.4** **Given** a message with no meeting or time language, **then** no job involving scheduling is proposed. Spot-checked through the test set.

### Anti-goal A4: noise filtering
- **AC-4.1** **Given** the test set, **then** at most 2% of messages the owner marked "needs me" are classified as noise. **[Call: threshold]**
- **AC-4.2** **Given** the test set after calibration corrections, **then** at least 80% of owner-marked noise is classified as noise. **[Call: threshold]**
- **AC-4.3** Both metrics are reported by one command, and CI runs it against a committed **synthetic** test set. The owner's real test set is only used locally.

### Proton self-healing
- **AC-P.1** **Given** Bridge is stopped, **when** the watchdog's next check runs, **then** Bridge is restarted and the app shows "Bridge restarted" with no owner action. Mail resumes within 5 minutes.
- **AC-P.2** **Given** the plugin process is killed, **then** the watchdog restarts it, and the app's Connections screen shows "plugin down → restarting" (not a generic error) in the meantime.
- **AC-P.3** **Given** the Bridge machine is offline, **then** the app shows "machine offline," not "Bridge down." When the machine returns, it catches up from the cursor with no duplicates and no missed mail.
- **AC-P.4** **Given** Bridge needs re-login, **then** the app shows exactly that instruction, stops automatic restarts and re-checks within 1 minute after the owner fixes it.
- **AC-P.5** **Given** the machine reboots and the owner's session starts (manual login or auto-logon), **then** the watchdog, Bridge and the plugin are all running again without any further owner action. Until then, the app shows "waiting for login on <machine>."

### Permissions
- **AC-K.1** **Given** `reply: ask`, **then** no reply is sent without an owner tap.
- **AC-K.2** **Given** `archive_noise: autonomous`, **then** noise is archived without a tap and appears in History and Filtered with a working undo.
- **AC-K.3** **Given** an attempt to set `unsubscribe` or `forward` to `autonomous` (in the file or the UI), **then** it is rejected with the ceiling explained.
- **AC-K.4** **Given** 10 approvals in a row of a verb with no edits, **then** promotion is offered once, and the setting doesn't change unless the owner accepts.

### Privacy
- **AC-R.1** **Given** `redacted_cloud`, **then** the outgoing AI request (captured in tests) contains no email addresses, phone numbers, URLs or names from the seeded message, and the job shown to the owner contains the real values.
- **AC-R.2** **Given** `full_cloud`, **then** behavior matches the minimized content only (no quoted history or signatures).

### Plugins and contract
- **AC-C.1** **Given** a new plugin entry in the config, **when** the app restarts, **then** the plugin appears on Connections with no code change.
- **AC-C.2** **Given** a plugin reporting an unsupported `contract_version`, **then** the app refuses it and shows why.
- **AC-C.3** **Given** both v1 plugins, **then** both pass the conformance suite.

### Auth
- **AC-A.1** **Given** no session, **then** every API route except health and auth returns 401. No route accepts `user_id` from the request.
- **AC-A.2** **Given** an owner already exists, **then** sign-up is unavailable.

## 12. Platform modernization

**Already done (2026-10-31):**
- Dependabot PRs #10–#19 resolved.
- #23 merged:
  - shadcn removed from runtime deps
  - pymongo, certifi and dnspython upgraded
  - deploy workflow on Node 24
- `npm audit`: 0 high or critical findings.
- `pip-audit`: clean.

**In scope for v1:**
- **Remove the forwarding ingestion stack:**
  - MailSlurp (`mailslurp-client`, `mailbox_provisioning.py`, `onboarding.py`, `email_retrieval_utils.py`)
  - the `/email/incoming` webhook and webhook-security admin UI
  - the `?user_id` mechanism and `ForwardingInstructionsModal`
  - Reusable pieces (duplicate detection, summarizer fallbacks) may be kept if they fit the pipeline. **[Builder]**
- **Database driver:** Motor → PyMongo's async API, and Beanie → 2.x. Motor is deprecated. **[Builder: verify Beanie 2 + PyMongo async compatibility]**
- **AI provider:** replace the direct OpenAI client with a provider interface, defaulting to Anthropic. `gpt-3.5-turbo` is retired.
- **Frontend dependencies:**
  - remove unused `add`, `input` and `mongodb`
  - pick one toast library (sonner) and drop `react-toastify`
  - lucide-react → Hugeicons
- **Open issues to fix along the way:** #4 (backend test failures), #8 (lint broken / not in CI), #24 (deploy).
- **Hosting:** **[Frank]**
  - **AWS is retired.** Its SSH deploy workflows are removed.
  - **The app ships as Docker Compose** (backend + frontend) for a Docker host on the tailnet, or for the owner's machine.
  - **MongoDB Atlas is the default database,** set by `MONGODB_URI`. An optional Compose profile runs MongoDB locally for people who don't want Atlas.
  - **Atlas means stored mail content leaves the owner's machines.** The owner accepts this. The privacy modes cover only what is sent to AI providers, and the docs say so.
- **CI:** backend tests, frontend tests, lint, type-check and the conformance suite (against a mock IMAP/SMTP server in CI) run on every PR. GitHub Actions move to current major versions.
- **Docs:**
  - rewrite `AI_GUIDELINES.md`: uv instead of Poetry; correct paths; add security, secrets, prompt-injection and privacy guidance
  - update the README to the new architecture

## 13. Suggested milestones **[Call; order is Builder's to refine]**
- **M0, foundation:** auth, dependency and driver migration, CI green (#4, #8), removal of forwarding ingestion.
- **M1, contract:** `mailbox/1`, the conformance suite and the Proton plugin with watchdog. Proton is the owner's primary mailbox.
- **M2, jobs:** the job pipeline (minimize → rules → AI → validate), job queue, archive-on-done, permissions and history.
- **M3, learning:** corrections, rules and examples, ask-owner cards, calibration and the test-set metrics.
- **M4, Gmail:** the Gmail plugin.
- **M5, privacy:** redacted cloud mode.
- **v1 ships** when every AC in §11 passes.

## 14. Later (after v1)
- Local-only AI mode.
- Outlook and generic IMAP plugins.
- A sender × action permission matrix.
- Multi-user and multi-tenant.
- Push notifications.
- Calendar-aware scheduling.
- Reading attachments.

## 15. Resolved decisions (2026-11-01)
- **Gmail:** IMAP with an app password (§7). **[Frank]**
- **Proton plugin:** written fresh in this repo, porting proven gateway pieces (§6.0). **[Frank: delegated; Call]**
- **Hosting:** no AWS; Docker Compose on a Docker host; MongoDB Atlas by default (§12). **[Frank]**

## 16. Left to the builder
- Exact MCP tool schemas and error codes.
- Config file formats.
- The similarity method for examples and rules.
- The redaction library.
- The Windows service mechanism for the watchdog.
- Job ordering.
- UI layout details within the standards above.
- Whether generic IMAP code is shared with the Proton plugin.
