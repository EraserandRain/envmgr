from __future__ import annotations

import argparse

from ..command_text import CLI_ROOT_COMMAND


def build_command_parser(
    command_name: str,
    description: str,
    *,
    prog_name: str | None = None,
) -> argparse.ArgumentParser:
    """Create a parser for legacy argparse-based command entrypoints."""
    return argparse.ArgumentParser(
        prog=prog_name or f"{CLI_ROOT_COMMAND} {command_name}",
        description=description,
    )


def parse_command_args(
    parser: argparse.ArgumentParser,
    argv: list[str] | None,
) -> argparse.Namespace:
    """Parse command arguments without inheriting the outer process argv."""
    return parser.parse_args([] if argv is None else argv)
