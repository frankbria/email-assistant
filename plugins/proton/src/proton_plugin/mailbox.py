import re
import socket
from collections.abc import Callable
from contextlib import AbstractContextManager
import ssl
import subprocess
import time
from typing import Literal

from imap_mailbox.mailbox import ImapMailbox, MailboxError
from mailbox_contract import Capability, ErrorCode, Health, HealthCheck, MailboxInfo, RepairResult

from proton_plugin.mutf7 import decode_mutf7
from proton_plugin.settings import ProtonSettings

LIST_LINE = re.compile(rb'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>"(?:[^"\\]|\\.)*"|\S+)$')
RESTART_BRIDGE = "restart_bridge"


class ProtonMailbox(ImapMailbox):
    def __init__(self, settings: ProtonSettings) -> None:
        super().__init__(settings)
        self.proton = settings

    # --- plain-language failures ---------------------------------------------------------

    def unreachable_message(self, protocol: str, host: str, port: int) -> str:
        return f"Proton Bridge isn't answering {protocol} at {host}:{port}. Is Bridge running and signed in?"

    def untrusted_certificate_message(self, protocol: str, error: ssl.SSLError) -> str:
        return (
            f"Bridge's {protocol} certificate doesn't match the pinned one ({self.proton.ca_cert_path}). "
            "Export it again from Bridge (Settings → Export TLS certificates) and point MAILBOX_CA_CERT_PATH at it."
        )

    def handshake_failed_message(self, protocol: str, host: str, port: int) -> str:
        return (
            f"Bridge at {host}:{port} didn't speak {protocol} as expected. Check that the security "
            "setting (STARTTLS or SSL) matches Bridge's mailbox settings."
        )

    def login_rejected_message(self, protocol: str) -> str:
        return (
            f"Bridge rejected the {protocol} login. Re-enter the mailbox password Bridge shows for this "
            "account (not your Proton password). If Bridge is asking you to sign in again, or is waiting "
            "for an update or a keychain unlock, do that in Bridge first."
        )

    # --- folders -------------------------------------------------------------------------

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
            raw = match["name"].decode()
            if raw.startswith('"'):
                raw = raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            name = decode_mutf7(raw)
            if name.startswith("Folders/"):
                grouped["folders"].append(name.removeprefix("Folders/"))
            elif name.startswith("Labels/"):
                grouped["labels"].append(name.removeprefix("Labels/"))
            elif name not in ("Folders", "Labels"):
                grouped["system"].append(name)
        return grouped

    def _folders_check(self) -> HealthCheck:
        try:
            folder_map = self.folder_map()
        except Exception as error:  # report, never crash the health check
            detail = error.message if isinstance(error, MailboxError) else f"Couldn't list Bridge's folders: {error}"
            return HealthCheck(layer="folders", ok=False, detail=detail)
        present = set(folder_map["system"])
        present |= {f"Folders/{name}" for name in folder_map["folders"]}
        present |= {f"Labels/{name}" for name in folder_map["labels"]}
        missing = [name for name in (self.folders.archive, self.folders.sent) if name not in present]
        if missing:
            return HealthCheck(
                layer="folders", ok=False,
                detail=f"Bridge has no {', '.join(missing)} folder; check the folder names in the plugin settings.",
            )
        return HealthCheck(layer="folders", ok=True, detail="Archive and Sent are there.")

    # --- tools ---------------------------------------------------------------------------

    def mailbox_info(self) -> MailboxInfo:
        info = super().mailbox_info()
        return info.model_copy(update={"capabilities": [Capability.REPAIR] if self.proton.bridge_restart_command else []})

    def health(self) -> Health:
        """Ordered layers (spec §6.3), stopping at the first failure, which is the one to show."""
        checks = [HealthCheck(layer="plugin", ok=True, detail="The plugin is answering.")]
        host, port = self.settings.imap_host, self.settings.imap_port
        try:
            socket.create_connection((host, port), timeout=3).close()
        except OSError:
            checks.append(HealthCheck(
                layer="imap_port", ok=False,
                detail=f"Proton Bridge isn't running: nothing is listening on {host}:{port}.",
            ))
            return self._result(checks, "down", restartable=True)
        checks.append(HealthCheck(layer="imap_port", ok=True, detail=f"Bridge is listening on {host}:{port}."))
        login_layers: tuple[tuple[str, Callable[[], AbstractContextManager[object]], Literal["down", "degraded"]], ...] = (
            ("imap_login", self._imap, "down"),
            ("smtp_auth", self._smtp, "degraded"),
        )
        for layer, connect, status in login_layers:
            try:
                with connect():
                    pass
            except MailboxError as error:
                checks.append(HealthCheck(layer=layer, ok=False, detail=error.message))
                # Down or hung → a restart may help; credentials or configuration need the owner.
                return self._result(checks, status, restartable=error.restartable)
            checks.append(HealthCheck(layer=layer, ok=True, detail="ok"))
        folders = self._folders_check()
        checks.append(folders)
        return self._result(checks, "ok" if folders.ok else "degraded", restartable=False)

    def _result(self, checks: list[HealthCheck], status: Literal["ok", "degraded", "down"], restartable: bool) -> Health:
        actions = [RESTART_BRIDGE] if restartable and self.proton.bridge_restart_command else []
        return Health(status=status, checks=checks, repair_actions=actions)

    def repair(self, action: str) -> RepairResult:
        """Run the owner-configured Bridge restart (never anything from the request), then re-check."""
        health = self.health()
        if action not in health.repair_actions or not self.proton.bridge_restart_command:
            first = next((check.detail for check in health.checks if not check.ok), "Bridge is healthy.")
            raise MailboxError(ErrorCode.UNSUPPORTED, f"'{action}' isn't available right now. {first}")
        try:
            # No output capture: a restart that starts Bridge in the background would hand it our
            # pipes, and run() would wait for them to close until the timeout.
            subprocess.run(
                self.proton.bridge_restart_command,
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return RepairResult(ok=False, detail=f"Restarting Bridge failed: {error}")
        deadline = time.monotonic() + self.proton.repair_wait_seconds
        while True:
            health = self.health()
            failing = next((check for check in health.checks if not check.ok), None)
            if failing is None:
                return RepairResult(ok=True, detail="Bridge was restarted and is answering again.")
            if not health.repair_actions:  # waiting longer can't fix this one
                return RepairResult(ok=False, detail=f"Bridge was restarted, but this needs your attention: {failing.detail}")
            if time.monotonic() >= deadline:
                return RepairResult(ok=False, detail=f"Bridge was restarted but still isn't answering: {failing.detail}")
            time.sleep(2)
