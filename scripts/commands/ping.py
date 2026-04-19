from __future__ import annotations

import subprocess

from ..runtime_config import ensure_runtime_layout
from ..services.runtime import run_runtime_subprocess
from .shared import (
    build_command_parser,
    exit_with_error,
    parse_command_args,
    require_setup_completed,
    resolve_inventory_option,
)


def ping(argv: list[str] | None = None) -> None:
    """Test connection to all hosts using ansible ping module."""
    parser = build_command_parser(
        "ping", description="Test connection to all hosts using ansible ping module"
    )
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )

    args = parse_command_args(parser, argv)

    require_setup_completed("ping")

    inventory_path, inventory_label = resolve_inventory_option(args.inventory)
    command = ["ansible", "-i", str(inventory_path), "-m", "ping", "all"]
    runtime_paths = ensure_runtime_layout()

    print(f"Testing connection with inventory: {inventory_label} -> {inventory_path}")

    try:
        run_runtime_subprocess(command, check=True, runtime_paths=runtime_paths)
    except subprocess.CalledProcessError as error:
        exit_with_error(f"Ping failed with exit code {error.returncode}")
    except FileNotFoundError:
        exit_with_error(
            "Error: ansible command not found. Please ensure ansible is installed."
        )
