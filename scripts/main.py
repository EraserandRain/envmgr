import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn
from uuid import uuid4

import yaml

from .catalog import (
    CatalogError,
    RoleMetadata,
    build_playbook_tag_index,
    get_available_tags,
    load_playbook_tags,
    load_role_catalog,
)
from .command_text import CLI_ROOT_COMMAND, SETUP_HINT
from .runtime_config import (
    ConfigError,
    RuntimeConfig,
    RuntimePaths,
    ensure_runtime_layout,
    get_runtime_paths,
    get_runtime_setup_status,
    is_runtime_setup_complete,
    load_runtime_config,
    mark_runtime_setup_complete,
    resolve_inventory_reference,
)
from .scaffold import ScaffoldError, generate_role


# ANSI color codes
class Colors:
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    RESET = "\033[0m"


DEFAULT_PLAYBOOKS = [
    "playbooks/workstation.yml",
    "playbooks/node.yml",
]
PYTHON_CHECK_PATHS = ["scripts/", "tests/"]
ALL_TAG = "all"
AI_TOOLS_CONTEXT7_METHODS = ("remote", "local")
DOCTOR_COMMANDS = ("uv", "ansible", "ansible-playbook", "ansible-galaxy")
RUNTIME_RUN_RECORD_SCHEMA_VERSION = 1
CommandHandler = Callable[[list[str] | None], None]


@dataclass(frozen=True)
class AiToolsInstallOptions:
    manage_claude_code: bool
    manage_codex: bool
    manage_rtk: bool
    enable_context7: bool
    claude_context7_method: str
    codex_context7_method: str


class WizardCancelled(RuntimeError):
    """Raised when the interactive setup wizard is cancelled by the user."""


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    paths: RuntimePaths
    default_inventory: str | None
    default_playbook_path: str | None
    checks: list[DoctorCheck]


@dataclass(frozen=True)
class RuntimeRunRecord:
    path: Path
    command: tuple[str, ...]
    cwd: str
    mode: str
    started_at: datetime


@dataclass
class RuntimePopenProcess:
    process: subprocess.Popen[Any]
    record: RuntimeRunRecord
    runtime_paths: RuntimePaths
    _finalized: bool = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.process, name)

    def _finalize(self, return_code: int) -> None:
        if self._finalized:
            return

        finish_runtime_run_record(
            self.record,
            runtime_paths=self.runtime_paths,
            status="succeeded" if return_code == 0 else "failed",
            return_code=return_code,
            pid=self.process.pid,
        )
        self._finalized = True

    def poll(self) -> int | None:
        return_code = self.process.poll()
        if return_code is not None:
            self._finalize(return_code)
        return return_code

    def wait(self, timeout: float | None = None) -> int:
        return_code = self.process.wait(timeout=timeout)
        self._finalize(return_code)
        return return_code

    def communicate(
        self,
        input: str | bytes | None = None,
        timeout: float | None = None,
    ) -> tuple[Any, Any]:
        output = self.process.communicate(input=input, timeout=timeout)
        return_code = self.process.returncode
        if return_code is not None:
            self._finalize(return_code)
        return output


DOCTOR_OK = "ok"
DOCTOR_WARN = "warn"
DOCTOR_FAIL = "fail"
REQUIRED_RUNTIME_DIRECTORIES = (
    "inventory_dir",
    "group_vars_all_dir",
    "log_dir",
    "runs_log_dir",
    "cache_dir",
    "galaxy_roles_dir",
    "galaxy_collections_dir",
    "tmp_dir",
)


def run_command_step(
    step_name: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    runtime_paths: RuntimePaths | None = None,
) -> bool:
    """Run one validation step and report its outcome."""
    print(f"\n[{step_name}] {' '.join(command)}")
    try:
        if runtime_paths is not None:
            run_runtime_subprocess(
                command,
                check=True,
                runtime_paths=runtime_paths,
                extra_env=env,
            )
        else:
            subprocess.run(command, check=True, env=env)
        print(f"✓ {step_name} passed")
        return True
    except subprocess.CalledProcessError as error:
        print(f"✗ {step_name} failed with exit code {error.returncode}")
        return False
    except FileNotFoundError:
        print(f"✗ {step_name} failed because '{command[0]}' was not found in PATH")
        return False


def run_assertion_step(step_name: str, check: Callable[[], None]) -> bool:
    """Run one Python-level smoke-test assertion and report its outcome."""
    print(f"\n[{step_name}]")
    try:
        check()
        print(f"✓ {step_name} passed")
        return True
    except (
        AssertionError,
        CatalogError,
        ConfigError,
        FileNotFoundError,
        ScaffoldError,
    ) as error:
        print(f"✗ {step_name} failed: {error}")
        return False


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
    """Load role-level and task-level tags from role metadata."""
    try:
        return get_available_tags("roles")
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


def load_runtime_config_option() -> RuntimeConfig:
    """Load ~/.envmgr/config.toml and surface a user-friendly configuration error."""
    try:
        return load_runtime_config()
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


def resolve_default_playbook_path(config: RuntimeConfig) -> str:
    """Resolve the configured default playbook name into a repository playbook path."""
    configured_playbook = Path(config.default_playbook)
    if configured_playbook.suffix in {".yml", ".yaml"}:
        return str(configured_playbook)
    return str(Path("playbooks") / f"{config.default_playbook}.yml")


def normalize_selected_tags(raw_tags: list[str]) -> list[str]:
    """Normalize install tags and reject ambiguous uses of the special `all` tag."""
    selected_tags = list(
        dict.fromkeys(tag.strip().lower() for tag in raw_tags if tag.strip())
    )
    if ALL_TAG in selected_tags and selected_tags != [ALL_TAG]:
        raise CatalogError(
            "tag 'all' cannot be combined with other tags; choose either 'all' or specific tags"
        )
    return selected_tags


def is_all_tag_selection(selected_tags: list[str]) -> bool:
    """Return whether the normalized selection targets the entire playbook."""
    return selected_tags == [ALL_TAG]


def merge_path_entries(entries: list[str]) -> str:
    """Merge search-path entries while preserving order and removing duplicates."""
    unique_entries: list[str] = []
    seen_entries: set[str] = set()
    for entry in entries:
        if not entry or entry in seen_entries:
            continue
        seen_entries.add(entry)
        unique_entries.append(entry)
    return os.pathsep.join(unique_entries)


def build_ansible_runtime_env(paths: RuntimePaths) -> dict[str, str]:
    """Build a consistent Ansible runtime environment rooted in ~/.envmgr."""
    env = os.environ.copy()
    env["ANSIBLE_FORCE_COLOR"] = "true"
    env["ANSIBLE_LOG_PATH"] = str(paths.ansible_log_file)
    env["ANSIBLE_ROLES_PATH"] = merge_path_entries(
        [
            str(Path("roles").resolve()),
            str(paths.galaxy_roles_dir),
        ]
    )
    env["ANSIBLE_COLLECTIONS_PATH"] = merge_path_entries(
        [
            str(paths.galaxy_collections_dir),
        ]
    )
    env["ANSIBLE_LOCAL_TEMP"] = str(paths.tmp_dir)
    return env


def get_current_utc_time() -> datetime:
    """Return the current UTC timestamp for runtime logs."""
    return datetime.now(timezone.utc)


