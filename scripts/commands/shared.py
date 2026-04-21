from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal, NoReturn

import typer
from rich.console import Console
from rich.rule import Rule
from rich.text import Text

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

StatusTone = Literal["info", "success", "warning"]
PromptBackend = Callable[[str, str | None], str]
ConfirmBackend = Callable[[str, bool], bool]

_STATUS_LABELS: dict[StatusTone, str] = {
    "info": "Info",
    "success": "Success",
    "warning": "Warning",
}
_STATUS_STYLES: dict[StatusTone, str] = {
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
}


def _abort_from_interrupt(error: KeyboardInterrupt) -> NoReturn:
    """Exit with a shell-friendly status code after an interrupted prompt."""
    console.print()
    raise typer.Exit(code=130) from error


def _default_prompt_backend(message: str, default: str | None) -> str:
    """Read a single text response using the current stdin/stdout streams."""
    prompt = message if default is None else f"{message} [{default}]"
    try:
        response = input(f"{prompt}: ")
    except EOFError:
        return "" if default is None else default
    except KeyboardInterrupt as error:
        _abort_from_interrupt(error)

    stripped = response.strip()
    if not stripped and default is not None:
        return default
    return stripped


def _default_confirm_backend(message: str, default: bool) -> bool:
    """Read a yes/no answer using the shared text prompt behavior."""
    hint = "Y/n" if default else "y/N"
    while True:
        prompt = f"{message} [{hint}]"
        try:
            response = input(f"{prompt}: ").strip().lower()
        except EOFError:
            return default
        except KeyboardInterrupt as error:
            _abort_from_interrupt(error)

        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False

        print("Please answer 'y' or 'n'.")


# Later workers can patch these callables to adopt Rich Prompt/Confirm without
# changing command call sites.
prompt_backend: PromptBackend = _default_prompt_backend
confirm_backend: ConfirmBackend = _default_confirm_backend


def exit_with_error(message: str, *, code: int = 1) -> NoReturn:
    """Print a user-facing error message and exit with a non-zero status."""
    error_console.print(Text(message, style="red"))
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

    console.print(
        Text.assemble(
            ("Setup required: ", "bold yellow"),
            f"'{command_name}' needs a bootstrapped envmgr runtime at "
            f"{runtime_paths.home}. Please {SETUP_HINT}.",
        )
    )
    raise SystemExit(1)


def print_command_heading(title: str, *, subtitle: str | None = None) -> None:
    """Render a consistent Rich heading for runtime-facing command output."""
    console.print(Rule(Text(title, style="bold cyan"), style="cyan"))
    if subtitle:
        console.print(Text(subtitle, style="dim"))


def print_summary_line(label: str, value: object) -> None:
    """Render a labeled summary line for command plans and runtime details."""
    line = Text()
    line.append(f"{label}: ", style="bold")
    line.append(str(value))
    console.print(line)


def print_status(message: str, *, tone: StatusTone = "info") -> None:
    """Render a short status line with a shared label and color treatment."""
    label = _STATUS_LABELS[tone]
    style = _STATUS_STYLES[tone]
    line = Text()
    line.append(f"{label}: ", style=f"bold {style}")
    line.append(message)
    console.print(line)


def print_warning(message: str) -> None:
    """Render a warning line using the shared runtime warning presentation."""
    print_status(message, tone="warning")


def prompt_text(message: str, *, default: str | None = None) -> str:
    """Ask for free-form input through the shared, patchable prompt backend."""
    return prompt_backend(message, default)


def confirm_choice(message: str, *, default: bool = False) -> bool:
    """Ask for a yes/no decision through the shared, patchable confirm backend."""
    return confirm_backend(message, default)
