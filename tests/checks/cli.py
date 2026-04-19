from __future__ import annotations

from unittest.mock import patch

from click.testing import Result
from typer.testing import CliRunner

from scripts.main import app

CLI_RUNNER = CliRunner()


def invoke_envmgr(*args: str) -> Result:
    return CLI_RUNNER.invoke(app, list(args), prog_name="envmgr")


def check_dispatcher_routes_install_subcommand() -> None:
    help_result = invoke_envmgr("--help")
    if help_result.exit_code != 0:
        raise AssertionError(
            "expected `envmgr --help` to exit successfully"
            f"\noutput:\n{help_result.output}"
        )

    help_output = help_result.output
    for expected_fragment in (
        "Usage: envmgr",
        "doctor",
        "history",
        "install",
        "ping",
        "setup",
    ):
        if expected_fragment not in help_output:
            raise AssertionError(
                f"expected `envmgr --help` to include {expected_fragment!r}"
            )
    if "validate" in help_output:
        raise AssertionError(
            "expected `envmgr --help` to omit development-only subcommands"
        )

    with patch(
        "scripts.commands.install.load_available_tags",
        return_value=(["zsh"], ["codex"]),
    ):
        result = invoke_envmgr("install", "-l")

    if result.exit_code != 0:
        raise AssertionError(
            "expected dispatcher to route to the install subcommand"
            f"\noutput:\n{result.output}"
        )

    output = result.output
    if "Envmgr available tags:" not in output:
        raise AssertionError("expected dispatcher to route to the install subcommand")
    if "  - zsh" not in output:
        raise AssertionError("expected dispatcher to print install role tags")
    if "  - codex" not in output:
        raise AssertionError("expected dispatcher to print install task tags")


def check_dispatcher_rejects_dev_only_subcommands() -> None:
    result = invoke_envmgr("validate")
    if result.exit_code != 2:
        raise AssertionError(
            "expected dispatcher to reject dev-only subcommands with exit code 2"
            f"\noutput:\n{result.output}"
        )

    output = result.output
    if "No such command 'validate'" not in output:
        raise AssertionError(
            "expected dispatcher rejection to use Click/Typer unknown-command wording"
        )
    if "Try 'envmgr --help' for help." not in output:
        raise AssertionError(
            "expected dispatcher rejection to point users at `envmgr --help`"
        )
