# backend/app/plugins/setup.py
"""The guided Proton setup checklist (spec §6.2): each step is done, failing with its fix,
or waiting on an earlier one, read from the plugin's layered health (spec §6.3)."""

from typing import Literal

from pydantic import BaseModel

from app.plugins.config import PluginConfig
from app.plugins.state import PluginState
from mailbox_contract import Health

# (title, health layer, what to do when that layer fails), in the order the owner works.
STEPS = (
    ("Install Proton Mail Bridge and start it", "imap_port",
     "Start Proton Mail Bridge on the Bridge machine (install it from proton.me/mail/bridge first if it isn't there)."),
    ("Sign in to Bridge", "imap_login",
     "Open Bridge and check that your Proton account is signed in."),
    (
        "Copy Bridge's IMAP and SMTP settings and password into the plugin settings",
        "smtp_auth",
        "Copy the SMTP settings and the password Bridge shows in its mailbox settings into the plugin settings.",
    ),
    ("Install the plugin and the watchdog", "plugin",
     "Install the Proton plugin and its watchdog on the Bridge machine (plugins/proton/README.md), then check its entry in plugins.yaml."),
    ("Test the connection", "folders", ""),
)


class SetupStep(BaseModel):
    title: str
    status: Literal["done", "failing", "waiting"]
    detail: str | None = None


class Checklist(BaseModel):
    plugin_id: str
    steps: list[SetupStep]


def build_checklist(config: PluginConfig, state: PluginState, health: Health | None) -> Checklist:
    checks = {check.layer: check for check in health.checks} if health else {}
    steps = []
    for title, layer, fix in STEPS:
        if layer == "plugin" and state.status != "connected":
            problem = state.reason or f"The {config.id} plugin isn't answering."
            steps.append(SetupStep(title=title, status="failing", detail=f"{problem} {fix}"))
        elif layer == "plugin":
            steps.append(SetupStep(title=title, status="done"))
        elif (check := checks.get(layer)) is None:
            steps.append(SetupStep(title=title, status="waiting"))
        elif check.ok:
            steps.append(SetupStep(title=title, status="done"))
        else:
            steps.append(SetupStep(title=title, status="failing", detail=f"{check.detail} {fix}".strip()))
    return Checklist(plugin_id=config.id, steps=steps)
