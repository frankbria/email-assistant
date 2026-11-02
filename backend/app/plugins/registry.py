# backend/app/plugins/registry.py
"""Connects the configured mailbox plugins (MCP servers) and tracks their state."""

import asyncio
import logging
import os
from contextlib import AsyncExitStack
from typing import Literal

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client import Transport
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent
from pydantic import BaseModel

from app.plugins.config import HttpTransport, PluginConfig, StdioTransport
from mailbox_contract import SUPPORTED_MAJOR, MailboxInfo, is_supported

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 15


class PluginConnectError(Exception):
    """A plugin could not be connected; the message is shown to the owner."""


class PluginState(BaseModel):
    id: str
    status: Literal["connected", "refused", "failed", "disabled"]
    reason: str | None = None
    info: MailboxInfo | None = None


def read_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise PluginConnectError(f"environment variable {name} is not set")
    return value


class PluginRegistry:
    def __init__(self) -> None:
        self.states: dict[str, PluginState] = {}
        self.clients: dict[str, Client] = {}
        self._connections: dict[str, AsyncExitStack] = {}

    async def connect_all(self, configs: list[PluginConfig]) -> None:
        for config in configs:
            self.states[config.id] = await self._connect(config)
            logger.info("Plugin %s: %s", config.id, self.states[config.id].status)

    async def close(self) -> None:
        for connection in self._connections.values():
            await connection.aclose()
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
            await connection.aclose()
            reason = str(error) or type(error).__name__
            return PluginState(id=config.id, status="failed", reason=f"Could not connect: {reason}")
        if not is_supported(info.contract_version):
            await connection.aclose()
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
