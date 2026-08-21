from __future__ import annotations

from typing import Annotated

import typer
from rich.text import Text

from ..runtime_config import (
    AiToolsConfig,
    load_runtime_config,
    save_ai_tools_config,
)
from .shared import console, exit_with_error

config_app = typer.Typer(
    help="Inspect and update envmgr runtime configuration.",
    add_completion=False,
)

_BOOL_FIELDS = {
    "ai_tools.manage_claude_code": "manage_claude_code",
    "ai_tools.manage_codex": "manage_codex",
    "ai_tools.manage_rtk": "manage_rtk",
}


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("true", "yes", "1", "on"):
        return True
    if normalized in ("false", "no", "0", "off"):
        return False
    exit_with_error(f"Error: expected a boolean value, got {value!r}")


def _config_from_key_value(
    current: AiToolsConfig,
    key: str,
    value: str,
) -> AiToolsConfig:
    if key in _BOOL_FIELDS:
        return _updated_bool_config(current, _BOOL_FIELDS[key], _parse_bool(value))

    exit_with_error(
        f"Error: unsupported config key {key!r}; expected an `ai_tools.*` key"
    )


def _updated_bool_config(
    current: AiToolsConfig,
    field: str,
    value: bool,
) -> AiToolsConfig:
    fields = {
        "manage_claude_code": current.manage_claude_code,
        "manage_codex": current.manage_codex,
        "manage_rtk": current.manage_rtk,
    }
    fields[field] = value
    return AiToolsConfig(
        configured=True,
        manage_claude_code=fields["manage_claude_code"],
        manage_codex=fields["manage_codex"],
        manage_rtk=fields["manage_rtk"],
    )


def _render_ai_tools_status(config: AiToolsConfig) -> list[tuple[str, str]]:
    def enabled_status(enabled: bool) -> str:
        return "enabled" if enabled else "disabled"

    return [
        ("Configured", "yes" if config.configured else "no"),
        ("Claude Code", enabled_status(config.manage_claude_code)),
        ("Codex CLI", enabled_status(config.manage_codex)),
        ("RTK", enabled_status(config.manage_rtk)),
    ]


@config_app.command("show", context_settings={"help_option_names": ["--help", "-h"]})
def _show_command() -> None:
    """Print the current AI-tools configuration."""
    config = load_runtime_config().ai_tools
    console.print()
    console.print(Text("AI Tools configuration:", style="bold cyan"))
    for label, value in _render_ai_tools_status(config):
        console.print(f"  - {label}: {value}")
    console.print()


@config_app.command("set", context_settings={"help_option_names": ["--help", "-h"]})
def _set_command(
    key: Annotated[
        str,
        typer.Argument(help="Config key to update, e.g. ai_tools.manage_codex"),
    ],
    value: Annotated[
        str,
        typer.Argument(help="New value for the config key"),
    ],
) -> None:
    """Update an `ai_tools.*` configuration key in config.toml."""
    runtime_config = load_runtime_config()
    updated = _config_from_key_value(runtime_config.ai_tools, key, value)
    save_ai_tools_config(runtime_config.paths, updated)
    console.print(Text(f"Updated {key} = {value}.", style="green"))


__all__ = ["config_app"]
