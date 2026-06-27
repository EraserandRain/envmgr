from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Annotated, Literal

import typer

from .command_text import CLI_APP_HELP, CLI_ROOT_COMMAND
from .commands.doctor import run_doctor
from .commands.history import run_history
from .commands.install import run_install
from .commands.ping import run_ping
from .commands.self_management import self_app
from .commands.setup import run_setup
from .commands.shared import (
    require_setup_completed as shared_require_setup_completed,
)
from .services.update_check import start_update_check_background

HELP_CONTEXT_SETTINGS = {"help_option_names": ["--help", "-h"]}
RUNTIME_OPTIONS_HELP_PANEL = "Runtime options"
AI_TOOLS_HELP_PANEL = "AI tools"
OUTPUT_HELP_PANEL = "Output"
VERSION_FALLBACK = "0+unknown"

app = typer.Typer(
    help=CLI_APP_HELP,
    no_args_is_help=True,
    add_completion=False,
    suggest_commands=True,
    rich_markup_mode="rich",
    context_settings=HELP_CONTEXT_SETTINGS,
)
app.add_typer(
    self_app,
    name="self",
    help="Manage installer-managed envmgr releases.",
)

Context7Method = Literal["remote", "local"]

# Only the Typer app, its root-command shims, and the setup guard remain the
# intentional public surface here.
__all__ = [
    "app",
    "doctor",
    "history",
    "install",
    "main",
    "ping",
    "require_setup_completed",
    "setup",
]


def require_setup_completed(
    command_name: str,
    *,
    envmgr_home: str | Path | None = None,
) -> None:
    """Retain the historical setup guard import path used by runtime helpers."""
    shared_require_setup_completed(command_name, envmgr_home=envmgr_home)


def _envmgr_version() -> str:
    try:
        return metadata.version("envmgr")
    except metadata.PackageNotFoundError:
        return VERSION_FALLBACK


def _version_callback(value: bool) -> bool:
    if value:
        typer.echo(f"{CLI_ROOT_COMMAND} {_envmgr_version()}")
        raise typer.Exit()
    return value


@app.callback()
def _root_callback(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the envmgr version and exit.",
        ),
    ] = False,
) -> None:
    """Run envmgr commands."""


@app.command("doctor", context_settings=HELP_CONTEXT_SETTINGS)
def _doctor_command(
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print the doctor report as JSON",
        ),
    ] = False,
) -> None:
    """Inspect envmgr runtime health."""
    run_doctor(json_output=json_output)


@app.command("history", context_settings=HELP_CONTEXT_SETTINGS)
def _history_command(
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Show at most this many recent records (default: 10)",
        ),
    ] = 10,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print recent runtime records as JSON",
        ),
    ] = False,
) -> None:
    """Show recent runtime subprocess records."""
    run_history(limit=limit, json_output=json_output)


