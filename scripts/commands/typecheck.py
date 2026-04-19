from __future__ import annotations

import subprocess

from .dev_shared import PYTHON_CHECK_PATHS
from .shared import build_command_parser, exit_with_error, parse_command_args


def typecheck(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run mypy type checking on the Python source directories."""
    parse_command_args(
        build_command_parser(
            "typecheck",
            "Run mypy type checking on the Python source directories.",
            prog_name=prog_name,
        ),
        argv,
    )

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
