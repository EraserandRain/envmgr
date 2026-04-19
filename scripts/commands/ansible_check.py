from __future__ import annotations

import subprocess

from .legacy_argparse import build_command_parser, parse_command_args
from .shared import exit_with_error


def ansible_lint(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run ansible-lint on the roles directory."""
    parse_command_args(
        build_command_parser(
            "ansible-check",
            "Run ansible-lint on the roles directory.",
            prog_name=prog_name,
        ),
        argv,
    )

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
