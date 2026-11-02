import re
import ssl
from typing import Literal

from imap_mailbox.mailbox import ImapMailbox, MailboxError
from mailbox_contract import ErrorCode, Health, HealthCheck

from proton_plugin.mutf7 import decode_mutf7
from proton_plugin.settings import ProtonSettings

LIST_LINE = re.compile(rb'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>"(?:[^"\\]|\\.)*"|\S+)$')


class ProtonMailbox(ImapMailbox):
    def __init__(self, settings: ProtonSettings) -> None:
        super().__init__(settings)
        self.proton = settings

    def unreachable_message(self, protocol: str, host: str, port: int) -> str:
        return f"Proton Bridge isn't answering {protocol} at {host}:{port}. Is Bridge running and signed in?"

    def untrusted_certificate_message(self, protocol: str, error: ssl.SSLError) -> str:
        return (
            f"Bridge's {protocol} certificate doesn't match the pinned one ({self.proton.ca_cert_path}). "
            "Export it again from Bridge (Settings → Export TLS certificates) and point MAILBOX_CA_CERT_PATH at it."
        )

    def login_rejected_message(self, protocol: str) -> str:
        return (
            f"Bridge rejected the {protocol} login. Use the mailbox password Bridge shows for this "
            "account, not your Proton password."
        )

    def folder_map(self) -> dict[Literal["system", "folders", "labels"], list[str]]:
        """Bridge's folders, decoded: system ones, Folders/… and Labels/…."""
        with self._imap() as connection:
            status, lines = connection.list()
        if status != "OK":
            raise MailboxError(ErrorCode.INTERNAL, "Bridge didn't list its folders.")
        grouped: dict[Literal["system", "folders", "labels"], list[str]] = {"system": [], "folders": [], "labels": []}
        for line in lines:
            match = LIST_LINE.search(line) if isinstance(line, bytes) else None
            if match is None:
                continue
            name = decode_mutf7(match["name"].decode().strip('"'))
            if name.startswith("Folders/"):
                grouped["folders"].append(name.removeprefix("Folders/"))
            elif name.startswith("Labels/"):
                grouped["labels"].append(name.removeprefix("Labels/"))
            elif name not in ("Folders", "Labels"):
                grouped["system"].append(name)
        return grouped

    def health(self) -> Health:
        health = super().health()
        if not all(check.ok for check in health.checks):
            return health
        try:
            system = self.folder_map()["system"]
        except MailboxError as error:
            return Health(status="degraded", checks=[*health.checks, HealthCheck(layer="folders", ok=False, detail=error.message)], repair_actions=[])
        missing = [name for name in (self.folders.archive, self.folders.sent) if name not in system]
        folders = HealthCheck(
            layer="folders",
            ok=not missing,
            detail="ok" if not missing else f"Bridge has no {', '.join(missing)} folder; check the folder names in the plugin settings.",
        )
        return Health(status="ok" if folders.ok else "degraded", checks=[*health.checks, folders], repair_actions=[])
