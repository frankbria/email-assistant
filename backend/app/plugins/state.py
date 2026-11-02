# backend/app/plugins/state.py
from typing import Literal

from pydantic import BaseModel

from mailbox_contract import MailboxInfo


class PluginState(BaseModel):
    id: str
    status: Literal["connected", "refused", "failed", "disabled"]
    reason: str | None = None
    info: MailboxInfo | None = None
