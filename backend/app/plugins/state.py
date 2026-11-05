# backend/app/plugins/state.py
from typing import Literal

from mailbox_contract import MailboxInfo
from pydantic import BaseModel

PluginStatus = Literal["connected", "refused", "failed", "disabled"]


class PluginState(BaseModel):
    id: str
    status: PluginStatus
    reason: str | None = None
    info: MailboxInfo | None = None
