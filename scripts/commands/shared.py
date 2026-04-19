from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console

from ..catalog import CatalogError
from ..command_text import SETUP_HINT
from ..runtime_config import (
    ConfigError,
    get_runtime_paths,
    is_runtime_setup_complete,
    resolve_inventory_reference,
)
from ..services.install import load_available_tags as load_available_tags_service

console = Console()
error_console = Console(stderr=True)


def exit_with_error(message: str, *, code: int = 1) -> NoReturn:
    """Print a user-facing error message and exit with a non-zero status."""
    error_console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=code)


def load_available_tags() -> tuple[list[str], list[str]]:
    """Load role-level and task-level tags and surface metadata errors."""
    try:
        return load_available_tags_service()
    except CatalogError as error:
        exit_with_error(f"Metadata error: {error}")


def resolve_inventory_option(selected_inventory: str | None) -> tuple[Path, str]:
    """Resolve an inventory alias from ~/.envmgr/config.toml."""
    try:
        return resolve_inventory_reference(selected_inventory)
    except ConfigError as error:
        exit_with_error(f"Configuration error: {error}")


def require_setup_completed(
    command_name: str,
    *,
    envmgr_home: str | Path | None = None,
) -> None:
    """Exit with setup guidance when the runtime has not been bootstrapped yet."""
    runtime_paths = get_runtime_paths(envmgr_home)
    if is_runtime_setup_complete(runtime_paths):
        return

    exit_with_error(
        f"Setup required: '{command_name}' needs a bootstrapped envmgr runtime at "
        f"{runtime_paths.home}. Please {SETUP_HINT}."
    )
