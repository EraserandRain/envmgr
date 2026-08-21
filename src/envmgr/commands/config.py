from __future__ import annotations

from typing import Annotated

import typer
from rich.text import Text

from ..runtime_config import (
    AI_TOOLS_CONTEXT7_METHODS,
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
    "ai_tools.enable_context7": "enable_context7",
}
_METHOD_FIELDS = {
    "ai_tools.claude_context7_method": "claude_context7_method",
    "ai_tools.codex_context7_method": "codex_context7_method",
}


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("true", "yes", "1", "on"):
        return True
    if normalized in ("false", "no", "0", "off"):
        return False
    exit_with_error(f"Error: expected a boolean value, got {value!r}")


def _parse_method(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in AI_TOOLS_CONTEXT7_METHODS:
        return normalized
    allowed = ", ".join(AI_TOOLS_CONTEXT7_METHODS)
    exit_with_error(f"Error: expected one of {allowed}, got {value!r}")


def _config_from_key_value(
    current: AiToolsConfig,
    key: str,
    value: str,
) -> AiToolsConfig:
    if key in _BOOL_FIELDS:
        return _updated_bool_config(current, _BOOL_FIELDS[key], _parse_bool(value))
    if key in _METHOD_FIELDS:
        return _updated_method_config(
            current, _METHOD_FIELDS[key], _parse_method(value)
        )

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
        "enable_context7": current.enable_context7,
    }
    fields[field] = value
    return AiToolsConfig(
        configured=True,
        manage_claude_code=fields["manage_claude_code"],
        manage_codex=fields["manage_codex"],
        manage_rtk=fields["manage_rtk"],
        enable_context7=fields["enable_context7"],
        claude_context7_method=current.claude_context7_method,
        codex_context7_method=current.codex_context7_method,
    )


def _updated_method_config(
    current: AiToolsConfig,
    field: str,
    value: str,
) -> AiToolsConfig:
    claude_method = (
        value if field == "claude_context7_method" else current.claude_context7_method
    )
    codex_method = (
        value if field == "codex_context7_method" else current.codex_context7_method
    )
    return AiToolsConfig(
        configured=True,
        manage_claude_code=current.manage_claude_code,
        manage_codex=current.manage_codex,
        manage_rtk=current.manage_rtk,
        enable_context7=current.enable_context7,
        claude_context7_method=claude_method,
        codex_context7_method=codex_method,
    )


def _render_ai_tools_status(config: AiToolsConfig) -> list[tuple[str, str]]:
    def enabled_status(enabled: bool) -> str:
        return "enabled" if enabled else "disabled"

    return [
        ("Configured", "yes" if config.configured else "no"),
        ("Claude Code", enabled_status(config.manage_claude_code)),
        ("Codex CLI", enabled_status(config.manage_codex)),
        ("RTK", enabled_status(config.manage_rtk)),
        ("Context7", enabled_status(config.enable_context7)),
        ("Claude Code Context7", config.claude_context7_method),
        ("Codex CLI Context7", config.codex_context7_method),
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
        typer.Argument(help="Config key to update, e.g. ai_tools.enable_context7"),
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
