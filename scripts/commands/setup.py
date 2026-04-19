from __future__ import annotations

import subprocess

from ..runtime_config import (
    ConfigError,
    ensure_runtime_layout,
    mark_runtime_setup_complete,
)
from ..services.runtime import run_runtime_subprocess
from .shared import exit_with_error


def run_setup() -> None:
    """Initialize ~/.envmgr and install the Ansible content envmgr needs."""
    print("Setting up envmgr runtime...")
    print("1. Initializing ~/.envmgr...")
    try:
        runtime_paths = ensure_runtime_layout()
        print(f"✓ Runtime config initialized at {runtime_paths.config_file}")
        print(f"  - Ansible log: {runtime_paths.ansible_log_file}")
        print(f"  - Galaxy roles cache: {runtime_paths.galaxy_roles_dir}")
        print(f"  - Galaxy collections cache: {runtime_paths.galaxy_collections_dir}")
    except ConfigError as error:
        exit_with_error(f"✗ Failed to initialize ~/.envmgr: {error}")
    except OSError as error:
        exit_with_error(f"✗ Failed to initialize ~/.envmgr: {error}")

    print("2. Installing ansible roles and collections...")
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
        print("✓ Ansible roles and collections installed successfully")
    except subprocess.CalledProcessError as error:
        exit_with_error(f"✗ Failed to install ansible roles or collections: {error}")
    except FileNotFoundError:
        exit_with_error(
            "✗ Error: ansible-galaxy command not found. Please ensure ansible is installed."
        )

    print("🎉 Setup completed successfully!")


def setup(argv: list[str] | None = None) -> None:
    """Initialize ~/.envmgr and install the Ansible content envmgr needs."""
    from .legacy_argparse import build_command_parser, parse_command_args

    parse_command_args(
        build_command_parser(
            "setup",
            "Initialize ~/.envmgr and install the Ansible content envmgr needs at runtime.",
        ),
        argv,
    )
    run_setup()
