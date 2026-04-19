from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..runtime_config import get_runtime_paths
from ..services.runtime import load_runtime_run_history
from .doctor import abbreviate_home_in_text
from .shared import Colors, build_command_parser, parse_command_args


def get_runtime_history_status_text(status: str) -> str:
    """Render a colored status label for runtime history output."""
    text = status.upper()
    if status == "succeeded":
        return f"{Colors.GREEN}{text}{Colors.RESET}"
    if status in {"running"}:
        return f"{Colors.YELLOW}{text}{Colors.RESET}"
    return f"{Colors.RED}{text}{Colors.RESET}"


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


def history(argv: list[str] | None = None) -> None:
    """Show recent runtime subprocess records from ~/.envmgr/log/runs."""
    parser = build_command_parser(
        "history", description="Show recent envmgr runtime subprocess records"
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=10,
        help="Show at most this many recent records (default: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print recent runtime records as JSON",
    )

    args = parse_command_args(parser, argv)
    if args.limit <= 0:
        print(f"{Colors.RED}History limit must be greater than zero.{Colors.RESET}")
        raise SystemExit(1)

    paths = get_runtime_paths()
    configured_home = os.environ.get("ENVMGR_HOME")
    records = load_runtime_run_history(paths)
    selected_records = records[: args.limit]

    if args.json_output:
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

    print("Envmgr History")
    print(f"Runtime home  {runtime_home_value}{runtime_home_suffix}")
    print(f"Runs dir      {abbreviate_home_in_text(str(paths.runs_log_dir))}")

    if not records:
        print()
        print("No runtime subprocess history has been recorded yet.")
        return

    print(
        f"Showing {len(selected_records)} of {len(records)} recorded runtime commands"
    )
    print()

    for record in selected_records:
        status = str(record.get("status", "unknown"))
        return_code = record.get("return_code")
        return_code_text = "-" if return_code is None else str(return_code)
        print(
            f"- {record.get('started_at', '<unknown time>')} "
            f"[{get_runtime_history_status_text(status)}] "
            f"rc={return_code_text} "
            f"dur={get_runtime_history_duration_text(record.get('duration_seconds'))} "
            f"mode={record.get('mode', '-')}"
        )
        print(f"  {stringify_runtime_history_command(record.get('command'))}")
