# `mailbox/1`: the mailbox plugin contract

contract_version: `1.0`

A mailbox plugin is an **MCP server**; the app is an MCP client and never imports plugin
code. Every tool below is an MCP tool. Inputs are the tool's arguments, and outputs are the
tool result's `structuredContent`. Design rationale: spec §5
(`docs/specs/2026-11-01-email-assistant-v1-design.md`).

- **Source of truth:** the pydantic models in `packages/mailbox-contract`
  (`mailbox_contract`), which both the app and the plugins validate against. The JSON
  schemas in [`mailbox-1/`](mailbox-1/) are generated from them
  (`packages/mailbox-contract/write_schemas.py`), and a backend test fails if they drift.
- **Strict shapes:** unknown fields are rejected in both directions (the one map-shaped
  output, `inbox_contains`, is checked against the request instead).
- **Nothing is ever permanently removed.** The contract has no tool that deletes a
  message, and no tool may expunge, purge or empty a folder as a side effect. `archive`
  moves; it never removes. The conformance suite (#41) proves every seeded message still
  exists after every tool has run.

## Versions

`mailbox_info.contract_version` is `MAJOR.MINOR`.

- **Minor** versions only add: new optional input fields, new output fields, new optional
  tools or capabilities. A plugin at `1.3` works with an app built for `1.0`.
- **Major** versions may break. The app refuses a plugin whose major version differs from
  its own and says why on the Connections screen (`mailbox_contract.is_supported`).

## Refs and cursors

- **`ref`** is an opaque string chosen by the plugin. It must stay stable for a message
  while the message exists, including after `archive`/`restore` moves it (IMAP: a UID
  plus UIDVALIDITY tracked across folders; Gmail: `X-GM-MSGID`). The app never parses it.
- **`list_messages` cursors** are opaque and must survive plugin and app restarts. The app
  persists `next_cursor` and passes it back, so a plugin that was offline catches up from
  where it stopped. Every call returns a `next_cursor`, even an empty page, and the app
  stores it. Paging: call again with `next_cursor` while `has_more` is true. Messages come
  oldest first within a page. A cursor that the plugin can no longer resume (for example
  because UIDVALIDITY changed) yields the `invalid_cursor` error, and the app restarts from
  `since`.
- **Deduplication:** the app treats a (`ref`, `message_id`) pair it has already seen as a
  duplicate, so re-delivering a message after a restart is harmless.

## Errors

A failed call is an MCP tool result with `isError: true` and this `structuredContent`
([`ToolError`](mailbox-1/ToolError.schema.json)):

```json
{"code": "unavailable", "message": "Bridge isn't running.", "retryable": true}
```

`retryable` is fixed by `code` (the models reject a mismatch):

| `code` | Meaning | `retryable` |
|---|---|---|
| `invalid_argument` | Input failed validation | false |
| `not_found` | No message with that `ref` | false |
| `invalid_cursor` | The cursor can't be resumed; restart from `since` | false |
| `unavailable` | The mail backend (Bridge, IMAP, SMTP) can't be reached | true |
| `auth_failed` | The backend rejected the credentials | false |
| `rate_limited` | The backend is throttling; retry later | true |
| `unsupported` | The tool or action isn't offered (e.g. `repair` without the capability) | false |
| `internal` | A bug in the plugin | true |

`message` is plain words the app can show the owner. It never contains credentials or
message bodies. `archive` and `restore` report an unconfirmed move as
`{"ok": true, "verified": false}`, not as an error, and the app treats that as a failure.

## Tools

### `mailbox_info`

Called on connect. Input: none ([`Empty`](mailbox-1/Empty.schema.json)).
Output: [`MailboxInfo`](mailbox-1/MailboxInfo.schema.json): `contract_version`,
`plugin_name`, `plugin_version`, `account` (the mailbox address), `capabilities` (`push`,
`repair`) and `folders` (the plugin's names for `inbox`, `archive` and `sent`).

### `health`

Input: none. Output: [`Health`](mailbox-1/Health.schema.json): `status` (`ok`, `degraded`,
`down`), the ordered `checks[]` (`{layer, ok, detail}`; the app shows the first failing
layer), and `repair_actions[]` accepted by `repair`. Generic plugins return a single check;
Proton returns layered ones (spec §6.3).

### `list_messages`

Input: [`ListMessagesInput`](mailbox-1/ListMessagesInput.schema.json): `folder` (`inbox` or
`sent`), `cursor?`, `since?` (used only without a cursor), `limit` (1–500, default 100).
Output: [`ListMessagesOutput`](mailbox-1/ListMessagesOutput.schema.json): `messages[]` (ref,
message_id, from, to, cc, date, subject, snippet, `list_id?`, `in_reply_to?`),
`next_cursor`, `has_more`.

### `inbox_contains`

Input: [`InboxContainsInput`](mailbox-1/InboxContainsInput.schema.json): `refs[]` (1–500).
Output: [`InboxContainsOutput`](mailbox-1/InboxContainsOutput.schema.json): an object that
maps every requested ref to whether the message is still in the inbox. An unknown ref
maps to `false`, not to an error. The keys must be exactly the requested refs: a schema
can't express that, so the app and the conformance suite check it. The app uses this to
close jobs handled elsewhere.

### `get_message`

Input: [`MessageRef`](mailbox-1/MessageRef.schema.json). Output:
[`MessageDetail`](mailbox-1/MessageDetail.schema.json): the summary fields plus `headers[]`
(`{name, value}`, in order, repeats allowed), `text` (plain text, converted from HTML when
there's no text part) and `attachments[]` metadata (`name`, `content_type`, `size`).
Attachment contents aren't fetched in v1.

### `archive`

Input: [`MessageRef`](mailbox-1/MessageRef.schema.json). Output:
[`MoveResult`](mailbox-1/MoveResult.schema.json) `{ok, verified}`. Moves the message to the
archive location (Gmail: remove the INBOX label) **and re-reads to confirm**.
`verified: false` is a failure. Never deletes, never expunges.

### `restore`

Input: [`MessageRef`](mailbox-1/MessageRef.schema.json). Output:
[`MoveResult`](mailbox-1/MoveResult.schema.json). Moves the message back to the inbox and
confirms. Used for undo.

### `send`

Input: [`SendInput`](mailbox-1/SendInput.schema.json): `to[]` (at least one), `cc[]`,
`subject`, `body_text`, `in_reply_to_ref?`. Output:
[`SendResult`](mailbox-1/SendResult.schema.json) `{ok, sent_message_id}`. A reply sets
`In-Reply-To` and `References` from the referenced message so the thread stays intact.

### `repair`

Optional: offered only when `capabilities` contains `repair`. Input:
[`RepairInput`](mailbox-1/RepairInput.schema.json) `{action}`, one of
`health.repair_actions`. Output: [`RepairResult`](mailbox-1/RepairResult.schema.json)
`{ok, detail}`.

## Conformance suite

A plugin is **supported** only when it passes `backend/tests/conformance/` (spec §5.5):
every tool, cursor paging that survives a restart, the `archive` → `restore` round trip,
`inbox_contains` answering exactly the requested refs, error shapes, a threaded reply,
and **after every tool has run, every seeded message still exists** (AC-1.1). A static
check fails on any unscoped expunge in the app, packages or plugins, and on any
delete-like tool name (AC-1.2).

Run it with the test services up (`docker compose -f docker-compose.test.yml up -d`):

```bash
cd backend
uv run pytest tests/conformance
```

It runs against each entry in `TARGETS` (a plugin config, plus mail seeded on the
GreenMail test server). The reference IMAP/SMTP plugin, `packages/imap-mailbox`, is the
first target. Each plugin adds its own.

## Reference plugin: `packages/imap-mailbox`

`mailbox/1` over any IMAP/SMTP server; the Proton and Gmail plugins build on it. It's
configured from `MAILBOX_*` environment variables (`MAILBOX_ACCOUNT`, `MAILBOX_USERNAME`,
`MAILBOX_PASSWORD`, `MAILBOX_IMAP_HOST`/`PORT`, `MAILBOX_SMTP_HOST`/`PORT`, `MAILBOX_TLS`
= `ssl`/`starttls`/`none`, `MAILBOX_CA_CERT_PATH` to pin a CA, `MAILBOX_FOLDER_*`,
`MAILBOX_APPEND_SENT`), and runs over stdio with `python -m imap_mailbox.server`, or
Streamable HTTP with `python -m imap_mailbox.server http <port>`.
Refs are `Message-ID`s (stable across moves). Moves use `MOVE`, or `COPY` + `UID EXPUNGE`
of that one message, and are re-read before they count as verified.
