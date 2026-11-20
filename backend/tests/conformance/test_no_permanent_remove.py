# AC-1.2: no tool is named or behaves like delete/expunge, and no source path can
# permanently remove a message. Expunging is allowed only as UID EXPUNGE of the one
# message just copied elsewhere (the COPY fallback for servers without MOVE).
import io
import re
import tokenize
from pathlib import Path

from imap_mailbox.mailbox import ImapMailbox
from imap_mailbox.server import build_server
from imap_mailbox.settings import ImapMailboxSettings
from mcp import Client

REPO = Path(__file__).resolve().parents[3]
SCANNED = [REPO / "backend" / "app", REPO / "packages", REPO / "plugins"]
EXPUNGE_COMMAND = re.compile(r"\s*EXPUNGE\b", re.IGNORECASE)
DESTRUCTIVE_NAME = re.compile(r"delete|expunge|purge|remove|destroy|trash", re.IGNORECASE)


def permanent_remove_paths(source: str) -> list[str]:
    """Unscoped expunges in Python source: `.expunge(` calls, or an EXPUNGE string that
    isn't the command of a `.uid("EXPUNGE", …)` call."""
    tokens = [t for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type != tokenize.COMMENT]
    problems = []
    for index, token in enumerate(tokens):
        previous = [t.string for t in tokens[max(0, index - 3) : index]]
        if token.type == tokenize.NAME and token.string.lower() == "expunge" and previous[-1:] == ["."]:
            problems.append(f"line {token.start[0]}: .{token.string}() expunges the whole folder")
        # A command literal starts with EXPUNGE; prose in docstrings doesn't count.
        if token.type == tokenize.STRING and EXPUNGE_COMMAND.match(token.string.strip("\"'")):
            if previous[-3:] != [".", "uid", "("]:
                problems.append(f"line {token.start[0]}: EXPUNGE outside a UID-scoped call")
    return problems


def test_detector_flags_unscoped_expunge():
    assert permanent_remove_paths("connection.expunge()\n")
    assert permanent_remove_paths('connection.xatom("EXPUNGE")\n')
    assert not permanent_remove_paths('connection.uid("EXPUNGE", uid)\n# EXPUNGE in a comment\n')
    assert not permanent_remove_paths('"""No tool deletes or expunges a message."""\n')


def test_no_source_path_permanently_removes_a_message():
    problems = {
        str(path.relative_to(REPO)): found
        for root in SCANNED
        if root.exists()
        for path in sorted(root.rglob("*.py"))
        if ".venv" not in path.parts and (found := permanent_remove_paths(path.read_text()))
    }
    assert problems == {}


async def test_reference_plugin_offers_no_destructive_tool():
    settings = ImapMailboxSettings(account="a@example.com", username="a", password="unused")
    async with Client(build_server(ImapMailbox(settings))) as client:
        names = [tool.name for tool in (await client.list_tools()).tools]

    assert names and not [name for name in names if DESTRUCTIVE_NAME.search(name)]
