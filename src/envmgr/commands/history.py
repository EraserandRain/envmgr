from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from rich.table import Table
from rich.text import Text

from ..runtime_config import get_runtime_paths
from ..services.runtime import load_runtime_run_history
from .doctor import abbreviate_home_in_text
from .shared import (
    console,
    exit_with_error,
    print_command_heading,
    print_status,
    print_summary_line,
)


def get_runtime_history_status_text(status: str) -> str:
    """Render an uppercase status label for runtime history output."""
    return status.upper()


def get_runtime_history_duration_text(value: Any) -> str:
    """Render a short duration cell for runtime history output."""
    if isinstance(value, int | float):
        return f"{value:.3f}s"
    return "-"


def stringify_runtime_history_command(value: Any) -> str:
    """Render a stored runtime command as a human-readable shell command."""
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return " ".join(value)
    return "<unknown command>"


def build_runtime_history_table(records: list[dict[str, Any]]) -> Table:
    """Build a human-readable table for runtime subprocess history."""
    table = Table(show_header=True)
    table.add_column("RECORD", no_wrap=True)
    table.add_column("FIELD", no_wrap=True)
    table.add_column("VALUE", overflow="fold")

    for index, record in enumerate(records, start=1):
        return_code = record.get("return_code")
        details = (
            f"rc={'-' if return_code is None else return_code} "
            f"dur={get_runtime_history_duration_text(record.get('duration_seconds'))} "
            f"mode={record.get('mode', '-')}"
        )
        table.add_row(
            str(index), "STARTED", Text(str(record.get("started_at", "<unknown time>")))
        )
        table.add_row(
            "",
            "STATUS",
            Text(get_runtime_history_status_text(str(record.get("status", "unknown")))),
        )
        table.add_row("", "DETAILS", Text(details))
        table.add_row(
            "",
            "COMMAND",
            Text(stringify_runtime_history_command(record.get("command"))),
        )

    return table


def run_history(*, limit: int, json_output: bool) -> None:
    """Show recent runtime subprocess records from ~/.envmgr/log/runs."""
    if limit <= 0:
        exit_with_error(
            "History limit must be greater than zero. Next: pass --limit with a positive integer."
        )

    paths = get_runtime_paths()
    configured_home = os.environ.get("ENVMGR_HOME")
    records = load_runtime_run_history(paths)
    selected_records = records[:limit]

    if json_output:
        payload = {
            "runtime": {
                "home": str(paths.home),
                "configured_home": (
                    str(Path(configured_home).expanduser().resolve())
                    if configured_home
                    else None
                ),
                "runs_log_dir": str(paths.runs_log_dir),
            },
            "count": len(selected_records),
            "total": len(records),
            "records": selected_records,
        }
        print(json.dumps(payload, indent=2))
        return

    runtime_home_value = abbreviate_home_in_text(str(paths.home))
    runtime_home_suffix = " (from ENVMGR_HOME)" if configured_home else " (default)"

    print_command_heading("Envmgr History")
    print_summary_line("Runtime home", runtime_home_value + runtime_home_suffix)
    print_summary_line("Runs dir", abbreviate_home_in_text(str(paths.runs_log_dir)))

    if not records:
        console.print()
        print_status("No runtime subprocess history has been recorded yet.")
        return

    print_status(
        f"Showing {len(selected_records)} of {len(records)} recorded runtime commands"
    )
    console.print()
    console.print(build_runtime_history_table(selected_records))
