# Proton mailbox plugin

`mailbox/1` plugin for Proton Mail through **Proton Mail Bridge**, built on the reference
IMAP/SMTP plugin (`packages/imap-mailbox`). It runs on the machine where Bridge runs.

## Setup

1. In Bridge, open the account's mailbox settings and note the **username and mailbox
   password** Bridge shows (not your Proton password), plus the IMAP/SMTP ports and their
   security (defaults: IMAP 1143, SMTP 1025, STARTTLS).
2. In Bridge, **Settings → Export TLS certificates**, and save `cert.pem`. The plugin pins
   it; certificate verification is never disabled.
3. Set the environment (secrets come from env vars, never from `plugins.yaml`):

| Variable | Meaning |
|---|---|
| `MAILBOX_ACCOUNT` | Your Proton address |
| `MAILBOX_USERNAME`, `MAILBOX_PASSWORD` | The Bridge username and mailbox password |
| `MAILBOX_CA_CERT_PATH` | Path to Bridge's exported `cert.pem` (required) |
| `MAILBOX_IMAP_PORT`, `MAILBOX_SMTP_PORT` | Bridge's ports if not 1143/1025 |
| `MAILBOX_TLS` (or `MAILBOX_IMAP_TLS`/`MAILBOX_SMTP_TLS`) | `starttls` (default) or `ssl`, matching Bridge |
| `MAILBOX_HTTP_HOST`, `MAILBOX_HTTP_PORT`, `MAILBOX_HTTP_TOKEN` | HTTP mode only: this machine's Tailscale IP, a port, and the bearer token the app sends |
| `MAILBOX_BRIDGE_RESTART_COMMAND` | Optional JSON list that restarts Bridge, e.g. `["systemctl", "--user", "restart", "proton-bridge"]`. Turns on the `repair` tool |

## Health and repair

`health` checks these layers in order and stops at the first failure, which is the one
the app shows: **plugin** answering → **imap_port** (Bridge listening) → **imap_login** →
**smtp_auth** → **folders** (Archive and Sent exist).

- A stopped Bridge or unreachable SMTP is **restartable**: with
  `MAILBOX_BRIDGE_RESTART_COMMAND` set, `repair_actions` offers `restart_bridge`. `repair`
  runs only that configured command, then waits for Bridge to answer again.
- A rejected login is **owner-only**: no repair is offered. The detail tells the owner what
  to do in Bridge (re-enter the mailbox password, sign in again, finish an update or
  unlock the keychain).

## Running

- **stdio** (the app starts it on the same machine): `python -m proton_plugin.server`
- **HTTP on the tailnet** (the app runs elsewhere): `python -m proton_plugin.server http`.
  It binds only to `MAILBOX_HTTP_HOST` (`0.0.0.0` is refused) and rejects requests
  without `Authorization: Bearer $MAILBOX_HTTP_TOKEN`. In the app's `plugins.yaml`:
  `transport: {type: http, url: http://<tailscale-ip>:8765/mcp, bearer_token_env: PROTON_PLUGIN_TOKEN}`.

Failures are reported in plain words, e.g. "Proton Bridge isn't answering IMAP at
127.0.0.1:1143. Is Bridge running and signed in?" or "Bridge's IMAP certificate doesn't
match the pinned one … Export it again from Bridge".