def format_runtime_timestamp(timestamp: datetime) -> str:
    """Render runtime timestamps in RFC 3339 format with timezone suffix."""
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def get_runtime_command_name(command: list[str]) -> str:
    """Return a readable command name for a subprocess invocation."""
    if not command:
        return "command"
    return Path(command[0]).name or "command"


def sanitize_runtime_record_slug(value: str) -> str:
    """Convert a command name into a filesystem-friendly slug."""
    characters = [
        character.lower() if character.isalnum() else "-" for character in value.strip()
    ]
    slug = "".join(characters).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "command"


def resolve_runtime_subprocess_cwd(cwd: str | os.PathLike[str] | None) -> str:
    """Resolve the working directory used for a subprocess record."""
    if cwd is None:
        return str(Path.cwd().resolve())
    return str(Path(cwd).expanduser().resolve())


def write_runtime_run_record(path: Path, payload: dict[str, Any]) -> None:
    """Persist a runtime subprocess record without interrupting the command flow."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def persist_runtime_run_record(
    record: RuntimeRunRecord,
    *,
    runtime_paths: RuntimePaths,
    status: str,
    pid: int | None = None,
    return_code: int | None = None,
    error: str | None = None,
    completed_at: datetime | None = None,
) -> None:
    """Write the current state of a runtime subprocess record to disk."""
    duration_seconds: float | None = None
    if completed_at is not None:
        duration_seconds = round(
            max((completed_at - record.started_at).total_seconds(), 0.0),
            3,
        )

    payload = {
        "schema_version": RUNTIME_RUN_RECORD_SCHEMA_VERSION,
        "mode": record.mode,
        "command_name": get_runtime_command_name(list(record.command)),
        "command": list(record.command),
        "cwd": record.cwd,
        "runtime_home": str(runtime_paths.home),
        "ansible_log_file": str(runtime_paths.ansible_log_file),
        "status": status,
        "pid": pid,
        "return_code": return_code,
        "started_at": format_runtime_timestamp(record.started_at),
        "completed_at": (
            format_runtime_timestamp(completed_at) if completed_at is not None else None
        ),
        "duration_seconds": duration_seconds,
        "error": error,
    }
    write_runtime_run_record(record.path, payload)


def start_runtime_run_record(
    command: list[str],
    *,
    runtime_paths: RuntimePaths,
    mode: str,
    cwd: str,
) -> RuntimeRunRecord:
    """Create an initial running record for a runtime subprocess."""
    started_at = get_current_utc_time()
    command_name = sanitize_runtime_record_slug(get_runtime_command_name(command))
    timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
    record_path = (
        runtime_paths.runs_log_dir
        / f"{timestamp}-{command_name}-{uuid4().hex[:8]}.json"
    )
    record = RuntimeRunRecord(
        path=record_path,
        command=tuple(command),
        cwd=cwd,
        mode=mode,
        started_at=started_at,
    )
    persist_runtime_run_record(
        record,
        runtime_paths=runtime_paths,
        status="running",
    )
    return record


def finish_runtime_run_record(
    record: RuntimeRunRecord,
    *,
    runtime_paths: RuntimePaths,
    status: str,
    pid: int | None = None,
    return_code: int | None = None,
    error: str | None = None,
) -> None:
    """Finalize a runtime subprocess record with completion metadata."""
    persist_runtime_run_record(
        record,
        runtime_paths=runtime_paths,
        status=status,
        pid=pid,
        return_code=return_code,
        error=error,
        completed_at=get_current_utc_time(),
    )


def run_runtime_subprocess(
    command: list[str],
    *,
    runtime_paths: RuntimePaths,
    extra_env: dict[str, str] | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Run a subprocess with the envmgr Ansible runtime environment."""
    record = start_runtime_run_record(
        command,
        runtime_paths=runtime_paths,
        mode="run",
        cwd=resolve_runtime_subprocess_cwd(kwargs.get("cwd")),
    )
    env = build_ansible_runtime_env(runtime_paths)
    if extra_env is not None:
        env.update(extra_env)
    try:
        result = subprocess.run(command, env=env, **kwargs)
    except subprocess.CalledProcessError as error:
        finish_runtime_run_record(
            record,
            runtime_paths=runtime_paths,
            status="failed",
            return_code=error.returncode,
            error=str(error),
        )
        raise
    except FileNotFoundError as error:
        finish_runtime_run_record(
            record,
            runtime_paths=runtime_paths,
            status="missing-command",
            error=str(error),
        )
        raise
    except OSError as error:
        finish_runtime_run_record(
            record,
            runtime_paths=runtime_paths,
            status="error",
            error=str(error),
        )
        raise

    finish_runtime_run_record(
        record,
        runtime_paths=runtime_paths,
        status="succeeded" if result.returncode == 0 else "failed",
        return_code=result.returncode,
    )
    return result


def popen_runtime_subprocess(
    command: list[str],
    *,
    runtime_paths: RuntimePaths,
    extra_env: dict[str, str] | None = None,
    **kwargs: Any,
) -> RuntimePopenProcess:
    """Start a subprocess with the envmgr Ansible runtime environment."""
    record = start_runtime_run_record(
        command,
        runtime_paths=runtime_paths,
        mode="popen",
        cwd=resolve_runtime_subprocess_cwd(kwargs.get("cwd")),
    )
    env = build_ansible_runtime_env(runtime_paths)
    if extra_env is not None:
        env.update(extra_env)
    try:
        process = subprocess.Popen(command, env=env, **kwargs)
    except FileNotFoundError as error:
        finish_runtime_run_record(
            record,
            runtime_paths=runtime_paths,
            status="missing-command",
            error=str(error),
        )
        raise
    except OSError as error:
        finish_runtime_run_record(
            record,
            runtime_paths=runtime_paths,
            status="error",
            error=str(error),
        )
        raise

    persist_runtime_run_record(
        record,
        runtime_paths=runtime_paths,
        status="running",
        pid=process.pid,
    )
    return RuntimePopenProcess(
        process=process,
        record=record,
        runtime_paths=runtime_paths,
    )


