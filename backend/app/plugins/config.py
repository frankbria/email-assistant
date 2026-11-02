# backend/app/plugins/config.py
"""plugins.yaml: which mailbox plugins (MCP servers) to connect, and how.

Secrets are never inline: transports name the environment variable that holds them.
"""

import logging
import re
from pathlib import Path
from urllib.parse import urlsplit
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

SECRET_WORDS = re.compile(r"token|password|passwd|secret|api_?key", re.IGNORECASE)
# A flag whose name mentions a secret, with or without =VALUE (e.g. --password,
# --secret-key=…, --password2=…).
INLINE_SECRET_ARGUMENT = re.compile(
    r"^-{1,2}[\w-]*(token|password|passwd|secret|api[-_]?key)[\w-]*(=|$)", re.IGNORECASE
)
# Uppercase by convention, which also catches most literal secrets pasted in by mistake.
ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")


def require_env_name(name: str) -> str:
    if not ENV_NAME.fullmatch(name):
        raise ValueError(
            f"'{name}' is not an environment variable name; inline secrets are not allowed"
        )
    return name


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_inline_secret_keys(cls, data: object) -> object:
        if isinstance(data, dict):
            for key in data:
                if SECRET_WORDS.search(str(key)) and not str(key).endswith("_env"):
                    raise ValueError(
                        f"'{key}' is an inline secret; reference it by environment "
                        "variable name instead (e.g. bearer_token_env)"
                    )
        return data


class StdioTransport(ConfigModel):
    type: Literal["stdio"]
    command: str
    args: list[str] = Field(default_factory=list)
    env_from: dict[str, str] = Field(
        default_factory=dict,
        description="Plugin env var → name of the app env var holding its value.",
    )

    @field_validator("args")
    @classmethod
    def reject_inline_secret_arguments(cls, args: list[str]) -> list[str]:
        # Rejects both --password=VALUE and a bare --password flag (its value follows it).
        for argument in args:
            if INLINE_SECRET_ARGUMENT.search(argument):
                raise ValueError(
                    f"argument '{argument.split('=')[0]}' carries an inline secret; "
                    "pass it through env_from instead"
                )
        return args

    @field_validator("env_from")
    @classmethod
    def require_env_names(cls, env_from: dict[str, str]) -> dict[str, str]:
        for name, source in env_from.items():
            require_env_name(name)
            require_env_name(source)
        return env_from


class HttpTransport(ConfigModel):
    type: Literal["http"]
    url: str
    bearer_token_env: str | None = None

    @field_validator("url")
    @classmethod
    def reject_credentials_in_url(cls, url: str) -> str:
        parts = urlsplit(url)
        if parts.username or parts.password:
            raise ValueError("the URL carries an inline secret (user:password@); use bearer_token_env")
        return url

    @field_validator("bearer_token_env")
    @classmethod
    def require_bearer_env_name(cls, name: str | None) -> str | None:
        return None if name is None else require_env_name(name)


class WatchdogConfig(ConfigModel):
    """The plugin machine's watchdog status endpoint (Proton, spec §6.3)."""

    url: str = Field(description="e.g. http://<tailscale-ip>:8766/status")
    token_env: str
    machine: str = Field(description="The machine's name, as shown to the owner.")

    @field_validator("token_env")
    @classmethod
    def require_token_env_name(cls, name: str) -> str:
        return require_env_name(name)


class PluginConfig(ConfigModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    enabled: bool = True
    transport: Annotated[StdioTransport | HttpTransport, Field(discriminator="type")]
    watchdog: WatchdogConfig | None = None


class PluginsFile(ConfigModel):
    plugins: list[PluginConfig] = Field(default_factory=list)

    @field_validator("plugins")
    @classmethod
    def reject_duplicate_ids(cls, plugins: list[PluginConfig]) -> list[PluginConfig]:
        ids = [plugin.id for plugin in plugins]
        duplicates = sorted({plugin_id for plugin_id in ids if ids.count(plugin_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate plugin ids: {', '.join(duplicates)}")
        return plugins


def load_plugins_config(path: Path) -> list[PluginConfig]:
    """Parse and validate plugins.yaml. A missing file means no plugins."""
    if not path.exists():
        logger.info("No plugins config at %s; no plugins connected", path.resolve())
        return []
    return PluginsFile.model_validate(yaml.safe_load(path.read_text()) or {}).plugins