@app.command(
    "install",
    context_settings=HELP_CONTEXT_SETTINGS,
)
def _install_command(
    ctx: typer.Context,
    tags: Annotated[
        list[str] | None,
        typer.Argument(
            help="List of tags: tag1 tag2 ...",
        ),
    ] = None,
    list_tags: Annotated[
        bool,
        typer.Option(
            "--list-tags",
            "-l",
            help="List all available tags",
            rich_help_panel=OUTPUT_HELP_PANEL,
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show the install plan without running Ansible",
            rich_help_panel=OUTPUT_HELP_PANEL,
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print the dry-run install plan as JSON",
            rich_help_panel=OUTPUT_HELP_PANEL,
        ),
    ] = False,
    playbook: Annotated[
        str | None,
        typer.Option(
            "--playbook",
            help=(
                "Built-in scenario (`workstation`, `node`) or custom playbook path. "
                "`workstation` targets the local workstation group; `node` targets "
                "Kubernetes node/master groups."
            ),
            rich_help_panel=RUNTIME_OPTIONS_HELP_PANEL,
        ),
    ] = None,
    inventory: Annotated[
        str | None,
        typer.Option(
            "--inventory",
            "-i",
            help="Specify an inventory alias from ~/.envmgr/config.toml",
            rich_help_panel=RUNTIME_OPTIONS_HELP_PANEL,
        ),
    ] = None,
    ask_vault_pass: Annotated[
        bool,
        typer.Option(
            "--ask-vault-pass",
            help="Ask for vault password",
            rich_help_panel=RUNTIME_OPTIONS_HELP_PANEL,
        ),
    ] = False,
    manage_claude_code: Annotated[
        bool | None,
        typer.Option(
            "--claude-code/--no-claude-code",
            help="When AI tools are selected, explicitly install Claude Code",
            show_default=False,
            rich_help_panel=AI_TOOLS_HELP_PANEL,
        ),
    ] = None,
    manage_codex: Annotated[
        bool | None,
        typer.Option(
            "--codex/--no-codex",
            help="When AI tools are selected, explicitly install Codex CLI",
            show_default=False,
            rich_help_panel=AI_TOOLS_HELP_PANEL,
        ),
    ] = None,
    manage_rtk: Annotated[
        bool | None,
        typer.Option(
            "--rtk/--no-rtk",
            help="When AI tools are selected, explicitly install RTK",
            show_default=False,
            rich_help_panel=AI_TOOLS_HELP_PANEL,
        ),
    ] = None,
    enable_context7: Annotated[
        bool | None,
        typer.Option(
            "--context7/--no-context7",
            help="When AI tools are selected, enable Context7 integration",
            show_default=False,
            rich_help_panel=AI_TOOLS_HELP_PANEL,
        ),
    ] = None,
    claude_context7_method: Annotated[
        Context7Method | None,
        typer.Option(
            "--claude-context7-method",
            help="Choose the Context7 transport for Claude Code",
            show_default=False,
            rich_help_panel=AI_TOOLS_HELP_PANEL,
        ),
    ] = None,
    codex_context7_method: Annotated[
        Context7Method | None,
        typer.Option(
            "--codex-context7-method",
            help="Choose the Context7 transport for Codex CLI",
            show_default=False,
            rich_help_panel=AI_TOOLS_HELP_PANEL,
        ),
    ] = None,
) -> None:
    """Run Ansible roles and task tags."""
    if not list_tags and not tags:
        typer.echo(ctx.get_help())
        return

    run_install(
        tags=[] if tags is None else list(tags),
        list_tags=list_tags,
        dry_run=dry_run,
        json_output=json_output,
        playbook=playbook,
        inventory=inventory,
        ask_vault_pass=ask_vault_pass,
        manage_claude_code=manage_claude_code,
        manage_codex=manage_codex,
        manage_rtk=manage_rtk,
        enable_context7=enable_context7,
        claude_context7_method=claude_context7_method,
        codex_context7_method=codex_context7_method,
    )


@app.command("ping", context_settings=HELP_CONTEXT_SETTINGS)
def _ping_command(
    inventory: Annotated[
        str | None,
        typer.Option(
            "--inventory",
            "-i",
            help="Specify an inventory alias from ~/.envmgr/config.toml",
        ),
    ] = None,
) -> None:
    """Test inventory connectivity with ansible ping."""
    run_ping(inventory=inventory)


@app.command("setup", context_settings=HELP_CONTEXT_SETTINGS)
def _setup_command() -> None:
    """Bootstrap the envmgr runtime under ~/.envmgr."""
    run_setup()


def _run_root_command(command_name: str, argv: list[str] | None = None) -> None:
    """Route retained root-command shims through the Typer app."""
    try:
        app(args=[command_name, *(argv or [])], prog_name=CLI_ROOT_COMMAND)
    except SystemExit as error:
        if error.code not in (0, None):
            raise


def doctor(argv: list[str] | None = None) -> None:
    """Retain backwards-compatible access to `envmgr doctor`."""
    _run_root_command("doctor", argv)


def history(argv: list[str] | None = None) -> None:
    """Retain backwards-compatible access to `envmgr history`."""
    _run_root_command("history", argv)


def install(argv: list[str] | None = None) -> None:
    """Retain backwards-compatible access to `envmgr install`."""
    _run_root_command("install", argv)


def ping(argv: list[str] | None = None) -> None:
    """Retain backwards-compatible access to `envmgr ping`."""
    _run_root_command("ping", argv)


def setup(argv: list[str] | None = None) -> None:
    """Retain backwards-compatible access to `envmgr setup`."""
    _run_root_command("setup", argv)


def main(argv: list[str] | None = None) -> None:
    """Run the Typer-based `envmgr` root app."""
    start_update_check_background()
    app(args=argv, prog_name=CLI_ROOT_COMMAND)