def build_doctor_report(envmgr_home: str | Path | None = None) -> DoctorReport:
    """Collect a read-only health report for the envmgr runtime."""
    paths = get_runtime_paths(envmgr_home)
    checks: list[DoctorCheck] = []
    default_inventory: str | None = None
    default_playbook_path: str | None = None

    def add_check(name: str, status: str, detail: str) -> None:
        checks.append(DoctorCheck(name=name, status=status, detail=detail))

    missing_commands = [
        command_name
        for command_name in DOCTOR_COMMANDS
        if shutil.which(command_name) is None
    ]
    if missing_commands:
        add_check(
            "commands",
            DOCTOR_FAIL,
            "missing: " + ", ".join(missing_commands),
        )
    else:
        add_check(
            "commands",
            DOCTOR_OK,
            ", ".join(DOCTOR_COMMANDS),
        )

    if not paths.home.exists():
        add_check(
            "runtime home",
            DOCTOR_FAIL,
            f"missing: {paths.home}; {SETUP_HINT}",
        )

    missing_runtime_directories = [
        str(getattr(paths, attribute_name))
        for attribute_name in REQUIRED_RUNTIME_DIRECTORIES
        if not getattr(paths, attribute_name).exists()
    ]
    if missing_runtime_directories:
        add_check(
            "runtime directories",
            DOCTOR_FAIL,
            "missing " + ", ".join(missing_runtime_directories),
        )

    if not paths.config_file.exists():
        add_check(
            "runtime config",
            DOCTOR_FAIL,
            f"missing {paths.config_file}; {SETUP_HINT}",
        )
    else:
        try:
            config = load_runtime_config(envmgr_home, ensure_layout=False)
        except ConfigError as error:
            add_check("runtime config", DOCTOR_FAIL, str(error))
        else:
            default_inventory = config.default_inventory
            default_playbook_path = resolve_default_playbook_path(config)
            if not Path(default_playbook_path).exists():
                add_check(
                    "runtime config",
                    DOCTOR_FAIL,
                    "inventory="
                    f"{config.default_inventory} playbook={config.default_playbook} "
                    f"(missing playbook: {default_playbook_path})",
                )

            default_inventory_path = config.inventories.get(config.default_inventory)
            if default_inventory_path is None:
                add_check(
                    "runtime config",
                    DOCTOR_FAIL,
                    f"default inventory alias '{config.default_inventory}' is missing from config",
                )
            elif default_inventory_path.exists():
                add_check(
                    f"inventory alias `{config.default_inventory}`",
                    DOCTOR_OK,
                    str(default_inventory_path),
                )
            else:
                add_check(
                    f"inventory alias `{config.default_inventory}`",
                    DOCTOR_FAIL,
                    f"missing: {default_inventory_path}",
                )

    setup_is_complete, setup_detail = get_runtime_setup_status(paths)
    add_check(
        "setup state",
        DOCTOR_OK if setup_is_complete else DOCTOR_FAIL,
        setup_detail,
    )

    return DoctorReport(
        paths=paths,
        default_inventory=default_inventory,
        default_playbook_path=default_playbook_path,
        checks=checks,
    )


def render_doctor_status_text(status: str) -> str:
    """Render a colored uppercase doctor status label."""
    text = status.upper()
    if status == DOCTOR_OK:
        return f"{Colors.GREEN}{text}{Colors.RESET}"
    if status == DOCTOR_WARN:
        return f"{Colors.YELLOW}{text}{Colors.RESET}"
    return f"{Colors.RED}{text}{Colors.RESET}"


def summarize_doctor_report(report: DoctorReport) -> tuple[int, int, int]:
    """Count ok, warn, and fail checks for a doctor report."""
    ok_count = sum(1 for check in report.checks if check.status == DOCTOR_OK)
    warn_count = sum(1 for check in report.checks if check.status == DOCTOR_WARN)
    fail_count = sum(1 for check in report.checks if check.status == DOCTOR_FAIL)
    return ok_count, warn_count, fail_count


def get_doctor_overall_status(report: DoctorReport) -> str:
    """Return the overall doctor status derived from its checks."""
    _ok_count, warn_count, fail_count = summarize_doctor_report(report)
    if fail_count:
        return DOCTOR_FAIL
    if warn_count:
        return DOCTOR_WARN
    return DOCTOR_OK


def build_doctor_json_payload(
    report: DoctorReport,
    *,
    configured_home: str | None,
) -> dict[str, Any]:
    """Serialize a doctor report into a machine-readable payload."""
    ok_count, warn_count, fail_count = summarize_doctor_report(report)
    resolved_configured_home = None
    if configured_home:
        resolved_configured_home = str(Path(configured_home).expanduser().resolve())

    return {
        "status": get_doctor_overall_status(report),
        "summary": {
            "ok": ok_count,
            "warn": warn_count,
            "fail": fail_count,
            "total": len(report.checks),
        },
        "runtime": {
            "home": str(report.paths.home),
            "configured_home": resolved_configured_home,
            "config_file": str(report.paths.config_file),
        },
        "defaults": {
            "inventory": report.default_inventory,
            "playbook": report.default_playbook_path,
        },
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
            }
            for check in report.checks
        ],
    }


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


def abbreviate_home_in_text(value: str) -> str:
    """Render paths under the current user's home directory with `~`."""
    home = str(Path.home().resolve())
    if value == home:
        return "~"
    return value.replace(f"{home}/", "~/")


def get_doctor_check_detail(check: DoctorCheck) -> str:
    """Return a concise human-readable detail for a doctor check."""
    return abbreviate_home_in_text(check.detail)


def get_doctor_status_cell(status: str, width: int) -> str:
    """Render a padded status cell for doctor tables."""
    plain_status = status.upper().ljust(width)
    if status == DOCTOR_OK:
        return f"{Colors.GREEN}{plain_status}{Colors.RESET}"
    if status == DOCTOR_WARN:
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


