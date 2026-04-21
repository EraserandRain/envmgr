from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from rich.text import Text

from ..runtime_config import get_runtime_paths
from ..services.runtime import load_runtime_run_history
from .doctor import abbreviate_home_in_text
from .shared import console, exit_with_error


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


def run_history(*, limit: int, json_output: bool) -> None:
    """Show recent runtime subprocess records from ~/.envmgr/log/runs."""
    if limit <= 0:
        exit_with_error("History limit must be greater than zero.")

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

    console.print("Envmgr History")

    runtime_home_line = Text("Runtime home  ")
    runtime_home_line.append(runtime_home_value)
    runtime_home_line.append(runtime_home_suffix)
    console.print(runtime_home_line)

    runs_dir_line = Text("Runs dir      ")
    runs_dir_line.append(abbreviate_home_in_text(str(paths.runs_log_dir)))
    console.print(runs_dir_line)

    if not records:
        console.print()
        console.print("No runtime subprocess history has been recorded yet.")
        return

    console.print(
        f"Showing {len(selected_records)} of {len(records)} recorded runtime commands"
    )
    console.print()

    for record in selected_records:
        status = str(record.get("status", "unknown"))
        return_code = record.get("return_code")
        return_code_text = "-" if return_code is None else str(return_code)

        summary_line = Text("- ")
        summary_line.append(str(record.get("started_at", "<unknown time>")))
        summary_line.append(" [")
        summary_line.append(get_runtime_history_status_text(status))
        summary_line.append("] ")
        summary_line.append(f"rc={return_code_text} ")
        summary_line.append(
            f"dur={get_runtime_history_duration_text(record.get('duration_seconds'))} "
        )
        summary_line.append(f"mode={record.get('mode', '-')}")
        console.print(summary_line)

        command_line = Text("  ")
        command_line.append(stringify_runtime_history_command(record.get("command")))
        console.print(command_line)
