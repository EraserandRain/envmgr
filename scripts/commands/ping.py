from __future__ import annotations

import subprocess

from ..runtime_config import ensure_runtime_layout
from ..services.runtime import run_runtime_subprocess
from .shared import (
    exit_with_error,
    print_command_heading,
    print_status,
    print_summary_line,
    require_setup_completed,
    resolve_inventory_option,
)


def run_ping(*, inventory: str | None) -> None:
    """Test connection to all hosts using ansible ping module."""
    require_setup_completed("ping")

    inventory_path, inventory_label = resolve_inventory_option(inventory)
    command = ["ansible", "-i", str(inventory_path), "-m", "ping", "all"]
    runtime_paths = ensure_runtime_layout()

    print_command_heading(
        "Envmgr Ping",
        subtitle="Test inventory connectivity with ansible ping.",
    )
    print_summary_line("Inventory", inventory_label)
    print_summary_line("Inventory path", inventory_path)
    print_status("Running ansible ping against all hosts...")

    try:
        run_runtime_subprocess(command, check=True, runtime_paths=runtime_paths)
    except subprocess.CalledProcessError as error:
        exit_with_error(f"Ping failed with exit code {error.returncode}")
    except FileNotFoundError:
        exit_with_error(
            "Error: ansible command not found. Please ensure ansible is installed."
        )

    print_status("Ping completed successfully.", tone="success")
