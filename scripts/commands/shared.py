from __future__ import annotations

import argparse
from pathlib import Path
from typing import NoReturn

from ..catalog import CatalogError
from ..command_text import CLI_ROOT_COMMAND, SETUP_HINT
from ..runtime_config import (
    ConfigError,
    get_runtime_paths,
    is_runtime_setup_complete,
    resolve_inventory_reference,
)
from ..services.install import load_available_tags as load_available_tags_service


class Colors:
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    RESET = "\033[0m"


def exit_with_error(message: str, *, code: int = 1) -> NoReturn:
    """Print a user-facing error message and exit with a non-zero status."""
    print(f"{Colors.RED}{message}{Colors.RESET}")
    raise SystemExit(code)


def build_command_parser(
    command_name: str,
    description: str,
    *,
    prog_name: str | None = None,
) -> argparse.ArgumentParser:
    """Create a parser for one `envmgr <command>` subcommand."""
    return argparse.ArgumentParser(
        prog=prog_name or f"{CLI_ROOT_COMMAND} {command_name}",
        description=description,
    )


def parse_command_args(
    parser: argparse.ArgumentParser,
    argv: list[str] | None,
) -> argparse.Namespace:
    """Parse subcommand arguments without inheriting outer `sys.argv` by default."""
    return parser.parse_args([] if argv is None else argv)


def load_available_tags() -> tuple[list[str], list[str]]:
    """Load role-level and task-level tags and surface metadata errors."""
    try:
        return load_available_tags_service()
    except CatalogError as error:
        print(f"{Colors.RED}Metadata error: {error}{Colors.RESET}")
        raise SystemExit(1) from error


def resolve_inventory_option(selected_inventory: str | None) -> tuple[Path, str]:
    """Resolve an inventory alias from ~/.envmgr/config.toml."""
    try:
        return resolve_inventory_reference(selected_inventory)
    except ConfigError as error:
        print(f"{Colors.RED}Configuration error: {error}{Colors.RESET}")
        raise SystemExit(1) from error


def require_setup_completed(
    command_name: str,
    *,
    envmgr_home: str | Path | None = None,
) -> None:
    """Exit with setup guidance when the runtime has not been bootstrapped yet."""
    runtime_paths = get_runtime_paths(envmgr_home)
    if is_runtime_setup_complete(runtime_paths):
        return

    print(
        f"{Colors.RED}Setup required: '{command_name}' needs a bootstrapped envmgr "
        f"runtime at {runtime_paths.home}. Please {SETUP_HINT}."
        f"{Colors.RESET}"
    )
    raise SystemExit(1)
