# Gmail mailbox plugin

`mailbox/1` plugin for Gmail over IMAP (`imap.gmail.com:993`, TLS) and SMTP
(`smtp.gmail.com:465`, or `587` with STARTTLS), signing in with the address and a Google
**app password**. Built on the reference IMAP/SMTP plugin (`packages/imap-mailbox`); the app
starts it over stdio.

## Settings

Secrets come from environment variables, never from `plugins.yaml` (which names them with
`env_from`):

| Variable | Meaning |
|---|---|
| `MAILBOX_ACCOUNT` | The Gmail address (also the IMAP/SMTP username) |
| `MAILBOX_PASSWORD` | An app password (needs 2-Step Verification), not your Google password |
| `MAILBOX_SMTP_PORT` | `465` (default, TLS) or `587` (STARTTLS, picked automatically) |
| `MAILBOX_FOLDER_ARCHIVE`, `MAILBOX_FOLDER_SENT` | Only if Gmail's folders aren't `[Gmail]/All Mail` and `[Gmail]/Sent Mail` (other interface languages, `[Google Mail]` accounts) |

Unencrypted connections are refused.

## How it maps Gmail

- **Refs** are Gmail's `X-GM-MSGID`, which never changes when labels do. `get_message`'s
  headers include `X-GM-MSGID` and `X-GM-THRID` (Gmail's thread id) as the server reports them;
  copies of those headers inside the mail itself are replaced.
- **Archive** is `UID MOVE` from `INBOX` to `[Gmail]/All Mail` (removing the Inbox label), and
  counts only when `X-GM-LABELS` no longer lists `\Inbox`.
- **Restore** copies the message from All Mail back to `INBOX` (adding the label) and counts only
  when `X-GM-LABELS` lists `\Inbox` again. It never moves anything out of All Mail, and the plugin
  never issues `EXPUNGE`: in Gmail either can send mail to the Trash.
- **Push**: the plugin keeps an IMAP IDLE on the inbox and publishes `mailbox://inbox` on new
  mail, so the app polls at once instead of waiting for its interval.

## Setup checklist

Connections → **Setup checklist** walks through 2-Step Verification, the app password, IMAP and
the connection, and checks Gmail's **Auto-Expunge** setting (Settings → Forwarding and POP/IMAP).
IMAP doesn't report that setting, so the check (the plugin's `setup_warnings` tool, run only when
the owner checks setup) appends one probe message to the Trash, marks only that message deleted,
and sees whether Gmail drops it at once. If it does, Auto-Expunge is on and the checklist warns;
otherwise the probe stays in the Trash, which Gmail empties after 30 days. No other message is
touched, and the plugin still never issues `EXPUNGE`. The Trash is found by its SPECIAL-USE flag,
so other interface languages work.

Live check (GreenMail has no such setting), against an account whose setting you know:

```bash
cd backend
GMAIL_ADDRESS=… GMAIL_APP_PASSWORD=… GMAIL_AUTO_EXPUNGE=on uv run pytest tests/plugins/test_gmail_setup_live.py -rs
```

Run it once with Auto-Expunge on and once with it off (`GMAIL_AUTO_EXPUNGE=off`).

## Running

The plugin is a runtime dependency of the backend, so its `gmail-plugin` script is on the backend's
path, both in the Docker image and under `uv run` locally. In `plugins.yaml`:

```yaml
- id: gmail
  transport:
    type: stdio
    command: gmail-plugin
    env_from:
      MAILBOX_ACCOUNT: GMAIL_ADDRESS
      MAILBOX_PASSWORD: GMAIL_APP_PASSWORD
```

## Conformance

The CI mail server has no Gmail extensions, so the Gmail half of the conformance suite runs
live, against a **disposable** account (the suite archives everything in its inbox before each
test, and sends mail to itself):

```bash
cd backend
GMAIL_ADDRESS=… GMAIL_APP_PASSWORD=… uv run pytest tests/conformance -k gmail -rs
```

Without those variables the Gmail target is skipped.
