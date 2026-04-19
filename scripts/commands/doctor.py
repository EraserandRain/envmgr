from __future__ import annotations

import json
import os
import shutil
import textwrap

from ..services.doctor import (
    DOCTOR_OK,
    DoctorCheck,
    DoctorReport,
    build_doctor_json_payload,
    build_doctor_report,
    get_doctor_overall_status,
    summarize_doctor_report,
)
from .shared import Colors, build_command_parser, parse_command_args


def render_doctor_status_text(status: str) -> str:
    """Render a colored uppercase doctor status label."""
    text = status.upper()
    if status == DOCTOR_OK:
        return f"{Colors.GREEN}{text}{Colors.RESET}"
    if status == "warn":
        return f"{Colors.YELLOW}{text}{Colors.RESET}"
    return f"{Colors.RED}{text}{Colors.RESET}"


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


def get_doctor_status_cell(status: str, width: int) -> str:
    """Render a padded status cell for doctor tables."""
    plain_status = status.upper().ljust(width)
    if status == DOCTOR_OK:
        return f"{Colors.GREEN}{plain_status}{Colors.RESET}"
    if status == "warn":
        return f"{Colors.YELLOW}{plain_status}{Colors.RESET}"
    return f"{Colors.RED}{plain_status}{Colors.RESET}"


def render_doctor_checks_table(checks: list[DoctorCheck]) -> str:
    """Render doctor checks as a compact ASCII table."""
    status_width = len("STATUS")
    labels = [get_doctor_check_label(check.name) for check in checks]
    label_width = min(
        max([len("CHECK"), *(len(label) for label in labels)], default=len("CHECK")),
        20,
    )
    terminal_width = shutil.get_terminal_size(fallback=(100, 20)).columns
    detail_width = max(24, terminal_width - status_width - label_width - 6)

    lines = [
        f"{'STATUS':<{status_width}}  {'CHECK':<{label_width}}  DETAIL",
        f"{'-' * status_width}  {'-' * label_width}  {'-' * detail_width}",
    ]

    for check, label in zip(checks, labels, strict=True):
        detail_lines = textwrap.wrap(get_doctor_check_detail(check), width=detail_width)
        if not detail_lines:
            detail_lines = [""]
        lines.append(
            f"{get_doctor_status_cell(check.status, status_width)}  "
            f"{label:<{label_width}}  {detail_lines[0]}"
        )
        for continuation in detail_lines[1:]:
            lines.append(f"{' ' * status_width}  {' ' * label_width}  {continuation}")

    return "\n".join(lines)


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


def doctor(argv: list[str] | None = None) -> None:
    """Inspect envmgr runtime health without mutating ~/.envmgr."""
    parser = build_command_parser(
        "doctor",
        description="Inspect envmgr runtime health without modifying the runtime",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the doctor report as JSON",
    )
    args = parse_command_args(parser, argv)

    report = build_doctor_report()
    configured_home = os.environ.get("ENVMGR_HOME")
    ok_count, warn_count, fail_count = summarize_doctor_report(report)

    if args.json_output:
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
            raise SystemExit(1)
        return

    overall_status = get_doctor_overall_status(report)
    summary = f"Summary: {ok_count} ok, {warn_count} warn, {fail_count} fail"
    print(f"Envmgr Doctor [{render_doctor_status_text(overall_status)}]")
    print(summary)
    print()
    print_doctor_overview(report, configured_home)
    print()
    print(render_doctor_checks_table(report.checks))

    if fail_count:
        raise SystemExit(1)
