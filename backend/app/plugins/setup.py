# backend/app/plugins/setup.py
"""The guided setup checklists (Proton spec §6.2, Gmail §7): each step is done, failing with its
fix, or waiting on an earlier one, read from the plugin's layered health (spec §6.3)."""

from typing import Literal

from mailbox_contract import Health
from pydantic import BaseModel, Field

from app.plugins.config import PluginConfig, StdioTransport
from app.plugins.diagnosis import WatchdogRead, WatchdogReport
from app.plugins.state import PluginState

# (title, health layer, what to do when that layer fails), in the order the owner works.
STEPS = (
    (
        "Install Proton Mail Bridge and start it",
        "imap_port",
        "Start Proton Mail Bridge on the Bridge machine (install it from proton.me/mail/bridge first if it isn't there).",
    ),
    ("Sign in to Bridge", "imap_login", "Open Bridge and check that your Proton account is signed in."),
    (
        "Copy Bridge's IMAP and SMTP settings and password into the plugin settings",
        "smtp_auth",
        "Copy the SMTP settings and the password Bridge shows in its mailbox settings into the plugin settings.",
    ),
    (
        "Install the plugin and the watchdog",
        "plugin",
        "Install the Proton plugin and its watchdog on the Bridge machine (plugins/proton/README.md), then check its entry in plugins.yaml.",
    ),
    ("Test the connection", "folders", ""),
)

# Gmail can't say which of the first three a rejected login was, so a failed login marks all three.
GMAIL_STEPS = (
    (
        "Turn on 2-Step Verification for the Google account",
        "imap_login",
        "App passwords need it: Google Account → Security → 2-Step Verification.",
    ),
    (
        "Create an app password and set it as GMAIL_APP_PASSWORD",
        "imap_login",
        "Create one at myaccount.google.com/apppasswords and use it, not your Google password.",
    ),
    (
        "Check that IMAP is on in Gmail's settings",
        "imap_login",
        "Personal accounts always have IMAP on; on a Google Workspace account, ask the admin to allow IMAP.",
    ),
    ("Add the Gmail plugin to plugins.yaml", "plugin", "See plugins/gmail/README.md."),
    ("Test the connection", "smtp", ""),
)


WATCHDOG_PROBLEMS = {
    "refused": "isn't running",
    "offline": "can't be reached; is the machine on?",
    "unreadable": "answered but couldn't be read; check its token",
}


class SetupStep(BaseModel):
    title: str
    status: Literal["done", "failing", "waiting"]
    detail: str | None = None


class Checklist(BaseModel):
    plugin_id: str
    title: str
    steps: list[SetupStep]
    warnings: list[str] = Field(description="Problems that don't stop mail, e.g. Gmail's Auto-Expunge.")


def install_step(title: str, fix: str, config: PluginConfig, state: PluginState, watchdog: WatchdogRead | None) -> SetupStep:
    """`watchdog` is what the configured watchdog's /status returned, None when none is configured."""
    if state.status != "connected":
        problem = state.reason or f"The {config.id} plugin isn't answering."
        return SetupStep(title=title, status="failing", detail=f"{problem} {fix}")
    if config.watchdog is None:
        problem = f"plugins.yaml has no watchdog for {config.id}, so nothing restarts Bridge when it stops."
        return SetupStep(title=title, status="failing", detail=f"{problem} {fix}")
    if not isinstance(watchdog, WatchdogReport):
        problem = f"The watchdog on {config.watchdog.machine} {WATCHDOG_PROBLEMS[watchdog or 'unreadable']}."
        return SetupStep(title=title, status="failing", detail=f"{problem} {fix}")
    return SetupStep(title=title, status="done")


def is_gmail(config: PluginConfig, state: PluginState) -> bool:
    if state.info is not None:
        return state.info.plugin_name == "gmail"
    # shortcut: a plugin that never started (e.g. no app password set) can't say what it is, so its
    # command is the clue; let plugins.yaml name the kind if a Gmail plugin is ever launched otherwise.
    transport = config.transport
    launch = [transport.command, *transport.args] if isinstance(transport, StdioTransport) else [transport.url]
    return any("gmail" in part for part in launch)


def build_checklist(
    config: PluginConfig,
    state: PluginState,
    health: Health | None,
    watchdog: WatchdogRead | None,
    warnings: list[str] | None = None,
) -> Checklist:
    gmail = is_gmail(config, state)
    checks = {check.layer: check for check in health.checks} if health else {}
    steps, explained = [], set()
    for title, layer, fix in GMAIL_STEPS if gmail else STEPS:
        if layer == "plugin" and gmail:
            failing = state.status != "connected"
            detail = f"{state.reason or 'The plugin is not answering.'} {fix}" if failing else None
            steps.append(SetupStep(title=title, status="failing" if failing else "done", detail=detail))
        elif layer == "plugin":
            steps.append(install_step(title, fix, config, state, watchdog))
        elif (check := checks.get(layer)) is None:
            steps.append(SetupStep(title=title, status="waiting"))
        elif check.ok:
            steps.append(SetupStep(title=title, status="done"))
        else:
            # The plugin's words once, on the first step its layer fails; every step adds its own fix.
            detail = fix if layer in explained else f"{check.detail} {fix}".strip()
            explained.add(layer)
            steps.append(SetupStep(title=title, status="failing", detail=detail))
    title = "Set up Gmail" if gmail else "Set up Proton Mail"
    return Checklist(plugin_id=config.id, title=title, steps=steps, warnings=warnings or [])
