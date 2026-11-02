"""The `mailbox/1` plugin contract (docs/contracts/mailbox-1.md).

A mailbox plugin is an MCP server exposing the tools in `TOOLS`. Inputs and outputs are
the pydantic models below; failures use `ToolError`. There is deliberately no tool that
deletes or expunges a message.
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

CONTRACT_VERSION = "1.0"
SUPPORTED_MAJOR = 1


class ContractModel(BaseModel):
    # Unknown fields are rejected so drift between app and plugin fails loudly.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Empty(ContractModel):
    """Input of tools that take no arguments."""


# --- mailbox_info ---------------------------------------------------------------


class Capability(StrEnum):
    PUSH = "push"
    REPAIR = "repair"


class Folders(ContractModel):
    """The plugin's names for the three folders the app uses."""

    inbox: str
    archive: str
    sent: str


class MailboxInfo(ContractModel):
    contract_version: str = Field(pattern=r"^\d+\.\d+$")
    plugin_name: str
    plugin_version: str
    account: str = Field(description="The mailbox address, e.g. owner@example.com.")
    capabilities: list[Capability]
    folders: Folders


# --- health ---------------------------------------------------------------------


class HealthCheck(ContractModel):
    layer: str = Field(description="What was checked, e.g. 'imap_login'.")
    ok: bool
    detail: str


class Health(ContractModel):
    status: Literal["ok", "degraded", "down"]
    checks: list[HealthCheck] = Field(description="In order; the first failing one is shown.")
    repair_actions: list[str] = Field(description="Actions accepted by `repair`.")


# --- messages ---------------------------------------------------------------------


class Address(ContractModel):
    name: str | None = None
    email: str


class MessageSummary(ContractModel):
    ref: str = Field(description="Opaque, stable plugin reference to the message.")
    message_id: str = Field(description="The RFC 5322 Message-ID header.")
    sender: Address = Field(alias="from")
    to: list[Address]
    cc: list[Address]
    date: datetime
    subject: str
    snippet: str
    list_id: str | None = None
    in_reply_to: str | None = None


class ListMessagesInput(ContractModel):
    folder: Literal["inbox", "sent"]
    cursor: str | None = Field(
        default=None, description="A next_cursor from an earlier call; omit to start."
    )
    since: datetime | None = Field(
        default=None, description="Without a cursor: only messages on or after this time."
    )
    limit: int = Field(default=100, ge=1, le=500)


class ListMessagesOutput(ContractModel):
    messages: list[MessageSummary]
    next_cursor: str = Field(
        description="Opaque position after the last message. Persist it: it must stay "
        "valid across plugin and app restarts."
    )
    has_more: bool


class InboxContainsInput(ContractModel):
    refs: list[str] = Field(min_length=1, max_length=500)


class InboxContainsOutput(RootModel[dict[str, bool]]):
    """Maps every requested ref to whether the message is still in the inbox.

    A schema can't tie the keys to the request; the app and the conformance suite check
    that the keys equal the requested refs.
    """


class MessageRef(ContractModel):
    ref: str


class Header(ContractModel):
    name: str
    value: str


class AttachmentMeta(ContractModel):
    name: str
    content_type: str
    size: int = Field(ge=0, description="Bytes.")


class MessageDetail(MessageSummary):
    headers: list[Header]
    text: str = Field(description="Plain-text body, converted from HTML if needed.")
    attachments: list[AttachmentMeta]


# --- archive / restore ------------------------------------------------------------


class MoveResult(ContractModel):
    ok: bool
    verified: bool = Field(
        description="True only after re-reading confirms the move; false counts as failure."
    )


# --- send -------------------------------------------------------------------------


class SendInput(ContractModel):
    to: list[Address] = Field(min_length=1)
    cc: list[Address] = Field(default_factory=list)
    subject: str
    body_text: str
    in_reply_to_ref: str | None = Field(
        default=None, description="Reply to this message: sets In-Reply-To and References."
    )


class SendResult(ContractModel):
    ok: bool
    sent_message_id: str


# --- repair (optional) ------------------------------------------------------------


class RepairInput(ContractModel):
    action: str = Field(description="One of health.repair_actions.")


class RepairResult(ContractModel):
    ok: bool
    detail: str


# --- errors -------------------------------------------------------------------------


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "invalid_argument"
    NOT_FOUND = "not_found"
    INVALID_CURSOR = "invalid_cursor"
    UNAVAILABLE = "unavailable"
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    UNSUPPORTED = "unsupported"
    INTERNAL = "internal"


RETRYABLE_CODES = frozenset({ErrorCode.UNAVAILABLE, ErrorCode.RATE_LIMITED, ErrorCode.INTERNAL})


class ToolError(ContractModel):
    """Structured content of an MCP tool result with isError=true."""

    code: ErrorCode
    message: str = Field(description="Plain words the app can show the owner.")
    retryable: bool = Field(description="Fixed by code: true for unavailable, rate_limited, internal.")

    @model_validator(mode="after")
    def retryable_matches_code(self) -> "ToolError":
        if self.retryable != (self.code in RETRYABLE_CODES):
            raise ValueError(f"retryable must be {self.code in RETRYABLE_CODES} for {self.code}")
        return self


# --- registry -----------------------------------------------------------------------


class Tool(ContractModel):
    name: str
    input: type[BaseModel]
    output: type[BaseModel]
    required: bool


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in [
        Tool(name="mailbox_info", input=Empty, output=MailboxInfo, required=True),
        Tool(name="health", input=Empty, output=Health, required=True),
        Tool(name="list_messages", input=ListMessagesInput, output=ListMessagesOutput, required=True),
        Tool(name="inbox_contains", input=InboxContainsInput, output=InboxContainsOutput, required=True),
        Tool(name="get_message", input=MessageRef, output=MessageDetail, required=True),
        Tool(name="archive", input=MessageRef, output=MoveResult, required=True),
        Tool(name="restore", input=MessageRef, output=MoveResult, required=True),
        Tool(name="send", input=SendInput, output=SendResult, required=True),
        Tool(name="repair", input=RepairInput, output=RepairResult, required=False),
    ]
}


def is_supported(contract_version: str) -> bool:
    """The app accepts any minor version of the major it was built for."""
    match = re.fullmatch(r"([0-9]+)\.[0-9]+", contract_version)
    return match is not None and int(match.group(1)) == SUPPORTED_MAJOR