def load_runtime_run_history(paths: RuntimePaths) -> list[dict[str, Any]]:
    """Load runtime subprocess records sorted from newest to oldest."""
    if not paths.runs_log_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for record_path in sorted(paths.runs_log_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload["record_path"] = str(record_path)
        records.append(payload)
    return records


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


def print_doctor_overview(report: DoctorReport, configured_home: str | None) -> None:
    """Print the high-level context for a doctor report."""
    runtime_home_value = abbreviate_home_in_text(str(report.paths.home))
    if configured_home:
        runtime_home_value += " (from ENVMGR_HOME)"
    else:
        runtime_home_value += " (default)"

    context_rows: list[tuple[str, str]] = [
        ("Runtime home", runtime_home_value),
    ]
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


def get_existing_default_playbooks() -> list[str]:
    """Return default scenario playbooks that exist in the repository."""
    return [playbook for playbook in DEFAULT_PLAYBOOKS if Path(playbook).exists()]


def resolve_selected_role_metadata(
    selected_tags: list[str],
    roles_dir: str | Path = "roles",
) -> dict[str, RoleMetadata]:
    """Resolve selected tags into a role closure that includes declared dependencies."""
    catalog = [
        metadata for metadata in load_role_catalog(roles_dir) if metadata.enabled
    ]
    metadata_by_name = {metadata.name: metadata for metadata in catalog}
    resolved_metadata: dict[str, RoleMetadata] = {}

    def add_metadata(metadata: RoleMetadata) -> None:
        if metadata.name in resolved_metadata:
            return
        resolved_metadata[metadata.name] = metadata
        for dependency_name in metadata.depends_on:
            dependency = metadata_by_name.get(dependency_name)
            if dependency is None:
                raise CatalogError(
                    f"role '{metadata.name}' depends on unknown role '{dependency_name}'"
                )
            add_metadata(dependency)

    for selected_tag in selected_tags:
        matched_metadata = [
            metadata
            for metadata in catalog
            if selected_tag in metadata.tags or selected_tag in metadata.task_tags
        ]
        if not matched_metadata:
            raise CatalogError(
                f"selected tag '{selected_tag}' does not map to a catalog role"
            )

        for metadata in matched_metadata:
            add_metadata(metadata)

    return resolved_metadata


def read_playbook_role_name(role_entry: Any, playbook_path: Path) -> str:
    """Read a role name from a playbook role entry."""
    if isinstance(role_entry, str):
        return role_entry

    if isinstance(role_entry, dict):
        role_name = role_entry.get("role")
        if isinstance(role_name, str) and role_name.strip():
            return role_name

    raise CatalogError(f"{playbook_path} contains an invalid role entry")


def read_playbook_role_tags(
    role_entry: dict[str, Any], playbook_path: Path
) -> list[str]:
    """Normalize a playbook role tag list."""
    value = role_entry.get("tags")
    role_name = role_entry.get("role", "<unknown>")
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise CatalogError(
        f"{playbook_path} role '{role_name}' field 'tags' must be a string or list of strings"
    )


def playbook_includes_role(source_playbook: str, role_name: str) -> bool:
    """Return whether the playbook references a specific role."""
    playbook_path = Path(source_playbook)
    with playbook_path.open(encoding="utf-8") as file:
        playbook_data = yaml.safe_load(file)

    if not isinstance(playbook_data, list):
        raise CatalogError(f"{playbook_path} must contain a YAML list of plays")

    for play in playbook_data:
        if not isinstance(play, dict):
            raise CatalogError(f"{playbook_path} contains an invalid play definition")

        roles = play.get("roles", [])
        if roles is None:
            continue
        if not isinstance(roles, list):
            raise CatalogError(f"{playbook_path} field 'roles' must be a list")

        for role_entry in roles:
            if read_playbook_role_name(role_entry, playbook_path) == role_name:
                return True

    return False


def prompt_bool(message: str, *, default: bool) -> bool:
    """Prompt for a yes/no decision and return the selected value."""
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            response = input(f"{message} [{hint}]: ").strip().lower()
        except EOFError:
            return default
        except KeyboardInterrupt as error:
            print()
            raise SystemExit(130) from error

        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False

        print("Please answer 'y' or 'n'.")


def render_context7_method_label(method: str) -> str:
    """Return a user-facing label for a Context7 connection mode."""
    if method == "remote":
        return "Remote service"
    return "Local MCP process"


def prompt_context7_method(tool_name: str, *, default: str) -> str:
    """Prompt for a user-friendly Context7 connection mode."""
    options = [
        (
            "1",
            "remote",
            "Remote service",
            "Connect to the hosted Context7 MCP endpoint.",
        ),
        (
            "2",
            "local",
            "Local MCP process",
            "Run Context7 locally through `npx` on this machine.",
        ),
    ]
    option_by_token = {token: method for token, method, _label, _description in options}
    option_by_token.update(
        {method: method for _token, method, _label, _description in options}
    )
    default_token = next(
        token for token, method, _label, _description in options if method == default
    )

    print(f"\n{tool_name} Context7 connection:")
    for token, method, label, description in options:
        suffix = " (Recommended)" if method == default else ""
        print(f"  {token}) {label}{suffix}")
        print(f"     {description}")

    while True:
        try:
            response = input(f"Choose 1 or 2 [{default_token}]: ").strip().lower()
        except EOFError:
            return default
        except KeyboardInterrupt as error:
            print()
            raise SystemExit(130) from error

        if not response:
            return default

        selected = option_by_token.get(response)
        if selected is not None:
            return selected

        print("Please choose 1/2, or type 'remote'/'local'.")


def build_ai_tools_setup_summary(
    options: AiToolsInstallOptions,
    *,
    context7_api_key_present: bool,
) -> list[str]:
    """Build a short setup summary for the interactive AI tools wizard."""
    context7_applicable = options.manage_claude_code or options.manage_codex
    lines = [
        "",
        "AI Tools Setup Summary",
        f"- Claude Code: {'enabled' if options.manage_claude_code else 'disabled'}",
        f"- Codex CLI: {'enabled' if options.manage_codex else 'disabled'}",
        f"- RTK: {'enabled' if options.manage_rtk else 'disabled'}",
    ]
    if context7_applicable:
        lines.append(
            f"- Context7: {'enabled' if options.enable_context7 else 'disabled'}"
        )
    if options.enable_context7 and context7_applicable:
        if options.manage_claude_code:
            lines.append(
                "- Claude Code Context7: "
                f"{render_context7_method_label(options.claude_context7_method)}"
            )
        if options.manage_codex:
            lines.append(
                "- Codex CLI Context7: "
                f"{render_context7_method_label(options.codex_context7_method)}"
            )
        if not context7_api_key_present:
            lines.append("- Context7 API key: not set; envmgr will continue without it")
    return lines


def run_ai_tools_setup_wizard(
    *,
    default_manage_claude_code: bool,
    default_manage_codex: bool,
    default_manage_rtk: bool,
    manage_claude_code: bool | None,
    manage_codex: bool | None,
    manage_rtk: bool | None,
    enable_context7: bool | None,
    claude_context7_method: str | None,
    codex_context7_method: str | None,
    context7_api_key_present: bool,
) -> AiToolsInstallOptions:
    """Run the interactive AI tools setup wizard and return the selected options."""
    print("\nAI Tools Setup")
    print("We'll help you choose which AI tools to install on this machine.")
    print("Press Ctrl+C at any time to cancel.")

    while True:
        resolved_manage_claude_code = (
            default_manage_claude_code
            if manage_claude_code is None
            else manage_claude_code
        )
        resolved_manage_codex = (
            default_manage_codex if manage_codex is None else manage_codex
        )
        resolved_manage_rtk = default_manage_rtk if manage_rtk is None else manage_rtk

        if manage_claude_code is None:
            resolved_manage_claude_code = prompt_bool(
                "Install Claude Code?",
                default=default_manage_claude_code,
            )
        if manage_codex is None:
            resolved_manage_codex = prompt_bool(
                "Install Codex CLI?",
                default=default_manage_codex,
            )
        if manage_rtk is None:
            resolved_manage_rtk = prompt_bool(
                "Install RTK?",
                default=default_manage_rtk,
            )

        if resolved_manage_claude_code or resolved_manage_codex or resolved_manage_rtk:
            break

        if (
            manage_claude_code is not None
            or manage_codex is not None
            or manage_rtk is not None
        ):
            raise CatalogError(
                "AI tools selection disabled Claude Code, Codex CLI, and RTK; choose at least one tool"
            )

        print("Select at least one tool to continue.")

    context7_applicable = resolved_manage_claude_code or resolved_manage_codex
    resolved_enable_context7 = False
    if context7_applicable:
        resolved_enable_context7 = True if enable_context7 is None else enable_context7
    if context7_applicable and enable_context7 is None:
        resolved_enable_context7 = prompt_bool(
            "Enable optional Context7 integration?",
            default=True,
        )

    resolved_claude_context7_method = (
        "remote" if claude_context7_method is None else claude_context7_method
    )
    resolved_codex_context7_method = (
        "remote" if codex_context7_method is None else codex_context7_method
    )

    if resolved_enable_context7:
        if resolved_manage_claude_code and claude_context7_method is None:
            resolved_claude_context7_method = prompt_context7_method(
                "Claude Code",
                default="remote",
            )
        if resolved_manage_codex and codex_context7_method is None:
            resolved_codex_context7_method = prompt_context7_method(
                "Codex CLI",
                default="remote",
            )

    options = AiToolsInstallOptions(
        manage_claude_code=resolved_manage_claude_code,
        manage_codex=resolved_manage_codex,
        manage_rtk=resolved_manage_rtk,
        enable_context7=resolved_enable_context7,
        claude_context7_method=resolved_claude_context7_method,
        codex_context7_method=resolved_codex_context7_method,
    )

    for line in build_ai_tools_setup_summary(
        options,
        context7_api_key_present=context7_api_key_present,
    ):
        print(line)

    if not prompt_bool("Install with these settings?", default=True):
        raise WizardCancelled("AI Tools Setup cancelled before installation.")

    return options


def resolve_ai_tools_install_options(
    selected_tags: list[str],
    *,
    execution_playbook_path: str,
    manage_claude_code: bool | None,
    manage_codex: bool | None,
    manage_rtk: bool | None,
    enable_context7: bool | None,
    claude_context7_method: str | None,
    codex_context7_method: str | None,
    interactive: bool,
) -> AiToolsInstallOptions | None:
    """Resolve AI-tools install choices from tags, flags, and interactive prompts."""
    if not playbook_includes_role(execution_playbook_path, "ai_tools"):
        return None

    requested_tags = {tag.lower() for tag in selected_tags}
    default_manage_claude_code = any(
        tag in requested_tags for tag in ("all", "ai_tools", "claude_code")
    )
    default_manage_codex = any(tag in requested_tags for tag in ("all", "codex"))
    default_manage_rtk = any(
        tag in requested_tags for tag in ("all", "ai_tools", "rtk")
    )

    if interactive:
        return run_ai_tools_setup_wizard(
            default_manage_claude_code=default_manage_claude_code,
            default_manage_codex=default_manage_codex,
            default_manage_rtk=default_manage_rtk,
            manage_claude_code=manage_claude_code,
            manage_codex=manage_codex,
            manage_rtk=manage_rtk,
            enable_context7=enable_context7,
            claude_context7_method=claude_context7_method,
            codex_context7_method=codex_context7_method,
            context7_api_key_present=bool(os.environ.get("CONTEXT7_API_KEY")),
        )

    resolved_manage_claude_code = (
        default_manage_claude_code if manage_claude_code is None else manage_claude_code
    )
    resolved_manage_codex = (
        default_manage_codex if manage_codex is None else manage_codex
    )
    resolved_manage_rtk = default_manage_rtk if manage_rtk is None else manage_rtk

    if not (
        resolved_manage_claude_code or resolved_manage_codex or resolved_manage_rtk
    ):
        raise CatalogError(
            "AI tools selection disabled Claude Code, Codex CLI, and RTK; choose at least one tool"
        )

    context7_applicable = resolved_manage_claude_code or resolved_manage_codex
    resolved_enable_context7 = False
    if context7_applicable:
        resolved_enable_context7 = True if enable_context7 is None else enable_context7
    resolved_claude_context7_method = (
        "remote" if claude_context7_method is None else claude_context7_method
    )
    resolved_codex_context7_method = (
        "remote" if codex_context7_method is None else codex_context7_method
    )

    return AiToolsInstallOptions(
        manage_claude_code=resolved_manage_claude_code,
        manage_codex=resolved_manage_codex,
        manage_rtk=resolved_manage_rtk,
        enable_context7=resolved_enable_context7,
        claude_context7_method=resolved_claude_context7_method,
        codex_context7_method=resolved_codex_context7_method,
    )


def build_ai_tools_extra_vars(options: AiToolsInstallOptions) -> dict[str, Any]:
    """Build Ansible extra vars for AI-tools install-time choices."""
    return {
        "ai_tools_manage_claude_code_override": options.manage_claude_code,
        "ai_tools_manage_codex_override": options.manage_codex,
        "ai_tools_manage_rtk_override": options.manage_rtk,
        "ai_tools_context7_enabled": options.enable_context7,
        "ai_tools_claude_context7_method": options.claude_context7_method,
        "ai_tools_codex_context7_method": options.codex_context7_method,
    }


def build_execution_playbook(
    source_playbook: str,
    selected_tags: list[str],
    roles_dir: str | Path = "roles",
) -> str:
    """Build a minimal temporary playbook for the selected tags."""
    playbook_path = Path(source_playbook)
    if not playbook_path.exists():
        raise CatalogError(f"playbook not found: {playbook_path}")

    selected_metadata = resolve_selected_role_metadata(selected_tags, roles_dir)
    selected_tag_set = set(selected_tags)
    required_playbook_roles: dict[str, str] = {}
    roles_requiring_selected_tags: set[str] = set()

    for metadata in selected_metadata.values():
        for playbook_role in metadata.playbook_roles:
            required_playbook_roles[playbook_role] = metadata.name
        if set(metadata.tags).isdisjoint(selected_tag_set):
            roles_requiring_selected_tags.add(metadata.name)

    with playbook_path.open(encoding="utf-8") as file:
        playbook_data = yaml.safe_load(file)

    if not isinstance(playbook_data, list):
        raise CatalogError(f"{playbook_path} must contain a YAML list of plays")

    generated_playbook: list[dict[str, Any]] = []
    selected_tag_list = list(dict.fromkeys(selected_tags))

    for play in playbook_data:
        if not isinstance(play, dict):
            raise CatalogError(f"{playbook_path} contains an invalid play definition")

        roles = play.get("roles", [])
        if roles is None:
            filtered_roles: list[Any] = []
        else:
            if not isinstance(roles, list):
                raise CatalogError(f"{playbook_path} field 'roles' must be a list")

            filtered_roles = []
            for role_entry in roles:
                role_name = read_playbook_role_name(role_entry, playbook_path)
                metadata_name = required_playbook_roles.get(role_name)
                if metadata_name is None:
                    continue

                if isinstance(role_entry, dict):
                    filtered_role_entry: Any = deepcopy(role_entry)
                else:
                    filtered_role_entry = role_entry

                if metadata_name in roles_requiring_selected_tags:
                    if isinstance(filtered_role_entry, str):
                        filtered_role_entry = {
                            "role": filtered_role_entry,
                            "tags": selected_tag_list,
                        }
                    else:
                        existing_tags = read_playbook_role_tags(
                            filtered_role_entry, playbook_path
                        )
                        merged_tags = list(
                            dict.fromkeys(existing_tags + selected_tag_list)
                        )
                        filtered_role_entry["tags"] = merged_tags

                filtered_roles.append(filtered_role_entry)

        filtered_play = deepcopy(play)
        filtered_play["roles"] = filtered_roles
        generated_playbook.append(filtered_play)

    if not any(play.get("roles") for play in generated_playbook):
        raise CatalogError("selected tags did not resolve to any playbook roles")

    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yml",
        prefix=f".envmgr-{playbook_path.stem}-",
        dir=playbook_path.parent,
        delete=False,
    )
    try:
        with temp_file:
            yaml.safe_dump(generated_playbook, temp_file, sort_keys=False)
    except Exception:
        Path(temp_file.name).unlink(missing_ok=True)
        raise

    return temp_file.name


