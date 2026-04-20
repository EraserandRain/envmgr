from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from .command_text import CLI_APP_HELP, CLI_ROOT_COMMAND
from .commands.doctor import run_doctor
from .commands.history import run_history
from .commands.install import run_install
from .commands.ping import run_ping
from .commands.setup import run_setup
from .commands.shared import (
    require_setup_completed as shared_require_setup_completed,
)

app = typer.Typer(
    help=CLI_APP_HELP,
    no_args_is_help=True,
    add_completion=False,
    suggest_commands=True,
    rich_markup_mode="rich",
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


@app.command("doctor")
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


@app.command("history")
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


@app.command("install")
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
        ),
    ] = False,
    playbook: Annotated[
        str | None,
        typer.Option(
            "--playbook",
            help="Specify a playbook file explicitly when tags are ambiguous",
        ),
    ] = None,
    inventory: Annotated[
        str | None,
        typer.Option(
            "--inventory",
            "-i",
            help="Specify an inventory alias from ~/.envmgr/config.toml",
        ),
    ] = None,
    ask_vault_pass: Annotated[
        bool,
        typer.Option(
            "--ask-vault-pass",
            help="Ask for vault password",
        ),
    ] = False,
    manage_claude_code: Annotated[
        bool | None,
        typer.Option(
            "--claude-code/--no-claude-code",
            help="When AI tools are selected, explicitly install Claude Code",
            show_default=False,
        ),
    ] = None,
    manage_codex: Annotated[
        bool | None,
        typer.Option(
            "--codex/--no-codex",
            help="When AI tools are selected, explicitly install Codex CLI",
            show_default=False,
        ),
    ] = None,
    manage_rtk: Annotated[
        bool | None,
        typer.Option(
            "--rtk/--no-rtk",
            help="When AI tools are selected, explicitly install RTK",
            show_default=False,
        ),
    ] = None,
    enable_context7: Annotated[
        bool | None,
        typer.Option(
            "--context7/--no-context7",
            help="When AI tools are selected, enable Context7 integration",
            show_default=False,
        ),
    ] = None,
    claude_context7_method: Annotated[
        Context7Method | None,
        typer.Option(
            "--claude-context7-method",
            help="Choose the Context7 transport for Claude Code",
            show_default=False,
        ),
    ] = None,
    codex_context7_method: Annotated[
        Context7Method | None,
        typer.Option(
            "--codex-context7-method",
            help="Choose the Context7 transport for Codex CLI",
            show_default=False,
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


@app.command("ping")
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


@app.command("setup")
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
    app(args=argv, prog_name=CLI_ROOT_COMMAND)
