# backend/app/plugins/registry.py
"""Connects the configured mailbox plugins (MCP servers) and tracks their state."""

import asyncio
import logging
import os
from collections import defaultdict
from contextlib import AsyncExitStack
from dataclasses import dataclass

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client import Transport
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

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


def result_text(result: CallToolResult) -> str:
    """The text a tool returned, e.g. an error message without structured content."""
    return " ".join(block.text for block in result.content if isinstance(block, TextContent))


@dataclass
class HeldConnection:
    """One plugin's MCP client, opened and closed by its own task: the client's anyio
    scopes must be exited by the task that entered them, and a dead transport then
    cancels only that task, never the app's."""

    task: asyncio.Task[None]
    closing: asyncio.Event


async def close_quietly(plugin_id: str, held: HeldConnection) -> None:
    """Close one plugin's connection without letting it hang or break the others."""
    held.closing.set()
    await asyncio.wait({held.task}, timeout=CLOSE_TIMEOUT_SECONDS)
    if not held.task.done():
        logger.error("Plugin %s did not close within %s s; cancelling it", plugin_id, CLOSE_TIMEOUT_SECONDS)
        held.task.cancel()
        await asyncio.wait({held.task}, timeout=CLOSE_TIMEOUT_SECONDS)
    if held.task.done() and not held.task.cancelled() and (error := held.task.exception()) is not None:
        logger.error("Plugin %s connection ended with an error", plugin_id, exc_info=error)


class PluginRegistry:
    def __init__(self) -> None:
        self.configs: dict[str, PluginConfig] = {}
        self.states: dict[str, PluginState] = {}
        self.diagnoses: dict[str, ConnectionState] = {}
        self.healths: dict[str, Health | None] = {}
        self.clients: dict[str, Client] = {}
        self._seen_restarts: dict[str, int] = {}
        self._connections: dict[str, HeldConnection] = {}
        self._checking: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def connect_all(self, configs: list[PluginConfig]) -> None:
        for config in configs:
            self.configs[config.id] = config
            self.states[config.id] = await self._connect(config)
            logger.info("Plugin %s: %s", config.id, self.states[config.id].status)

    async def run(self, configs: list[PluginConfig], ready: asyncio.Event, interval_seconds: float = REFRESH_SECONDS) -> None:
        """Connect, then refresh every interval until cancelled."""
        try:
            await self.connect_all(configs)
            await self.refresh()
            ready.set()
            while True:
                await asyncio.sleep(interval_seconds)
                try:
                    await self.refresh()
                except Exception:
                    logger.exception("Plugin refresh failed; retrying next cycle")
        finally:
            ready.set()
            await self.close()

    async def refresh(self, timeout: float = 5) -> None:
        """Reconnect plugins that aren't connected, then re-diagnose every plugin, so an
        owner's fix shows up within one refresh."""
        for plugin_id in self.configs:
            await self.check(plugin_id, timeout)

    async def check(self, plugin_id: str, timeout: float = 5) -> None:
        """Reconnect one plugin if it isn't connected, then re-check its health and diagnosis.
        Locked per plugin: the refresh loop and an owner's "check now" never overlap."""
        async with self._checking[plugin_id]:
            config = self.configs[plugin_id]
            if config.enabled and self.states[plugin_id].status != "connected":
                await self._drop(plugin_id)
                self.states[plugin_id] = await self._connect(config)
            health = await self._health(plugin_id)
            diagnosis = await diagnose(
                self.states[plugin_id], health, config.watchdog, timeout, self._seen_restarts.get(plugin_id)
            )
            if diagnosis.bridge_restarts is not None:
                self._seen_restarts[plugin_id] = diagnosis.bridge_restarts
            self.healths[plugin_id] = health
            self.diagnoses[plugin_id] = diagnosis

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
            await self._drop(plugin_id)
            self.states[plugin_id] = PluginState(id=plugin_id, status="failed", reason=f"Not answering: {error}")
            return None

    async def _drop(self, plugin_id: str) -> None:
        self.clients.pop(plugin_id, None)
        connection = self._connections.pop(plugin_id, None)
        if connection is not None:
            await close_quietly(plugin_id, connection)

    async def close(self) -> None:
        await asyncio.gather(*(close_quietly(plugin_id, held) for plugin_id, held in self._connections.items()))
        self._connections.clear()
        self.clients.clear()

    async def _connect(self, config: PluginConfig) -> PluginState:
        if not config.enabled:
            return PluginState(id=config.id, status="disabled")
        opened: asyncio.Future[Client] = asyncio.get_running_loop().create_future()
        closing = asyncio.Event()
        connection = HeldConnection(asyncio.create_task(self._hold(config, opened, closing)), closing)
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS):
                client = await asyncio.shield(opened)
                info = await self._mailbox_info(client)
        except Exception as error:
            await close_quietly(config.id, connection)
            reason = str(error) or type(error).__name__
            return PluginState(id=config.id, status="failed", reason=f"Could not connect: {reason}")
        except BaseException:  # shutdown mid-connect: the holder isn't stored yet, so close it here
            await close_quietly(config.id, connection)
            raise
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

    @classmethod
    async def _hold(cls, config: PluginConfig, opened: "asyncio.Future[Client]", closing: asyncio.Event) -> None:
        try:
            async with AsyncExitStack() as connection:
                client = await connection.enter_async_context(
                    Client(await cls._target(config.transport, connection))
                )
                opened.set_result(client)
                await closing.wait()
        except Exception as error:
            if not opened.done():
                opened.set_exception(error)
                return  # reported through `opened`
            raise
        finally:
            if not opened.done():
                opened.cancel()

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
            raise PluginConnectError(f"mailbox_info failed: {result_text(result) or 'no structured result'}")
        return MailboxInfo.model_validate(result.structured_content)
