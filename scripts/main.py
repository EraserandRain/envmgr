from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from .command_text import CLI_ROOT_COMMAND
from .commands.doctor import doctor
from .commands.history import history
from .commands.install import install
from .commands.ping import ping
from .commands.setup import setup
from .commands.shared import (
    Colors,
    build_command_parser,
    parse_command_args,
)
from .commands.shared import (
    require_setup_completed as shared_require_setup_completed,
)
from .scaffold import ScaffoldError, generate_role

CommandHandler = Callable[[list[str] | None], None]


def require_setup_completed(
    command_name: str,
    *,
    envmgr_home: str | Path | None = None,
) -> None:
    """Keep the historical `scripts.main` helper surface for existing callers."""
    shared_require_setup_completed(command_name, envmgr_home=envmgr_home)


def create(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Create a new Ansible role by prompting for a role name."""
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
            print(f"{Colors.RED}{error}{Colors.RESET}")
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


COMMAND_SUMMARIES: dict[str, str] = {
    "doctor": "Inspect envmgr runtime health.",
    "history": "Show recent runtime subprocess records.",
    "install": "Run Ansible roles and task tags.",
    "ping": "Test inventory connectivity with ansible ping.",
    "setup": "Bootstrap the envmgr runtime under ~/.envmgr.",
}

COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "doctor": doctor,
    "history": history,
    "install": install,
    "ping": ping,
    "setup": setup,
}


def build_dispatcher_parser() -> argparse.ArgumentParser:
    """Create the top-level `envmgr` dispatcher parser."""
    commands_text = "\n".join(
        f"  {command_name:<13} {summary}"
        for command_name, summary in COMMAND_SUMMARIES.items()
    )
    parser = argparse.ArgumentParser(
        prog=CLI_ROOT_COMMAND,
        description="envmgr command dispatcher",
        epilog=(
            "Available commands:\n"
            f"{commands_text}\n\n"
            f"Use `{CLI_ROOT_COMMAND} <command> --help` for command-specific options."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=sorted(COMMAND_HANDLERS),
        help="Subcommand to run",
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Dispatch `envmgr <subcommand>` to the appropriate command handler."""
    parser = build_dispatcher_parser()
    parsed_args = parser.parse_args(argv)

    if parsed_args.command is None:
        parser.print_help()
        return

    COMMAND_HANDLERS[parsed_args.command](parsed_args.args)


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
