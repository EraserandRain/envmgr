from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, NoReturn

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.text import Text

from ..runtime_config import ConfigError, resolve_inventory_reference
from ..services.runtime import (
    require_setup_completed as _services_require_setup_completed,
)

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


class RichInstallConsole:
    """Bind the shared Rich console and prompt helpers into the Install console seam."""

    def print(self, *args: Any, **kwargs: Any) -> None:
        console.print(*args, **kwargs)

    def warn(self, message: str) -> None:
        error_console.print(Text(message, style="yellow"))

    def error(self, message: str) -> None:
        error_console.print(Text(message, style="red"))

    def confirm(self, message: str, *, default: bool) -> bool:
        return confirm_choice(message, default=default)

    def prompt_text(self, message: str, *, default: str | None = None) -> str:
        return prompt_text(message, default=default)


def _abort_from_interrupt(error: KeyboardInterrupt) -> NoReturn:
    """Exit with a shell-friendly status code after an interrupted prompt."""
    console.print()
    raise typer.Exit(code=130) from error


def _default_prompt_backend(message: str, default: str | None) -> str:
    """Read a single text response using Rich's prompt renderer."""
    try:
        if default is None:
            return str(Prompt.ask(message, console=console))
        return str(Prompt.ask(message, console=console, default=default))
    except EOFError:
        return "" if default is None else default


def _default_confirm_backend(message: str, default: bool) -> bool:
    """Read a yes/no answer using Rich's confirm renderer."""
    try:
        return bool(Confirm.ask(message, console=console, default=default))
    except EOFError:
        return default


# Tests can patch these callables without changing command prompt call sites.
prompt_backend: PromptBackend = _default_prompt_backend
confirm_backend: ConfirmBackend = _default_confirm_backend


def exit_with_error(message: str, *, code: int = 1) -> NoReturn:
    """Print a user-facing error message and exit with a non-zero status."""
    error_console.print(Text(message, style="red"))
    raise typer.Exit(code=code)


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
    _services_require_setup_completed(
        command_name,
        envmgr_home=envmgr_home,
        console=error_console,
    )


def print_command_heading(title: str, *, subtitle: str | None = None) -> None:
    """Render a consistent Rich heading for runtime-facing command output."""
    console.print(Rule(Text(title, style="bold cyan"), style="cyan"))
    if subtitle:
        console.print(Text(subtitle, style="dim"))


def print_summary_line(label: str, value: object) -> None:
    """Render a labeled summary line for command plans and runtime details."""
    line = Text()
    line.append(f"{label}: ", style="bold")
    if isinstance(value, Text):
        line.append_text(value)
    else:
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


def print_section_title(title: str, *, style: str = "bold cyan") -> None:
    """Render a compact section title for runtime command output."""
    console.print(Text(title, style=style))


def print_bullet_list(title: str, values: list[str]) -> None:
    """Render a titled bullet list through the shared runtime console."""
    console.print()
    console.print(Text(title, style="bold"))
    for value in values:
        console.print(Text(f"  - {value}"))


def print_labeled_value(
    label: str,
    value: str | Text,
    *,
    prefix: str = "  ",
) -> None:
    """Render a prefixed label/value line while preserving literal text values."""
    line = Text()
    line.append(f"{prefix}{label}: ", style="bold")
    if isinstance(value, Text):
        line.append_text(value)
    else:
        line.append(value)
    console.print(line)


def prompt_text(message: str, *, default: str | None = None) -> str:
    """Ask for free-form input through the shared, patchable prompt backend."""
    try:
        return prompt_backend(message, default)
    except KeyboardInterrupt as error:
        _abort_from_interrupt(error)


def confirm_choice(message: str, *, default: bool = False) -> bool:
    """Ask for a yes/no decision through the shared, patchable confirm backend."""
    try:
        return confirm_backend(message, default)
    except KeyboardInterrupt as error:
        _abort_from_interrupt(error)
