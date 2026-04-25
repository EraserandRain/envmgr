from __future__ import annotations

import subprocess

import typer

from ..command_text import CLI_ROOT_COMMAND
from .dev_shared import PYTHON_CHECK_PATHS, require_repo_dev_context
from .shared import exit_with_error

COMMAND_NAME = "typecheck"
app = typer.Typer(add_completion=False, rich_markup_mode="rich")


def run_typecheck() -> None:
    """Run mypy type checking on the Python source directories."""
    require_repo_dev_context(COMMAND_NAME)

    command = ["mypy", *PYTHON_CHECK_PATHS]

    print("Running type checking with mypy...")

    try:
        subprocess.run(command, check=True)
        print("✓ Type checking passed")
    except subprocess.CalledProcessError as error:
        exit_with_error(f"✗ Type checking failed with exit code {error.returncode}")
    except FileNotFoundError:
        exit_with_error(
            "Error: mypy command not found. Please ensure mypy is installed."
        )


@app.command()
def _typecheck_command() -> None:
    """Run mypy type checking on the Python source directories."""
    run_typecheck()


def typecheck(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run mypy type checking on the Python source directories."""
    app(
        args=[] if argv is None else argv,
        prog_name=prog_name or f"{CLI_ROOT_COMMAND} {COMMAND_NAME}",
    )


def main() -> None:
    """Run the mypy helper from its dedicated development command."""
    app(prog_name=COMMAND_NAME)