def resolve_install_playbook(
    selected_tags: list[str],
    *,
    explicit_playbook: str | None,
) -> str:
    """Resolve a playbook for install operations based on explicit input or tag scope."""
    if explicit_playbook:
        if selected_tags and not is_all_tag_selection(selected_tags):
            playbook_tags = load_playbook_tags(explicit_playbook)
            requested_tags = set(selected_tags)
            if not requested_tags.issubset(playbook_tags):
                raise CatalogError(
                    f"selected tags are not valid in {explicit_playbook}; "
                    "choose a matching playbook"
                )
        return explicit_playbook

    if not selected_tags:
        raise CatalogError("no tags selected")

    if is_all_tag_selection(selected_tags):
        raise CatalogError("tag 'all' requires --playbook so the scenario is explicit")

    playbook_paths = get_existing_default_playbooks()
    if not playbook_paths:
        raise CatalogError("no scenario playbooks found under playbooks/")

    playbook_tag_index = build_playbook_tag_index(playbook_paths)
    requested_tags = set(selected_tags)
    matching_playbooks = [
        playbook
        for playbook, playbook_tags in playbook_tag_index.items()
        if requested_tags.issubset(playbook_tags)
    ]

    if len(matching_playbooks) == 1:
        return matching_playbooks[0]

    if not matching_playbooks:
        raise CatalogError(
            "selected tags do not map to a scenario playbook; use --playbook explicitly"
        )

    matching_names = ", ".join(matching_playbooks)
    raise CatalogError(
        f"selected tags are valid in multiple playbooks ({matching_names}); use --playbook explicitly"
    )


