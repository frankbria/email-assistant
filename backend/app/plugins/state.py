# backend/app/plugins/state.py
from typing import Literal

from pydantic import BaseModel

from mailbox_contract import MailboxInfo


PluginStatus = Literal["connected", "refused", "failed", "disabled"]


class PluginState(BaseModel):
    id: str
    status: PluginStatus
    reason: str | None = None
    info: MailboxInfo | None = None
