from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal

import typer

from .command_text import CLI_ROOT_COMMAND
from .commands.doctor import run_doctor
from .commands.history import run_history
from .commands.install import run_install
from .commands.ping import run_ping
from .commands.setup import run_setup
from .commands.shared import (
    require_setup_completed as shared_require_setup_completed,
)
from .scaffold import ScaffoldError, generate_role

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    suggest_commands=True,
    rich_markup_mode="rich",
)

Context7Method = Literal["remote", "local"]


def require_setup_completed(
    command_name: str,
    *,
    envmgr_home: str | Path | None = None,
) -> None:
    """Keep the historical `scripts.main` helper surface for existing callers."""
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


def create(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Create a new Ansible role by prompting for a role name."""
    from .commands.legacy_argparse import build_command_parser, parse_command_args

    parser = build_command_parser(
        "create",
        description="Create a new Ansible role by prompting the user for a role name and generating the role directory.",
        prog_name=prog_name,
    )
    parser.add_argument("role", nargs="?", help="The name of the role to create")

    args = parse_command_args(parser, argv)

    if args.role:
        try:
            generate_role(args.role)
            print(f"Role '{args.role}' generated successfully.")
            print(
                f"Update roles/{args.role}/meta/envmgr.yml and add the role to the appropriate playbook."
            )
        except FileExistsError:
            print(f"Role '{args.role}' already exists.")
        except (FileNotFoundError, ScaffoldError) as error:
            print(error)
    else:
        parser.print_help()


def lint(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run ruff linting and formatting on Python code."""
    from .commands.lint import lint as lint_command

    lint_command(argv, prog_name=prog_name)


def ansible_lint(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run ansible-lint on the roles directory."""
    from .commands.ansible_check import ansible_lint as ansible_lint_command

    ansible_lint_command(argv, prog_name=prog_name)


def typecheck(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run mypy type checking on the Python source directories."""
    from .commands.typecheck import typecheck as typecheck_command

    typecheck_command(argv, prog_name=prog_name)


def validate(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run the project validation suite in one command."""
    from .commands.validate import validate as validate_command

    validate_command(argv, prog_name=prog_name)


def smoke_test(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run lightweight integration checks without installing software."""
    from .commands.smoke_test import smoke_test as smoke_test_command

    smoke_test_command(argv, prog_name=prog_name)


def doctor(argv: list[str] | None = None) -> None:
    """Keep the historical `scripts.main.doctor` helper surface."""
    app(args=["doctor", *(argv or [])], prog_name=CLI_ROOT_COMMAND)


def history(argv: list[str] | None = None) -> None:
    """Keep the historical `scripts.main.history` helper surface."""
    app(args=["history", *(argv or [])], prog_name=CLI_ROOT_COMMAND)


def install(argv: list[str] | None = None) -> None:
    """Keep the historical `scripts.main.install` helper surface."""
    app(args=["install", *(argv or [])], prog_name=CLI_ROOT_COMMAND)


def ping(argv: list[str] | None = None) -> None:
    """Keep the historical `scripts.main.ping` helper surface."""
    from .commands.ping import ping as legacy_ping

    legacy_ping(argv)


def setup(argv: list[str] | None = None) -> None:
    """Keep the historical `scripts.main.setup` helper surface."""
    from .commands.setup import setup as legacy_setup

    legacy_setup(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the Typer-based `envmgr` root app."""
    app(args=argv, prog_name=CLI_ROOT_COMMAND)


def create_entrypoint() -> None:
    """Run the role-scaffolding helper from its dedicated development command."""
    create(sys.argv[1:], prog_name="create")


def lint_entrypoint() -> None:
    """Run the Ruff helper from its dedicated development command."""
    lint(sys.argv[1:], prog_name="lint")


def ansible_lint_entrypoint() -> None:
    """Run the ansible-lint helper from its dedicated development command."""
    ansible_lint(sys.argv[1:], prog_name="ansible-check")


def typecheck_entrypoint() -> None:
    """Run the mypy helper from its dedicated development command."""
    typecheck(sys.argv[1:], prog_name="typecheck")


def validate_entrypoint() -> None:
    """Run the full validation helper from its dedicated development command."""
    validate(sys.argv[1:], prog_name="validate")


def smoke_test_entrypoint() -> None:
    """Run the smoke helper from its dedicated development command."""
    smoke_test(sys.argv[1:], prog_name="smoke-test")