def install(argv: list[str] | None = None) -> None:
    """
    Install and configure the envmgr project using Ansible.
    """
    parser = build_command_parser(
        "install", description="Install and Configure envmgr with ansible"
    )

    # Define the positional argument for tags
    parser.add_argument(
        "tags",
        nargs="*",
        help="List of tags: tag1 tag2 ...",
    )

    # Add an optional argument to list tags
    parser.add_argument(
        "-l", "--list-tags", action="store_true", help="List all available tags"
    )
    parser.add_argument(
        "--playbook",
        help="Specify a playbook file explicitly when tags are ambiguous",
    )

    # Add inventory option
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )

    # Add vault password option
    parser.add_argument(
        "--ask-vault-pass", action="store_true", help="Ask for vault password"
    )
    parser.add_argument(
        "--claude-code",
        dest="ai_tools_manage_claude_code",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, explicitly install Claude Code",
    )
    parser.add_argument(
        "--no-claude-code",
        dest="ai_tools_manage_claude_code",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip Claude Code",
    )
    parser.add_argument(
        "--codex",
        dest="ai_tools_manage_codex",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, explicitly install Codex CLI",
    )
    parser.add_argument(
        "--no-codex",
        dest="ai_tools_manage_codex",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip Codex CLI",
    )
    parser.add_argument(
        "--rtk",
        dest="ai_tools_manage_rtk",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, explicitly install RTK",
    )
    parser.add_argument(
        "--no-rtk",
        dest="ai_tools_manage_rtk",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip RTK",
    )
    parser.add_argument(
        "--context7",
        dest="ai_tools_context7",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, enable Context7 integration",
    )
    parser.add_argument(
        "--no-context7",
        dest="ai_tools_context7",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip Context7 integration",
    )
    parser.add_argument(
        "--claude-context7-method",
        choices=AI_TOOLS_CONTEXT7_METHODS,
        help="Choose the Context7 transport for Claude Code",
    )
    parser.add_argument(
        "--codex-context7-method",
        choices=AI_TOOLS_CONTEXT7_METHODS,
        help="Choose the Context7 transport for Codex CLI",
    )

    args = parse_command_args(parser, argv)

    if args.list_tags:
        role_tags, task_tags = load_available_tags()
        print("Envmgr available tags:")
        print("\nRole level tags:")
        for tag in role_tags:
            print(f"  - {tag}")
        print("\nTask level tags:")
        for tag in task_tags:
            print(f"  - {tag}")
        return

    if not args.tags:
        parser.print_help()
        return

    try:
        selected_tags = normalize_selected_tags(list(args.tags))
    except CatalogError as error:
        exit_with_error(f"Error: {error}")

    if not selected_tags:
        exit_with_error("Error: no tags selected for execution")

    role_tags, task_tags = load_available_tags()

    selected_tag_set: set[str] = set(selected_tags)

    # Check if tags exist
    all_tags: set[str] = set(role_tags + task_tags)
    invalid_tags = selected_tag_set - {ALL_TAG} - all_tags
    if invalid_tags:
        exit_with_error(
            "Error: unknown tags: "
            + ", ".join(sorted(invalid_tags))
            + "\nUse -l or --list-tags to see all available tags"
        )

    require_setup_completed("install")

    runtime_paths = ensure_runtime_layout()
    runtime_config: RuntimeConfig | None = None

    def require_runtime_config() -> RuntimeConfig:
        nonlocal runtime_config
        if runtime_config is None:
            runtime_config = load_runtime_config_option()
        return runtime_config

    def load_default_ask_vault_pass() -> bool:
        if runtime_config is not None:
            return runtime_config.default_ask_vault_pass
        try:
            return load_runtime_config().default_ask_vault_pass
        except ConfigError:
            return False

    try:
        yaml_file_path = resolve_install_playbook(
            selected_tags,
            explicit_playbook=(
                args.playbook
                or (
                    resolve_default_playbook_path(require_runtime_config())
                    if is_all_tag_selection(selected_tags)
                    else None
                )
            ),
        )
    except CatalogError as error:
        exit_with_error(f"Error: {error}")

    if not Path(yaml_file_path).exists():
        exit_with_error(f"Error: playbook not found: {yaml_file_path}")

    inventory_path, inventory_label = resolve_inventory_option(args.inventory)
    execution_playbook_path = yaml_file_path
    if not is_all_tag_selection(selected_tags):
        try:
            execution_playbook_path = build_execution_playbook(
                yaml_file_path,
                selected_tags,
            )
        except CatalogError as error:
            exit_with_error(f"Error: {error}")

    interactive_ai_tools = sys.stdin.isatty() and sys.stdout.isatty()
    ai_tools_flags_provided = any(
        value is not None
        for value in (
            args.ai_tools_manage_claude_code,
            args.ai_tools_manage_codex,
            args.ai_tools_manage_rtk,
            args.ai_tools_context7,
            args.claude_context7_method,
            args.codex_context7_method,
        )
    )
    use_ai_tools_wizard = interactive_ai_tools and not ai_tools_flags_provided
    try:
        ai_tools_options = resolve_ai_tools_install_options(
            selected_tags,
            execution_playbook_path=execution_playbook_path,
            manage_claude_code=args.ai_tools_manage_claude_code,
            manage_codex=args.ai_tools_manage_codex,
            manage_rtk=args.ai_tools_manage_rtk,
            enable_context7=args.ai_tools_context7,
            claude_context7_method=args.claude_context7_method,
            codex_context7_method=args.codex_context7_method,
            interactive=use_ai_tools_wizard,
        )
    except WizardCancelled as error:
        print(error)
        if execution_playbook_path != yaml_file_path:
            Path(execution_playbook_path).unlink(missing_ok=True)
        return
    except CatalogError as error:
        if execution_playbook_path != yaml_file_path:
            Path(execution_playbook_path).unlink(missing_ok=True)
        exit_with_error(f"Error: {error}")
    if ai_tools_options is None and ai_tools_flags_provided:
        print(
            f"{Colors.RED}Warning: AI-tools flags were ignored because this run does not include the ai_tools role{Colors.RESET}"
        )

    # Display execution info
    print("\nRunning Ansible playbook with:")
    print(f"  Playbook: {yaml_file_path}")
    if execution_playbook_path != yaml_file_path:
        print(f"  Execution playbook: {execution_playbook_path}")
    print(f"  Inventory: {inventory_label} -> {inventory_path}")
    if is_all_tag_selection(selected_tags):
        print(f"{Colors.GREEN}  All tags will be executed{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}  Tags:", end=" ")
        for tag in selected_tags:
            if tag in role_tags:
                print(f"[Role: {tag}]", end=" ")
            elif tag in task_tags:
                print(f"[Task: {tag}]", end=" ")
        print(f"{Colors.RESET}")
    if ai_tools_options is not None:
        print(
            f"  AI tools: Claude Code={ai_tools_options.manage_claude_code}, "
            f"Codex CLI={ai_tools_options.manage_codex}, "
            f"RTK={ai_tools_options.manage_rtk}"
        )
        if ai_tools_options.manage_claude_code or ai_tools_options.manage_codex:
            context7_status = (
                "enabled" if ai_tools_options.enable_context7 else "disabled"
            )
            print(f"  Context7: {context7_status}")
        if ai_tools_options.enable_context7:
            if ai_tools_options.manage_claude_code:
                print(
                    "  Claude Code Context7 method: "
                    f"{ai_tools_options.claude_context7_method}"
                )
            if ai_tools_options.manage_codex:
                print(
                    f"  Codex Context7 method: {ai_tools_options.codex_context7_method}"
                )
            if not os.environ.get("CONTEXT7_API_KEY"):
                print("  Context7 API key: not set (continuing without it)")
    print()

    play: list[str] = [
        "ansible-playbook",
        "-i",
        str(inventory_path),
        execution_playbook_path,
    ]
    if is_all_tag_selection(selected_tags):
        command = play
    else:
        tags_str = ",".join(selected_tags)
        command = play + ["-t", tags_str]

    # Add vault password option if specified
    default_ask_vault_pass = (
        load_default_ask_vault_pass() if not args.ask_vault_pass else False
    )
    if args.ask_vault_pass or default_ask_vault_pass:
        command.append("--ask-vault-pass")

    if ai_tools_options is not None:
        command.extend(
            ["--extra-vars", json.dumps(build_ai_tools_extra_vars(ai_tools_options))]
        )

    # Use Popen for real-time output
    process: RuntimePopenProcess | None = None
    try:
        process = popen_runtime_subprocess(
            command,
            runtime_paths=runtime_paths,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Read and print output line by line
        if process.stdout is not None:
            for line in process.stdout:
                print(line, end="")
            process.stdout.close()
        return_code = process.wait()
        if return_code != 0:
            raise SystemExit(return_code)
    except KeyboardInterrupt as error:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                process.wait()
            except OSError:
                pass
        raise SystemExit(130) from error
    finally:
        if execution_playbook_path != yaml_file_path:
            Path(execution_playbook_path).unlink(missing_ok=True)


def create(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """
    Create a new Ansible role by prompting the user for a role name and generating the role directory.
    """
    parser = build_command_parser(
        "create",
        description="Create a new Ansible role by prompting the user for a role name and generating the role directory.",
        prog_name=prog_name,
    )
    parser.add_argument("role", nargs="?", help="The name of the role to create")

    args = parse_command_args(parser, argv)

    if args.role:
        try:
            generate_role(args.role)
            print(f"Role '{args.role}' generated successfully.")
            print(
                f"Update roles/{args.role}/meta/envmgr.yml and add the role to the appropriate playbook."
            )
        except FileExistsError:
            print(f"Role '{args.role}' already exists.")
        except (FileNotFoundError, ScaffoldError) as error:
            print(f"{Colors.RED}{error}{Colors.RESET}")
    else:
        parser.print_help()


def ping(argv: list[str] | None = None) -> None:
    """
    Test connection to all hosts using ansible ping module.
    """
    parser = build_command_parser(
        "ping", description="Test connection to all hosts using ansible ping module"
    )

    # Add inventory option
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )

    args = parse_command_args(parser, argv)

    require_setup_completed("ping")

    inventory_path, inventory_label = resolve_inventory_option(args.inventory)
    command: list[str] = ["ansible", "-i", str(inventory_path), "-m", "ping", "all"]

    runtime_paths = ensure_runtime_layout()

    print(f"Testing connection with inventory: {inventory_label} -> {inventory_path}")

    try:
        run_runtime_subprocess(command, check=True, runtime_paths=runtime_paths)
    except subprocess.CalledProcessError as e:
        exit_with_error(f"Ping failed with exit code {e.returncode}")
    except FileNotFoundError:
        exit_with_error(
            "Error: ansible command not found. Please ensure ansible is installed."
        )


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

    if warn_count:
        return


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


def setup(argv: list[str] | None = None) -> None:
    """
    Initialize ~/.envmgr and install the Ansible content envmgr needs at runtime.
    """
    parse_command_args(
        build_command_parser(
            "setup",
            "Initialize ~/.envmgr and install the Ansible content envmgr needs at runtime.",
        ),
        argv,
    )

    print("Setting up envmgr runtime...")

    # Step 1: Initialize the user-level envmgr runtime directory
    print("1. Initializing ~/.envmgr...")
    try:
        runtime_paths = ensure_runtime_layout()
        print(f"✓ Runtime config initialized at {runtime_paths.config_file}")
        print(f"  - Ansible log: {runtime_paths.ansible_log_file}")
        print(f"  - Galaxy roles cache: {runtime_paths.galaxy_roles_dir}")
        print(f"  - Galaxy collections cache: {runtime_paths.galaxy_collections_dir}")
    except ConfigError as error:
        exit_with_error(f"✗ Failed to initialize ~/.envmgr: {error}")
    except OSError as error:
        exit_with_error(f"✗ Failed to initialize ~/.envmgr: {error}")

    # Step 2: Install ansible roles and collections
    print("2. Installing ansible roles and collections...")
    try:
        run_runtime_subprocess(
            [
                "ansible-galaxy",
                "role",
                "install",
                "-p",
                str(runtime_paths.galaxy_roles_dir),
                "-r",
                "requirements.yaml",
            ],
            check=True,
            runtime_paths=runtime_paths,
        )
        run_runtime_subprocess(
            [
                "ansible-galaxy",
                "collection",
                "install",
                "-p",
                str(runtime_paths.galaxy_collections_dir),
                "-r",
                "requirements.yaml",
            ],
            check=True,
            runtime_paths=runtime_paths,
        )
        mark_runtime_setup_complete(runtime_paths)
        print("✓ Ansible roles and collections installed successfully")
    except subprocess.CalledProcessError as e:
        exit_with_error(f"✗ Failed to install ansible roles or collections: {e}")
    except FileNotFoundError:
        exit_with_error(
            "✗ Error: ansible-galaxy command not found. Please ensure ansible is installed."
        )

    print("🎉 Setup completed successfully!")


def lint(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """
    Run ruff linting and formatting on Python code.
    """
    parse_command_args(
        build_command_parser(
            "lint",
            "Run ruff linting and formatting on Python code.",
            prog_name=prog_name,
        ),
        argv,
    )

    print("Running Python code linting with ruff...")

    # Run ruff check
    check_command: list[str] = ["ruff", "check", *PYTHON_CHECK_PATHS]
    print("1. Running ruff check...")

    try:
        subprocess.run(check_command, check=True)
        print("✓ Ruff check passed")
    except subprocess.CalledProcessError as e:
        exit_with_error(f"✗ Ruff check failed with exit code {e.returncode}")
    except FileNotFoundError:
        exit_with_error(
            "Error: ruff command not found. Please ensure ruff is installed."
        )

    # Run ruff format check
    format_command: list[str] = ["ruff", "format", "--check", *PYTHON_CHECK_PATHS]
    print("2. Running ruff format check...")

    try:
        subprocess.run(format_command, check=True)
        print("✓ Ruff format check passed")
    except subprocess.CalledProcessError:
        exit_with_error(
            "✗ Code formatting issues found. Run 'ruff format scripts/ tests/' to fix."
        )
    except FileNotFoundError:
        exit_with_error(
            "Error: ruff command not found. Please ensure ruff is installed."
        )

    print("🎉 All Python linting checks passed!")


def ansible_lint(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """
    Run ansible-lint on the roles directory.
    """
    parse_command_args(
        build_command_parser(
            "ansible-check",
            "Run ansible-lint on the roles directory.",
            prog_name=prog_name,
        ),
        argv,
    )

    command: list[str] = ["ansible-lint", "./roles"]

    print("Running Ansible linting...")

    try:
        subprocess.run(command, check=True)
        print("✓ Ansible lint passed")
    except subprocess.CalledProcessError as e:
        exit_with_error(f"✗ Ansible linting failed with exit code {e.returncode}")
    except FileNotFoundError:
        exit_with_error(
            "Error: ansible-lint command not found. Please ensure ansible-lint is installed."
        )


def typecheck(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """
    Run mypy type checking on the Python source directories.
    """
    parse_command_args(
        build_command_parser(
            "typecheck",
            "Run mypy type checking on the Python source directories.",
            prog_name=prog_name,
        ),
        argv,
    )

    command: list[str] = ["mypy", *PYTHON_CHECK_PATHS]

    print("Running type checking with mypy...")

    try:
        subprocess.run(command, check=True)
        print("✓ Type checking passed")
    except subprocess.CalledProcessError as e:
        exit_with_error(f"✗ Type checking failed with exit code {e.returncode}")
    except FileNotFoundError:
        exit_with_error(
            "Error: mypy command not found. Please ensure mypy is installed."
        )


def validate(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """
    Run the project validation suite in one command.
    """
    parser = build_command_parser(
        "validate",
        description="Run lint, typecheck, ansible lint, and playbook syntax checks",
        prog_name=prog_name,
    )
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        help="Specify a playbook file to syntax-check (can be used multiple times)",
    )

    args = parse_command_args(parser, argv)

    require_setup_completed("validate")

    playbooks = args.playbook or [
        playbook
        for playbook in ["playbooks/workstation.yml", "playbooks/node.yml"]
        if Path(playbook).exists()
    ]
    inventory_path, _inventory_label = resolve_inventory_option(args.inventory)

    runtime_paths = ensure_runtime_layout()

    print("Running project validation...")

    results = [
        run_command_step("ruff check", ["ruff", "check", *PYTHON_CHECK_PATHS]),
        run_command_step(
            "ruff format",
            ["ruff", "format", "--check", *PYTHON_CHECK_PATHS],
        ),
        run_command_step("mypy", ["mypy", *PYTHON_CHECK_PATHS]),
        run_command_step(
            "ansible-lint",
            ["ansible-lint", "./roles"],
            runtime_paths=runtime_paths,
        ),
    ]

    if not playbooks:
        print("No playbooks selected for syntax checks.")

    for playbook in playbooks:
        if not Path(playbook).exists():
            print(f"✗ syntax-check failed because playbook was not found: {playbook}")
            results.append(False)
            continue
        results.append(
            run_command_step(
                f"syntax-check {playbook}",
                [
                    "ansible-playbook",
                    "-i",
                    str(inventory_path),
                    playbook,
                    "--syntax-check",
                ],
                runtime_paths=runtime_paths,
            )
        )

    if all(results):
        print("\n✓ Validation passed")
        return

    print("\n✗ Validation failed")
    raise SystemExit(1)


def smoke_test(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run lightweight integration checks without installing software."""
    from .smoke_checks import iter_smoke_tests

    parser = build_command_parser(
        "smoke-test",
        description="Run lightweight smoke tests for metadata, scaffolds, and playbooks",
        prog_name=prog_name,
    )
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        help="Specify a playbook file to smoke-check (can be used multiple times)",
    )

    args = parse_command_args(parser, argv)

    require_setup_completed("smoke-test")

    playbooks = args.playbook or [
        playbook
        for playbook in ["playbooks/workstation.yml", "playbooks/node.yml"]
        if Path(playbook).exists()
    ]
    inventory_path, _inventory_label = resolve_inventory_option(args.inventory)

    runtime_paths = ensure_runtime_layout()

    print("Running smoke tests...")

    results = [
        run_assertion_step(step_name, test.debug)
        for step_name, test in iter_smoke_tests()
    ]

    if not playbooks:
        print("No playbooks selected for smoke checks.")

    for playbook in playbooks:
        if not Path(playbook).exists():
            print(f"✗ list-tags failed because playbook was not found: {playbook}")
            results.append(False)
            continue
        results.append(
            run_command_step(
                f"list-tags {playbook}",
                [
                    "ansible-playbook",
                    "-i",
                    str(inventory_path),
                    playbook,
                    "--list-tags",
                ],
                runtime_paths=runtime_paths,
            )
        )

    if all(results):
        print("\n✓ Smoke tests passed")
        return

    print("\n✗ Smoke tests failed")
    raise SystemExit(1)


COMMAND_SUMMARIES: dict[str, str] = {
    "doctor": "Inspect envmgr runtime health.",
    "history": "Show recent runtime subprocess records.",
    "install": "Run Ansible roles and task tags.",
    "ping": "Test inventory connectivity with ansible ping.",
    "setup": "Bootstrap the envmgr runtime under ~/.envmgr.",
}

COMMAND_HANDLERS: dict[str, CommandHandler] = {
    "doctor": doctor,
    "history": history,
    "install": install,
    "ping": ping,
    "setup": setup,
}


def build_dispatcher_parser() -> argparse.ArgumentParser:
    """Create the top-level `envmgr` dispatcher parser."""
    commands_text = "\n".join(
        f"  {command_name:<13} {summary}"
        for command_name, summary in COMMAND_SUMMARIES.items()
    )
    parser = argparse.ArgumentParser(
        prog=CLI_ROOT_COMMAND,
        description="envmgr command dispatcher",
        epilog=(
            "Available commands:\n"
            f"{commands_text}\n\n"
            f"Use `{CLI_ROOT_COMMAND} <command> --help` for command-specific options."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=sorted(COMMAND_HANDLERS),
        help="Subcommand to run",
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Dispatch `envmgr <subcommand>` to the appropriate command handler."""
    parser = build_dispatcher_parser()
    parsed_args = parser.parse_args(argv)

    if parsed_args.command is None:
        parser.print_help()
        return

    COMMAND_HANDLERS[parsed_args.command](parsed_args.args)


def create_entrypoint() -> None:
    """Run the role-scaffolding helper from its dedicated development command."""
    create(sys.argv[1:], prog_name="create")


def lint_entrypoint() -> None:
    """Run the Ruff helper from its dedicated development command."""
    lint(sys.argv[1:], prog_name="lint")


def ansible_lint_entrypoint() -> None:
    """Run the ansible-lint helper from its dedicated development command."""
    ansible_lint(sys.argv[1:], prog_name="ansible-check")


def typecheck_entrypoint() -> None:
    """Run the mypy helper from its dedicated development command."""
    typecheck(sys.argv[1:], prog_name="typecheck")


def validate_entrypoint() -> None:
    """Run the full validation helper from its dedicated development command."""
    validate(sys.argv[1:], prog_name="validate")


def smoke_test_entrypoint() -> None:
    """Run the smoke helper from its dedicated development command."""
    smoke_test(sys.argv[1:], prog_name="smoke-test")
