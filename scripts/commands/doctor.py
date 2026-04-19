from __future__ import annotations

import json
import os

import typer
from rich.table import Table
from rich.text import Text

from ..services.doctor import (
    DOCTOR_OK,
    DOCTOR_WARN,
    DoctorCheck,
    DoctorReport,
    build_doctor_json_payload,
    build_doctor_report,
    get_doctor_overall_status,
    summarize_doctor_report,
)
from .shared import console


def render_doctor_status_text(status: str) -> Text:
    """Render a colored uppercase doctor status label."""
    style = "red"
    label = "FAIL"
    if status == DOCTOR_OK:
        style = "green"
        label = "OK"
    elif status == DOCTOR_WARN:
        style = "yellow"
        label = "WARN"
    return Text(label, style=style)


def get_doctor_check_label(name: str) -> str:
    """Return a compact label for a doctor check."""
    if name.startswith("command `") and name.endswith("`"):
        return name[len("command `") : -1]
    if name.startswith("inventory alias `") and name.endswith("`"):
        return "inventory " + name[len("inventory alias `") : -1]
    if name == "runtime directories":
        return "runtime dirs"
    if name == "setup state":
        return "setup"
    return name


def get_doctor_check_detail(check: DoctorCheck) -> str:
    """Return a concise human-readable detail for a doctor check."""
    return abbreviate_home_in_text(check.detail)


def abbreviate_home_in_text(value: str) -> str:
    """Render paths under the current user's home directory with `~`."""
    home = os.path.expanduser("~")
    if value == home:
        return "~"
    return value.replace(f"{home}/", "~/")


def build_doctor_checks_table(checks: list[DoctorCheck]) -> Table:
    """Render doctor checks as a compact Rich table."""
    table = Table(show_header=True)
    table.add_column("STATUS", no_wrap=True)
    table.add_column("CHECK", no_wrap=True)
    table.add_column("DETAIL")

    for check in checks:
        table.add_row(
            render_doctor_status_text(check.status),
            get_doctor_check_label(check.name),
            get_doctor_check_detail(check),
        )

    return table


def print_doctor_overview(report: DoctorReport, configured_home: str | None) -> None:
    """Print the high-level context for a doctor report."""
    runtime_home_value = abbreviate_home_in_text(str(report.paths.home))
    if configured_home:
        runtime_home_value += " (from ENVMGR_HOME)"
    else:
        runtime_home_value += " (default)"

    context_rows: list[tuple[str, str]] = [("Runtime home", runtime_home_value)]
    default_parts: list[str] = []
    if report.default_inventory is not None:
        default_parts.append(f"inventory={report.default_inventory}")
    if report.default_playbook_path is not None:
        default_parts.append(f"playbook={report.default_playbook_path}")
    if default_parts:
        context_rows.append(("Defaults", " ".join(default_parts)))

    label_width = max(len(label) for label, _value in context_rows)
    for label, value in context_rows:
        print(f"{label:<{label_width}}  {value}")


def run_doctor(*, json_output: bool) -> None:
    """Inspect envmgr runtime health without mutating ~/.envmgr."""
    report = build_doctor_report()
    configured_home = os.environ.get("ENVMGR_HOME")
    ok_count, warn_count, fail_count = summarize_doctor_report(report)

    if json_output:
        print(
            json.dumps(
                build_doctor_json_payload(
                    report,
                    configured_home=configured_home,
                ),
                indent=2,
            )
        )
        if fail_count:
            raise typer.Exit(code=1)
        return

    overall_status = get_doctor_overall_status(report)
    summary = f"Summary: {ok_count} ok, {warn_count} warn, {fail_count} fail"
    heading = Text("Envmgr Doctor [")
    heading.append(render_doctor_status_text(overall_status))
    heading.append("]")
    console.print(heading)
    console.print(summary)
    console.print()
    print_doctor_overview(report, configured_home)
    console.print()
    console.print(build_doctor_checks_table(report.checks))

    if fail_count:
        raise typer.Exit(code=1)
