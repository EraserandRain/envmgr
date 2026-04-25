from __future__ import annotations

import subprocess

import typer

from ..command_text import CLI_ROOT_COMMAND
from .dev_shared import PYTHON_CHECK_PATHS, require_repo_dev_context
from .shared import exit_with_error

COMMAND_NAME = "lint"
app = typer.Typer(add_completion=False, rich_markup_mode="rich")


def run_lint() -> None:
    """Run ruff linting and formatting on Python code."""
    require_repo_dev_context(COMMAND_NAME)

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
            "✗ Code formatting issues found. Run 'ruff format src/envmgr/ tests/' to fix."
        )
    except FileNotFoundError:
        exit_with_error(
            "Error: ruff command not found. Please ensure ruff is installed."
        )

    print("🎉 All Python linting checks passed!")


@app.command()
def _lint_command() -> None:
    """Run ruff linting and formatting on Python code."""
    run_lint()


def lint(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run ruff linting and formatting on Python code."""
    app(
        args=[] if argv is None else argv,
        prog_name=prog_name or f"{CLI_ROOT_COMMAND} {COMMAND_NAME}",
    )


def main() -> None:
    """Run the Ruff helper from its dedicated development command."""
    app(prog_name=COMMAND_NAME)
