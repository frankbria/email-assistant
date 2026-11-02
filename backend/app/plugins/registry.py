# backend/app/plugins/registry.py
"""Connects the configured mailbox plugins (MCP servers) and tracks their state."""

import asyncio
import logging
import os
from contextlib import AsyncExitStack

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client import Transport
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from app.plugins.config import HttpTransport, PluginConfig, StdioTransport
from app.plugins.diagnosis import ConnectionState, diagnose
from app.plugins.state import PluginState
from mailbox_contract import SUPPORTED_MAJOR, Health, MailboxInfo, is_supported

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 15
CLOSE_TIMEOUT_SECONDS = 5
REFRESH_SECONDS = 60  # owner fixes show up within a minute (AC-P.4)


class PluginConnectError(Exception):
    """A plugin could not be connected; the message is shown to the owner."""


def read_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise PluginConnectError(f"environment variable {name} is not set")
    return value


async def close_quietly(plugin_id: str, connection: AsyncExitStack) -> None:
    """Close one plugin's connection without letting it hang or break the others."""
    try:
        async with asyncio.timeout(CLOSE_TIMEOUT_SECONDS):
            await connection.aclose()
    except Exception:
        logger.exception("Plugin %s did not close cleanly", plugin_id)


# Plugins connect one after another on purpose: each MCP client's anyio scopes must be
# exited by the task that entered them, which is the app's lifespan task.
class PluginRegistry:
    def __init__(self) -> None:
        self.configs: dict[str, PluginConfig] = {}
        self.states: dict[str, PluginState] = {}
        self.diagnoses: dict[str, ConnectionState] = {}
        self.clients: dict[str, Client] = {}
        self._connections: dict[str, AsyncExitStack] = {}

    async def connect_all(self, configs: list[PluginConfig]) -> None:
        for config in configs:
            self.configs[config.id] = config
            self.states[config.id] = await self._connect(config)
            logger.info("Plugin %s: %s", config.id, self.states[config.id].status)

    async def run(self, configs: list[PluginConfig], ready: asyncio.Event, interval_seconds: float = REFRESH_SECONDS) -> None:
        """Connect, then refresh every interval until cancelled, all in this one task:
        MCP clients must be closed by the task that opened them."""
        try:
            await self.connect_all(configs)
            await self.refresh()
            ready.set()
            while True:
                await asyncio.sleep(interval_seconds)
                await self.refresh()
        finally:
            ready.set()
            await self.close()

    async def refresh(self, timeout: float = 5) -> None:
        """Reconnect plugins that aren't connected, then re-diagnose every plugin, so an
        owner's fix shows up within one refresh."""
        for plugin_id, config in self.configs.items():
            if config.enabled and self.states[plugin_id].status != "connected":
                connection = self._connections.pop(plugin_id, None)
                if connection is not None:
                    await close_quietly(plugin_id, connection)
                self.clients.pop(plugin_id, None)
                self.states[plugin_id] = await self._connect(config)
            health = await self._health(plugin_id)
            self.diagnoses[plugin_id] = await diagnose(self.states[plugin_id], health, config.watchdog, timeout)

    async def _health(self, plugin_id: str) -> Health | None:
        client = self.clients.get(plugin_id)
        if client is None:
            return None
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS):
                result = await client.call_tool("health", {})
            if result.is_error or result.structured_content is None:
                raise PluginConnectError("health failed")
            return Health.model_validate(result.structured_content)
        except Exception as error:
            # The plugin stopped answering: drop the connection; the next refresh reconnects.
            self.states[plugin_id] = PluginState(id=plugin_id, status="failed", reason=f"Not answering: {error}")
            return None

    async def close(self) -> None:
        for plugin_id, connection in self._connections.items():
            await close_quietly(plugin_id, connection)
        self._connections.clear()
        self.clients.clear()

    async def _connect(self, config: PluginConfig) -> PluginState:
        if not config.enabled:
            return PluginState(id=config.id, status="disabled")
        connection = AsyncExitStack()
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS):
                client = await connection.enter_async_context(
                    Client(await self._target(config.transport, connection))
                )
                info = await self._mailbox_info(client)
        except Exception as error:
            await close_quietly(config.id, connection)
            reason = str(error) or type(error).__name__
            return PluginState(id=config.id, status="failed", reason=f"Could not connect: {reason}")
        if not is_supported(info.contract_version):
            await close_quietly(config.id, connection)
            return PluginState(
                id=config.id,
                status="refused",
                info=info,
                reason=f"Plugin speaks mailbox/{info.contract_version}; "
                f"this app supports mailbox/{SUPPORTED_MAJOR}.x",
            )
        self._connections[config.id] = connection
        self.clients[config.id] = client
        return PluginState(id=config.id, status="connected", info=info)

    @staticmethod
    async def _target(
        transport: StdioTransport | HttpTransport, connection: AsyncExitStack
    ) -> StdioServerParameters | Transport:
        if isinstance(transport, StdioTransport):
            env = {name: read_env(source) for name, source in transport.env_from.items()}
            return StdioServerParameters(command=transport.command, args=transport.args, env=env)
        headers = (
            {"Authorization": f"Bearer {read_env(transport.bearer_token_env)}"}
            if transport.bearer_token_env
            else {}
        )
        http_client = await connection.enter_async_context(httpx2.AsyncClient(headers=headers))
        return streamable_http_client(transport.url, http_client=http_client)

    @staticmethod
    async def _mailbox_info(client: Client) -> MailboxInfo:
        result = await client.call_tool("mailbox_info", {})
        if result.is_error or result.structured_content is None:
            text = " ".join(block.text for block in result.content if isinstance(block, TextContent))
            raise PluginConnectError(f"mailbox_info failed: {text or 'no structured result'}")
        return MailboxInfo.model_validate(result.structured_content)
