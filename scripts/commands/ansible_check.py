from __future__ import annotations

import subprocess

import typer

from ..command_text import CLI_ROOT_COMMAND
from .shared import exit_with_error

COMMAND_NAME = "ansible-check"
app = typer.Typer(add_completion=False, rich_markup_mode="rich")


def run_ansible_lint() -> None:
    """Run ansible-lint on the roles directory."""
    command = ["ansible-lint", "./roles"]

    print("Running Ansible linting...")

    try:
        subprocess.run(command, check=True)
        print("✓ Ansible lint passed")
    except subprocess.CalledProcessError as error:
        exit_with_error(f"✗ Ansible linting failed with exit code {error.returncode}")
    except FileNotFoundError:
        exit_with_error(
            "Error: ansible-lint command not found. Please ensure ansible-lint is installed."
        )


@app.command()
def _ansible_lint_command() -> None:
    """Run ansible-lint on the roles directory."""
    run_ansible_lint()


def ansible_lint(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run ansible-lint on the roles directory."""
    app(
        args=[] if argv is None else argv,
        prog_name=prog_name or f"{CLI_ROOT_COMMAND} {COMMAND_NAME}",
    )


def main() -> None:
    """Run the ansible-lint helper from its dedicated development command."""
    app(prog_name=COMMAND_NAME)
