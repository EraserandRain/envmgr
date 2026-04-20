from __future__ import annotations

import subprocess

from ..runtime_config import (
    ConfigError,
    ensure_runtime_layout,
    mark_runtime_setup_complete,
)
from ..services.runtime import run_runtime_subprocess
from .shared import (
    exit_with_error,
    print_command_heading,
    print_status,
    print_summary_line,
)


def run_setup() -> None:
    """Initialize ~/.envmgr and install the Ansible content envmgr needs."""
    print_command_heading(
        "Envmgr Setup",
        subtitle="Bootstrap the envmgr runtime under ~/.envmgr.",
    )
    print_status("Initializing ~/.envmgr...")
    try:
        runtime_paths = ensure_runtime_layout()
    except ConfigError as error:
        exit_with_error(f"Failed to initialize ~/.envmgr: {error}")
    except OSError as error:
        exit_with_error(f"Failed to initialize ~/.envmgr: {error}")

    print_summary_line("Runtime config", runtime_paths.config_file)
    print_summary_line("Ansible log", runtime_paths.ansible_log_file)
    print_summary_line("Galaxy roles cache", runtime_paths.galaxy_roles_dir)
    print_summary_line(
        "Galaxy collections cache",
        runtime_paths.galaxy_collections_dir,
    )
    print_status("Installing Ansible roles and collections...")
    try:
        run_runtime_subprocess(
            [
                "ansible-galaxy",
                "role",
                "install",
                "-p",
                str(runtime_paths.galaxy_roles_dir),
                "-r",
                "requirements.yaml",
            ],
            check=True,
            runtime_paths=runtime_paths,
        )
        run_runtime_subprocess(
            [
                "ansible-galaxy",
                "collection",
                "install",
                "-p",
                str(runtime_paths.galaxy_collections_dir),
                "-r",
                "requirements.yaml",
            ],
            check=True,
            runtime_paths=runtime_paths,
        )
        mark_runtime_setup_complete(runtime_paths)
    except subprocess.CalledProcessError as error:
        exit_with_error(f"Failed to install ansible roles or collections: {error}")
    except FileNotFoundError:
        exit_with_error(
            "Error: ansible-galaxy command not found. Please ensure ansible is installed."
        )

    print_status(
        "Ansible roles and collections installed successfully.", tone="success"
    )
    print_status("Setup completed successfully.", tone="success")


def setup(argv: list[str] | None = None) -> None:
    """Initialize ~/.envmgr using the Typer-based root CLI."""
    from ..main import main as root_main

    root_main(["setup", *(argv or [])])
