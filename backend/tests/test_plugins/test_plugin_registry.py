# Plugins are real MCP server processes (tests/fixtures/fake_mailbox_plugin.py); no mocks.
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.plugins.config import load_plugins_config
from app.plugins.registry import PluginRegistry

FAKE_PLUGIN = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mailbox_plugin.py"


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "plugins.yaml"
    path.write_text(body)
    return path


def stdio_entry(plugin_id: str, env_from: str = "{}", enabled: str = "true") -> str:
    return f"""
  - id: {plugin_id}
    enabled: {enabled}
    transport:
      type: stdio
      command: {sys.executable}
      args: [{FAKE_PLUGIN}]
      env_from: {env_from}
"""


async def connect(config_path: Path) -> PluginRegistry:
    registry = PluginRegistry()
    await registry.connect_all(load_plugins_config(config_path))
    return registry


# --- config loading -------------------------------------------------------------------


def test_missing_config_file_means_no_plugins(tmp_path):
    assert load_plugins_config(tmp_path / "absent.yaml") == []


def test_http_entry_references_its_token_by_env_name(tmp_path):
    path = write_config(
        tmp_path,
        """
plugins:
  - id: gmail
    transport: {type: http, url: "http://127.0.0.1:9/mcp", bearer_token_env: GMAIL_PLUGIN_TOKEN}
""",
    )

    [config] = load_plugins_config(path)

    assert config.transport.type == "http"
    assert config.enabled is True


@pytest.mark.parametrize(
    "transport",
    [
        '{type: http, url: "http://127.0.0.1:9/mcp", bearer_token: "abc123"}',
        '{type: http, url: "http://127.0.0.1:9/mcp", password: "abc"}',
        '{type: stdio, command: python, args: ["--password=abc"]}',
        '{type: stdio, command: python, args: ["--token", "abc"]}',
        '{type: stdio, command: python, args: ["--secret-key=abc"]}',
        '{type: stdio, command: python, args: ["--password2=abc"]}',
        '{type: http, url: "http://owner:abc@127.0.0.1:9/mcp"}',
        '{type: http, url: "http://127.0.0.1:9/mcp", bearer_token_env: "abc 123"}',
        '{type: stdio, command: python, env_from: {APP_PASSWORD: "abc123"}}',
    ],
)
def test_inline_secret_is_rejected_at_load(tmp_path, transport):
    path = write_config(tmp_path, f"plugins:\n  - id: proton\n    transport: {transport}\n")

    with pytest.raises(ValidationError, match="secret"):
        load_plugins_config(path)


def test_duplicate_plugin_ids_are_rejected(tmp_path):
    path = write_config(tmp_path, "plugins:" + stdio_entry("proton") + stdio_entry("proton"))

    with pytest.raises(ValidationError, match="duplicate"):
        load_plugins_config(path)


# --- connecting -----------------------------------------------------------------------


async def test_new_config_entry_connects_with_no_code_change(tmp_path):
    """AC-C.1: a new entry in the config is connected on (re)start."""
    registry = await connect(write_config(tmp_path, "plugins:" + stdio_entry("proton")))
    try:
        state = registry.states["proton"]
        assert state.status == "connected"
        assert state.info is not None and state.info.plugin_name == "fake"
        assert "proton" in registry.clients
    finally:
        await registry.close()


async def test_unsupported_contract_version_is_refused_with_reason(tmp_path, monkeypatch):
    """AC-C.2: a plugin on another major version is refused, and the reason is recorded."""
    monkeypatch.setenv("FAKE_V2", "2.0")
    entry = stdio_entry("future", env_from="{FAKE_CONTRACT_VERSION: FAKE_V2}")
    registry = await connect(write_config(tmp_path, "plugins:" + entry))
    try:
        state = registry.states["future"]
        assert state.status == "refused"
        assert state.reason is not None and "2.0" in state.reason and "1.x" in state.reason
        assert "future" not in registry.clients
    finally:
        await registry.close()


async def test_disabled_plugin_is_not_started(tmp_path):
    registry = await connect(write_config(tmp_path, "plugins:" + stdio_entry("paused", enabled="false")))
    try:
        assert registry.states["paused"].status == "disabled"
        assert "paused" not in registry.clients
    finally:
        await registry.close()


async def test_plugin_that_cannot_start_fails_without_stopping_others(tmp_path):
    broken = """
  - id: broken
    transport: {type: stdio, command: /nonexistent/plugin-binary}
"""
    registry = await connect(write_config(tmp_path, "plugins:" + broken + stdio_entry("proton")))
    try:
        assert registry.states["broken"].status == "failed"
        assert registry.states["broken"].reason
        assert registry.states["proton"].status == "connected"
    finally:
        await registry.close()


async def test_missing_secret_env_var_fails_with_its_name(tmp_path, monkeypatch):
    monkeypatch.delenv("UNSET_PLUGIN_TOKEN", raising=False)
    entry = """
  - id: gmail
    transport: {type: http, url: "http://127.0.0.1:9/mcp", bearer_token_env: UNSET_PLUGIN_TOKEN}
"""
    registry = await connect(write_config(tmp_path, "plugins:" + entry))
    try:
        state = registry.states["gmail"]
        assert state.status == "failed"
        assert state.reason is not None and "UNSET_PLUGIN_TOKEN" in state.reason
    finally:
        await registry.close()


@pytest.fixture
def http_plugin():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([sys.executable, str(FAKE_PLUGIN), "http", str(port)])
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        process.kill()
        process.wait(timeout=10)
        pytest.fail("fake HTTP plugin did not start listening")
    yield f"http://127.0.0.1:{port}/mcp"
    process.terminate()
    process.wait(timeout=10)


async def test_http_plugin_connects(tmp_path, monkeypatch, http_plugin):
    monkeypatch.setenv("HTTP_PLUGIN_TOKEN", "test-token")
    entry = f"""
  - id: remote
    transport: {{type: http, url: "{http_plugin}", bearer_token_env: HTTP_PLUGIN_TOKEN}}
"""
    registry = await connect(write_config(tmp_path, "plugins:" + entry))
    try:
        assert registry.states["remote"].status == "connected"
    finally:
        await registry.close()


def test_app_connects_configured_plugins_on_startup(tmp_path, monkeypatch):
    """AC-C.1 end to end: the app's startup reads the config file and connects."""
    monkeypatch.setenv("PLUGINS_CONFIG", str(write_config(tmp_path, "plugins:" + stdio_entry("proton"))))

    with TestClient(app):
        assert app.state.plugins.states["proton"].status == "connected"
