# The mailbox/1 contract: committed JSON schemas, the pydantic models and the doc must agree.
import json
import re
from pathlib import Path

import jsonschema
import pytest
from pydantic import BaseModel, ValidationError

import mailbox_contract as contract

CONTRACT_DIR = Path(__file__).resolve().parents[3] / "docs" / "contracts"
SCHEMA_DIR = CONTRACT_DIR / "mailbox-1"
DOC = CONTRACT_DIR / "mailbox-1.md"

MESSAGE = {
    "ref": "INBOX/42",
    "message_id": "<abc@example.com>",
    "from": {"name": "Ana", "email": "ana@example.com"},
    "to": [{"name": None, "email": "owner@example.com"}],
    "cc": [],
    "date": "2026-11-01T09:30:00Z",
    "subject": "Q3 budget",
    "snippet": "Can we meet Thursday?",
    "list_id": None,
    "in_reply_to": None,
}

# One realistic payload per model, as a plugin or the app would put it on the wire.
EXAMPLES: dict[type[BaseModel], dict[str, object]] = {
    contract.MailboxInfo: {
        "contract_version": "1.0",
        "plugin_name": "proton",
        "plugin_version": "0.1.0",
        "account": "owner@example.com",
        "capabilities": ["push", "repair"],
        "folders": {"inbox": "INBOX", "archive": "Archive", "sent": "Sent"},
    },
    contract.Health: {
        "status": "degraded",
        "checks": [
            {"layer": "plugin", "ok": True, "detail": "answering"},
            {"layer": "imap_login", "ok": False, "detail": "Bridge rejected the login"},
        ],
        "repair_actions": ["restart_bridge"],
    },
    contract.ListMessagesInput: {"folder": "inbox", "cursor": "c-17", "since": None, "limit": 50},
    contract.ListMessagesOutput: {"messages": [MESSAGE], "next_cursor": "c-18", "has_more": False},
    contract.InboxContainsInput: {"refs": ["INBOX/42", "INBOX/43"]},
    contract.InboxContainsOutput: {"INBOX/42": True, "INBOX/43": False},
    contract.MessageRef: {"ref": "INBOX/42"},
    contract.MessageDetail: {
        **MESSAGE,
        "headers": [{"name": "Received", "value": "from mx1"}, {"name": "Received", "value": "from mx2"}],
        "text": "Can we meet Thursday at 3pm?",
        "attachments": [{"name": "agenda.pdf", "content_type": "application/pdf", "size": 2048}],
    },
    contract.MoveResult: {"ok": True, "verified": True},
    contract.SendInput: {
        "to": [{"name": "Ana", "email": "ana@example.com"}],
        "cc": [],
        "subject": "Re: Q3 budget",
        "body_text": "Thursday at 3 works.",
        "in_reply_to_ref": "INBOX/42",
    },
    contract.SendResult: {"ok": True, "sent_message_id": "<reply@example.com>"},
    contract.RepairInput: {"action": "restart_bridge"},
    contract.RepairResult: {"ok": True, "detail": "Bridge restarted"},
    contract.ToolError: {"code": "unavailable", "message": "Bridge isn't running.", "retryable": True},
    contract.Empty: {},
}

MODELS = sorted(
    {tool.input for tool in contract.TOOLS.values()}
    | {tool.output for tool in contract.TOOLS.values()}
    | {contract.ToolError},
    key=lambda model: model.__name__,
)


def schema_path(model: type[BaseModel]) -> Path:
    return SCHEMA_DIR / f"{model.__name__}.schema.json"


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_committed_schema_matches_model(model):
    # Regenerate with: uv run python ../packages/mailbox-contract/write_schemas.py
    committed = json.loads(schema_path(model).read_text())
    assert committed == model.model_json_schema(by_alias=True)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_example_round_trips_through_schema_and_model(model):
    example = EXAMPLES[model]
    schema = json.loads(schema_path(model).read_text())

    jsonschema.validate(example, schema)
    parsed = model.model_validate(example)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert dumped == example
    jsonschema.validate(dumped, schema)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        contract.MoveResult.model_validate({"ok": True, "verified": True, "deleted": True})


def test_no_tool_deletes_or_expunges():
    forbidden = re.compile(r"delete|expunge|purge|remove|destroy|trash", re.IGNORECASE)
    assert not [name for name in contract.TOOLS if forbidden.search(name)]


def test_doc_lists_exactly_the_contract_tools():
    documented = re.findall(r"^### `(\w+)`", DOC.read_text(), re.MULTILINE)
    assert documented == list(contract.TOOLS)


def test_doc_and_package_agree_on_version():
    assert f"contract_version: `{contract.CONTRACT_VERSION}`" in DOC.read_text()


@pytest.mark.parametrize(
    ("version", "supported"),
    [("1.0", True), ("1.7", True), ("2.0", False), ("0.9", False), ("1", False), ("one.0", False)],
)
def test_supported_versions(version, supported):
    assert contract.is_supported(version) is supported
