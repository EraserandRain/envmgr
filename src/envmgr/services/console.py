from __future__ import annotations

from typing import Any, Protocol

from rich.text import Text


class InstallConsole(Protocol):
    """Console surface Install and the AI-tools wizard print and prompt through."""

    def print(self, *args: Any, **kwargs: Any) -> None: ...
    def warn(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def confirm(self, message: str, *, default: bool) -> bool: ...
    def prompt_text(self, message: str, *, default: str | None = None) -> str: ...


def print_section_title(
    console: InstallConsole,
    title: str,
    *,
    style: str = "bold cyan",
) -> None:
    console.print(Text(title, style=style))


def print_labeled_value(
    console: InstallConsole,
    label: str,
    value: str | Text,
    *,
    prefix: str = "  ",
) -> None:
    line = Text()
    line.append(f"{prefix}{label}: ", style="bold")
    if isinstance(value, Text):
        line.append_text(value)
    else:
        line.append(str(value))
    console.print(line)


def print_bullet_list(console: InstallConsole, title: str, values: list[str]) -> None:
    console.print()
    console.print(Text(title, style="bold"))
    for value in values:
        console.print(Text(f"  - {value}"))


def print_warning(console: InstallConsole, message: str) -> None:
    line = Text()
    line.append("Warning: ", style="bold yellow")
    line.append(message)
    console.print(line)
