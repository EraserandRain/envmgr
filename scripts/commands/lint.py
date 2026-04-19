from __future__ import annotations

import subprocess

from .dev_shared import PYTHON_CHECK_PATHS
from .shared import build_command_parser, exit_with_error, parse_command_args


def lint(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run ruff linting and formatting on Python code."""
    parse_command_args(
        build_command_parser(
            "lint",
            "Run ruff linting and formatting on Python code.",
            prog_name=prog_name,
        ),
        argv,
    )

    print("Running Python code linting with ruff...")
    check_command = ["ruff", "check", *PYTHON_CHECK_PATHS]
    print("1. Running ruff check...")

    try:
        subprocess.run(check_command, check=True)
        print("✓ Ruff check passed")
    except subprocess.CalledProcessError as error:
        exit_with_error(f"✗ Ruff check failed with exit code {error.returncode}")
    except FileNotFoundError:
        exit_with_error(
            "Error: ruff command not found. Please ensure ruff is installed."
        )

    format_command = ["ruff", "format", "--check", *PYTHON_CHECK_PATHS]
    print("2. Running ruff format check...")

    try:
        subprocess.run(format_command, check=True)
        print("✓ Ruff format check passed")
    except subprocess.CalledProcessError:
        exit_with_error(
            "✗ Code formatting issues found. Run 'ruff format scripts/ tests/' to fix."
        )
    except FileNotFoundError:
        exit_with_error(
            "Error: ruff command not found. Please ensure ruff is installed."
        )

    print("🎉 All Python linting checks passed!")
