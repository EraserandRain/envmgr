import argparse
import io
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
from typing import Any
from unittest.mock import Mock, patch
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
from .runtime_config import (
    SETUP_SCHEMA_VERSION,
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
AI_TOOLS_CONTEXT7_METHODS = ("remote", "local")
DOCTOR_COMMANDS = ("uv", "ansible", "ansible-playbook", "ansible-galaxy")
RUNTIME_RUN_RECORD_SCHEMA_VERSION = 1


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
        f"runtime at {runtime_paths.home}. Please run `uv run setup` first."
        f"{Colors.RESET}"
    )
    raise SystemExit(1)


def resolve_default_playbook_path(config: RuntimeConfig) -> str:
    """Resolve the configured default playbook name into a repository playbook path."""
    configured_playbook = Path(config.default_playbook)
    if configured_playbook.suffix in {".yml", ".yaml"}:
        return str(configured_playbook)
    return str(Path("playbooks") / f"{config.default_playbook}.yml")


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
            f"missing: {paths.home}; run `uv run setup` first",
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
            f"missing {paths.config_file}; run `uv run setup` first",
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
        if selected_tags and selected_tags[0].lower() != "all":
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

    if selected_tags[0].lower() == "all":
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


def install() -> None:
    """
    Install and configure the envmgr project using Ansible.
    """
    parser = argparse.ArgumentParser(
        description="Install and Configure envmgr with ansible"
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

    args = parser.parse_args()

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

    require_setup_completed("install")

    role_tags, task_tags = load_available_tags()
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

    selected_tags: list[str] = list(args.tags)
    if not selected_tags:
        print(f"{Colors.RED}Warning: No tags selected for execution{Colors.RESET}")
        return

    selected_tag_set: set[str] = set(selected_tags)

    # Check if tags exist
    all_tags: set[str] = set(role_tags + task_tags)
    invalid_tags = selected_tag_set - {"all"} - all_tags
    if invalid_tags:
        print(
            f"{Colors.RED}Warning: Unknown tags: {', '.join(invalid_tags)}{Colors.RESET}"
        )
        print("Use -l or --list-tags to see all available tags")
        return

    try:
        yaml_file_path = resolve_install_playbook(
            selected_tags,
            explicit_playbook=(
                args.playbook
                or (
                    resolve_default_playbook_path(require_runtime_config())
                    if selected_tags[0].lower() == "all"
                    else None
                )
            ),
        )
    except CatalogError as error:
        print(f"{Colors.RED}Warning: {error}{Colors.RESET}")
        return

    if not Path(yaml_file_path).exists():
        print(
            f"{Colors.RED}Warning: Playbook not found: {yaml_file_path}{Colors.RESET}"
        )
        return

    inventory_path, inventory_label = resolve_inventory_option(args.inventory)
    execution_playbook_path = yaml_file_path
    if selected_tags[0].lower() != "all":
        try:
            execution_playbook_path = build_execution_playbook(
                yaml_file_path,
                selected_tags,
            )
        except CatalogError as error:
            print(f"{Colors.RED}Warning: {error}{Colors.RESET}")
            return

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
        print(f"{Colors.RED}Warning: {error}{Colors.RESET}")
        if execution_playbook_path != yaml_file_path:
            Path(execution_playbook_path).unlink(missing_ok=True)
        return
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
    if selected_tags[0].lower() == "all":
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
    if selected_tags[0].lower() == "all":
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
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
    finally:
        if execution_playbook_path != yaml_file_path:
            Path(execution_playbook_path).unlink(missing_ok=True)


def create() -> None:
    """
    Create a new Ansible role by prompting the user for a role name and generating the role directory.
    """
    parser = argparse.ArgumentParser(
        description="Create a new Ansible role by prompting the user for a role name and generating the role directory."
    )
    parser.add_argument("role", nargs="?", help="The name of the role to create")

    args = parser.parse_args()

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


def ping() -> None:
    """
    Test connection to all hosts using ansible ping module.
    """
    parser = argparse.ArgumentParser(
        description="Test connection to all hosts using ansible ping module"
    )

    # Add inventory option
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )

    args = parser.parse_args()

    require_setup_completed("ping")

    inventory_path, inventory_label = resolve_inventory_option(args.inventory)
    command: list[str] = ["ansible", "-i", str(inventory_path), "-m", "ping", "all"]

    runtime_paths = ensure_runtime_layout()

    print(f"Testing connection with inventory: {inventory_label} -> {inventory_path}")

    try:
        run_runtime_subprocess(command, check=True, runtime_paths=runtime_paths)
    except subprocess.CalledProcessError as e:
        print(f"Ping failed with exit code {e.returncode}")
    except FileNotFoundError:
        print("Error: ansible command not found. Please ensure ansible is installed.")


def doctor() -> None:
    """Inspect envmgr runtime health without mutating ~/.envmgr."""
    parser = argparse.ArgumentParser(
        description="Inspect envmgr runtime health without modifying the runtime"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the doctor report as JSON",
    )
    args = parser.parse_args()

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


def history() -> None:
    """Show recent runtime subprocess records from ~/.envmgr/log/runs."""
    parser = argparse.ArgumentParser(
        description="Show recent envmgr runtime subprocess records"
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

    args = parser.parse_args()
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


def setup() -> None:
    """
    Setup the envmgr project by syncing dependencies, initializing ~/.envmgr, and installing ansible content.
    """
    print("Setting up envmgr...")

    # Step 1: Sync dependencies with uv
    print("1. Syncing dependencies with uv...")
    try:
        subprocess.run(["uv", "sync"], check=True)
        print("✓ Dependencies synced successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to sync dependencies: {e}")
        return
    except FileNotFoundError:
        print("✗ Error: uv command not found. Please ensure uv is installed.")
        return

    # Step 2: Initialize the user-level envmgr runtime directory
    print("2. Initializing ~/.envmgr...")
    try:
        runtime_paths = ensure_runtime_layout()
        print(f"✓ Runtime config initialized at {runtime_paths.config_file}")
        print(f"  - Ansible log: {runtime_paths.ansible_log_file}")
        print(f"  - Galaxy roles cache: {runtime_paths.galaxy_roles_dir}")
        print(f"  - Galaxy collections cache: {runtime_paths.galaxy_collections_dir}")
    except ConfigError as error:
        print(f"✗ Failed to initialize ~/.envmgr: {error}")
        return
    except OSError as error:
        print(f"✗ Failed to initialize ~/.envmgr: {error}")
        return

    # Step 3: Install ansible roles and collections
    print("3. Installing ansible roles and collections...")
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
        print(f"✗ Failed to install ansible roles or collections: {e}")
        return
    except FileNotFoundError:
        print(
            "✗ Error: ansible-galaxy command not found. Please ensure ansible is installed."
        )
        return

    print("🎉 Setup completed successfully!")


def lint() -> None:
    """
    Run ruff linting and formatting on Python code.
    """
    print("Running Python code linting with ruff...")

    # Run ruff check
    check_command: list[str] = ["ruff", "check", "scripts/"]
    print("1. Running ruff check...")

    try:
        subprocess.run(check_command, check=True)
        print("✓ Ruff check passed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Ruff check failed with exit code {e.returncode}")
        return
    except FileNotFoundError:
        print("Error: ruff command not found. Please ensure ruff is installed.")
        return

    # Run ruff format check
    format_command: list[str] = ["ruff", "format", "--check", "scripts/"]
    print("2. Running ruff format check...")

    try:
        subprocess.run(format_command, check=True)
        print("✓ Ruff format check passed")
    except subprocess.CalledProcessError:
        print("✗ Code formatting issues found. Run 'ruff format scripts/' to fix.")
        return
    except FileNotFoundError:
        print("Error: ruff command not found. Please ensure ruff is installed.")
        return

    print("🎉 All Python linting checks passed!")


def ansible_lint() -> None:
    """
    Run ansible-lint on the roles directory.
    """
    command: list[str] = ["ansible-lint", "./roles"]

    print("Running Ansible linting...")

    try:
        subprocess.run(command, check=True)
        print("✓ Ansible lint passed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Ansible linting failed with exit code {e.returncode}")
    except FileNotFoundError:
        print(
            "Error: ansible-lint command not found. Please ensure ansible-lint is installed."
        )


def typecheck() -> None:
    """
    Run mypy type checking on the scripts directory.
    """
    command: list[str] = ["mypy", "scripts/"]

    print("Running type checking with mypy...")

    try:
        subprocess.run(command, check=True)
        print("✓ Type checking passed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Type checking failed with exit code {e.returncode}")
    except FileNotFoundError:
        print("Error: mypy command not found. Please ensure mypy is installed.")


def validate() -> None:
    """
    Run the project validation suite in one command.
    """
    parser = argparse.ArgumentParser(
        description="Run lint, typecheck, ansible lint, and playbook syntax checks"
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

    args = parser.parse_args()

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
        run_command_step("ruff check", ["ruff", "check", "scripts/"]),
        run_command_step("ruff format", ["ruff", "format", "--check", "scripts/"]),
        run_command_step("mypy", ["mypy", "scripts/"]),
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


def smoke_test() -> None:
    """Run lightweight integration checks without installing software."""

    def check_metadata_catalog() -> None:
        role_tags, task_tags = get_available_tags("roles")

        if "init" not in role_tags:
            raise AssertionError("expected role tag 'init' to be present")
        if "init_core" in role_tags:
            raise AssertionError("expected init_core to stay hidden from role tags")
        if "git" in task_tags:
            raise AssertionError("expected git task tag to stay hidden")
        if "codex" not in task_tags:
            raise AssertionError("expected task tag 'codex' to be present")
        if "rtk" not in task_tags:
            raise AssertionError("expected task tag 'rtk' to be present")

    def check_scaffold_generation() -> None:
        required_files = [
            Path("README.md"),
            Path("defaults/main.yml"),
            Path("vars/main.yml"),
            Path("meta/main.yml"),
            Path("meta/envmgr.yml"),
            Path("tasks/main.yml"),
            Path("tasks/smoke-role.yml"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            role_path = generate_role(
                "smoke-role",
                roles_dir=temp_path / "roles",
                scaffold_dir="scaffolds/role",
            )

            for relative_path in required_files:
                generated_path = role_path / relative_path
                if not generated_path.exists():
                    raise AssertionError(f"missing scaffold output: {generated_path}")

                content = generated_path.read_text(encoding="utf-8")
                if "{{ role_name }}" in content or "{{ role_title }}" in content:
                    raise AssertionError(
                        f"unrendered template placeholder found in {generated_path}"
                    )

            metadata_contents = (role_path / "meta" / "envmgr.yml").read_text(
                encoding="utf-8"
            )
            if "name: smoke-role" not in metadata_contents:
                raise AssertionError("generated metadata did not render role name")

    def check_playbook_resolution() -> None:
        if resolve_install_playbook(["zsh"], explicit_playbook=None) != (
            "playbooks/workstation.yml"
        ):
            raise AssertionError("expected zsh to resolve to workstation playbook")

        if resolve_install_playbook(["kubeadm"], explicit_playbook=None) != (
            "playbooks/node.yml"
        ):
            raise AssertionError("expected kubeadm to resolve to node playbook")

        try:
            resolve_install_playbook(["docker"], explicit_playbook=None)
        except CatalogError:
            pass
        else:
            raise AssertionError("expected docker to require an explicit playbook")

        if (
            resolve_install_playbook(
                ["init"], explicit_playbook="playbooks/workstation.yml"
            )
            != "playbooks/workstation.yml"
        ):
            raise AssertionError("expected init to stay valid on workstation playbook")

        try:
            resolve_install_playbook(["init"], explicit_playbook="playbooks/node.yml")
        except CatalogError:
            return

        raise AssertionError("expected init to be rejected on node playbook")

    def check_execution_playbook_generation() -> None:
        generated_ai_tools_playbook = build_execution_playbook(
            "playbooks/workstation.yml",
            ["ai_tools"],
        )
        generated_codex_playbook = build_execution_playbook(
            "playbooks/workstation.yml",
            ["codex"],
        )
        generated_rtk_playbook = build_execution_playbook(
            "playbooks/workstation.yml",
            ["rtk"],
        )
        generated_init_playbook = build_execution_playbook(
            "playbooks/workstation.yml",
            ["init"],
        )
        generated_monitoring_playbook = build_execution_playbook(
            "playbooks/node.yml",
            ["monitoring"],
        )

        try:
            with Path(generated_ai_tools_playbook).open(encoding="utf-8") as file:
                ai_tools_data = yaml.safe_load(file)
            with Path(generated_codex_playbook).open(encoding="utf-8") as file:
                codex_data = yaml.safe_load(file)
            with Path(generated_rtk_playbook).open(encoding="utf-8") as file:
                rtk_data = yaml.safe_load(file)
            with Path(generated_init_playbook).open(encoding="utf-8") as file:
                init_data = yaml.safe_load(file)
            with Path(generated_monitoring_playbook).open(encoding="utf-8") as file:
                monitoring_data = yaml.safe_load(file)

            if not isinstance(ai_tools_data, list) or not ai_tools_data:
                raise AssertionError(
                    "expected generated ai_tools playbook to contain a play"
                )
            if not isinstance(codex_data, list) or not codex_data:
                raise AssertionError(
                    "expected generated codex playbook to contain a play"
                )
            if not isinstance(rtk_data, list) or not rtk_data:
                raise AssertionError(
                    "expected generated rtk playbook to contain a play"
                )
            if not isinstance(init_data, list) or not init_data:
                raise AssertionError(
                    "expected generated init playbook to contain a play"
                )
            if not isinstance(monitoring_data, list) or len(monitoring_data) != 2:
                raise AssertionError(
                    "expected generated monitoring playbook to preserve both node plays"
                )

            ai_tools_roles = ai_tools_data[0].get("roles", [])
            codex_roles = codex_data[0].get("roles", [])
            rtk_roles = rtk_data[0].get("roles", [])
            init_roles = init_data[0].get("roles", [])
            monitoring_node_roles = monitoring_data[0].get("roles", [])
            monitoring_master_roles = monitoring_data[1].get("roles", [])
            if (
                not isinstance(ai_tools_roles, list)
                or not isinstance(codex_roles, list)
                or not isinstance(rtk_roles, list)
                or not isinstance(init_roles, list)
                or not isinstance(monitoring_node_roles, list)
                or not isinstance(monitoring_master_roles, list)
            ):
                raise AssertionError("expected generated playbook roles to be a list")

            ai_tools_role_names = [
                read_playbook_role_name(role_entry, Path(generated_ai_tools_playbook))
                for role_entry in ai_tools_roles
            ]
            codex_role_names = [
                read_playbook_role_name(role_entry, Path(generated_codex_playbook))
                for role_entry in codex_roles
            ]
            rtk_role_names = [
                read_playbook_role_name(role_entry, Path(generated_rtk_playbook))
                for role_entry in rtk_roles
            ]
            init_role_names = [
                read_playbook_role_name(role_entry, Path(generated_init_playbook))
                for role_entry in init_roles
            ]
            monitoring_master_role_names = [
                read_playbook_role_name(role_entry, Path(generated_monitoring_playbook))
                for role_entry in monitoring_master_roles
            ]

            if ai_tools_role_names != ["init_core", "node", "ai_tools"]:
                raise AssertionError(
                    "expected ai_tools execution roles to be "
                    f"['init_core', 'node', 'ai_tools'], got {ai_tools_role_names}"
                )
            if "gantsign.oh-my-zsh" in ai_tools_role_names:
                raise AssertionError(
                    "expected ai_tools execution playbook to exclude oh-my-zsh"
                )

            if codex_role_names != ["init_core", "node", "ai_tools"]:
                raise AssertionError(
                    "expected codex execution roles to be "
                    f"['init_core', 'node', 'ai_tools'], got {codex_role_names}"
                )
            if rtk_role_names != ["init_core", "node", "ai_tools"]:
                raise AssertionError(
                    "expected rtk execution roles to be "
                    f"['init_core', 'node', 'ai_tools'], got {rtk_role_names}"
                )
            if init_role_names != ["init_core", "init"]:
                raise AssertionError(
                    "expected init execution roles to be "
                    f"['init_core', 'init'], got {init_role_names}"
                )
            if monitoring_node_roles:
                raise AssertionError(
                    "expected monitoring execution playbook to skip the all-node play"
                )
            if monitoring_master_role_names != ["kubernetes_tools", "monitoring"]:
                raise AssertionError(
                    "expected monitoring execution roles to be "
                    f"['kubernetes_tools', 'monitoring'], got {monitoring_master_role_names}"
                )

            init_core_entry = ai_tools_roles[0]
            if not isinstance(init_core_entry, dict):
                raise AssertionError(
                    "expected transitive dependency role entry to include tags"
                )
            if "ai_tools" not in read_playbook_role_tags(
                init_core_entry,
                Path(generated_ai_tools_playbook),
            ):
                raise AssertionError(
                    "expected init_core dependency role to inherit the ai_tools tag"
                )

            node_entry = ai_tools_roles[1]
            if not isinstance(node_entry, dict):
                raise AssertionError("expected dependency role entry to include tags")
            if "ai_tools" not in read_playbook_role_tags(
                node_entry,
                Path(generated_ai_tools_playbook),
            ):
                raise AssertionError(
                    "expected node dependency role to inherit the ai_tools tag"
                )

            codex_ai_tools_entry = codex_roles[2]
            if not isinstance(codex_ai_tools_entry, dict):
                raise AssertionError("expected codex role entry to include tags")
            if "codex" not in read_playbook_role_tags(
                codex_ai_tools_entry,
                Path(generated_codex_playbook),
            ):
                raise AssertionError(
                    "expected ai_tools role to inherit the codex tag for task-level runs"
                )

            rtk_ai_tools_entry = rtk_roles[2]
            if not isinstance(rtk_ai_tools_entry, dict):
                raise AssertionError("expected rtk role entry to include tags")
            if "rtk" not in read_playbook_role_tags(
                rtk_ai_tools_entry,
                Path(generated_rtk_playbook),
            ):
                raise AssertionError(
                    "expected ai_tools role to inherit the rtk tag for task-level runs"
                )
        finally:
            Path(generated_ai_tools_playbook).unlink(missing_ok=True)
            Path(generated_codex_playbook).unlink(missing_ok=True)
            Path(generated_rtk_playbook).unlink(missing_ok=True)
            Path(generated_init_playbook).unlink(missing_ok=True)
            Path(generated_monitoring_playbook).unlink(missing_ok=True)

    def check_runtime_config_bootstrap() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            config = load_runtime_config(envmgr_home)

            if config.default_inventory != "default":
                raise AssertionError("expected default inventory alias to be 'default'")

            if config.default_playbook != "workstation":
                raise AssertionError("expected default playbook to be 'workstation'")

            default_inventory_path = config.inventories.get("default")
            if default_inventory_path is None or not default_inventory_path.exists():
                raise AssertionError("expected bootstrap default inventory to exist")

            if not config.paths.config_file.exists():
                raise AssertionError("expected bootstrap config.toml to exist")

    def check_setup_marker_is_written_after_setup() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")

            if is_runtime_setup_complete(runtime_paths):
                raise AssertionError(
                    "expected setup marker to be absent before setup completes"
                )

            (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
            (runtime_paths.galaxy_collections_dir / "community").mkdir()
            mark_runtime_setup_complete(runtime_paths)

            if not is_runtime_setup_complete(runtime_paths):
                raise AssertionError(
                    "expected setup marker to mark the runtime as bootstrapped"
                )
            marker_contents = runtime_paths.setup_marker_file.read_text(
                encoding="utf-8"
            )
            if f"schema_version = {SETUP_SCHEMA_VERSION}" not in marker_contents:
                raise AssertionError(
                    "expected setup marker to persist the setup schema version"
                )
            if 'completed_at = "' not in marker_contents:
                raise AssertionError(
                    "expected setup marker to persist the completion timestamp"
                )

    def check_unbootstrapped_runtime_surfaces_setup_guidance() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            ensure_runtime_layout(envmgr_home)
            captured_output = io.StringIO()

            with patch("sys.stdout", new=captured_output):
                try:
                    require_setup_completed("ping", envmgr_home=envmgr_home)
                except SystemExit as error:
                    if error.code != 1:
                        raise AssertionError(
                            "expected unbootstrapped runtime to exit with code 1"
                        ) from error
                else:
                    raise AssertionError(
                        "expected unbootstrapped runtime to require uv run setup"
                    )

            if "`uv run setup`" not in captured_output.getvalue():
                raise AssertionError(
                    "expected setup guidance to mention `uv run setup`"
                )

    def check_outdated_setup_stamp_requires_setup() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
            (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
            (runtime_paths.galaxy_collections_dir / "community").mkdir()
            runtime_paths.setup_marker_file.write_text(
                'schema_version = 0\ncompleted_at = "2026-04-15T00:00:00Z"\n',
                encoding="utf-8",
            )

            if is_runtime_setup_complete(runtime_paths):
                raise AssertionError(
                    "expected outdated setup schema versions to require re-running setup"
                )

    def check_ai_tools_install_option_resolution() -> None:
        options = resolve_ai_tools_install_options(
            ["ai_tools"],
            execution_playbook_path="playbooks/workstation.yml",
            manage_claude_code=None,
            manage_codex=True,
            manage_rtk=None,
            enable_context7=False,
            claude_context7_method=None,
            codex_context7_method="remote",
            interactive=False,
        )

        if options is None:
            raise AssertionError("expected workstation AI tools playbook to resolve")
        if not options.manage_claude_code:
            raise AssertionError("expected ai_tools tag to keep Claude Code enabled")
        if not options.manage_codex:
            raise AssertionError("expected explicit Codex selection to be honored")
        if not options.manage_rtk:
            raise AssertionError("expected ai_tools tag to keep RTK enabled")
        if options.enable_context7:
            raise AssertionError("expected explicit Context7 disable to be honored")
        if options.codex_context7_method != "remote":
            raise AssertionError(
                "expected Codex Context7 method override to be honored"
            )

        rtk_only_options = resolve_ai_tools_install_options(
            ["rtk"],
            execution_playbook_path="playbooks/workstation.yml",
            manage_claude_code=None,
            manage_codex=None,
            manage_rtk=None,
            enable_context7=None,
            claude_context7_method=None,
            codex_context7_method=None,
            interactive=False,
        )
        if rtk_only_options is None:
            raise AssertionError("expected rtk task tag to resolve AI tools options")
        if not rtk_only_options.manage_rtk:
            raise AssertionError("expected rtk task tag to enable RTK")
        if rtk_only_options.enable_context7:
            raise AssertionError("expected RTK-only installs to skip Context7")

        node_options = resolve_ai_tools_install_options(
            ["all"],
            execution_playbook_path="playbooks/node.yml",
            manage_claude_code=None,
            manage_codex=None,
            manage_rtk=None,
            enable_context7=None,
            claude_context7_method=None,
            codex_context7_method=None,
            interactive=False,
        )
        if node_options is not None:
            raise AssertionError("expected node playbook to skip AI tools resolution")

    def check_ai_tools_setup_wizard_flow() -> None:
        with patch(
            "builtins.input",
            side_effect=["", "y", "", "", "1", "1", ""],
        ):
            options = resolve_ai_tools_install_options(
                ["ai_tools"],
                execution_playbook_path="playbooks/workstation.yml",
                manage_claude_code=None,
                manage_codex=None,
                manage_rtk=None,
                enable_context7=None,
                claude_context7_method=None,
                codex_context7_method=None,
                interactive=True,
            )

        if options is None:
            raise AssertionError("expected AI tools wizard to return options")
        if not options.manage_claude_code:
            raise AssertionError("expected wizard to keep Claude Code enabled")
        if not options.manage_codex:
            raise AssertionError("expected wizard to allow enabling Codex CLI")
        if not options.manage_rtk:
            raise AssertionError("expected wizard to keep RTK enabled by default")
        if not options.enable_context7:
            raise AssertionError("expected wizard to keep Context7 enabled")
        if options.claude_context7_method != "remote":
            raise AssertionError("expected wizard to select remote for Claude Code")
        if options.codex_context7_method != "remote":
            raise AssertionError("expected wizard to select remote for Codex CLI")

    def check_unknown_inventory_alias_is_rejected() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            ensure_runtime_layout(envmgr_home)

            try:
                resolve_inventory_reference(
                    "inventory/default.yaml",
                    envmgr_home=envmgr_home,
                )
            except ConfigError as error:
                message = str(error)
                if (
                    "inventory alias 'inventory/default.yaml' is not defined"
                    not in message
                ):
                    raise AssertionError(
                        "expected unknown inventory inputs to be rejected as aliases"
                    ) from error
                return

            raise AssertionError(
                "expected unknown inventory aliases to raise ConfigError"
            )

    def check_runtime_env_uses_runtime_paths_only() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
            original_roles_path = os.environ.get("ANSIBLE_ROLES_PATH")
            original_collections_path = os.environ.get("ANSIBLE_COLLECTIONS_PATH")
            os.environ["ANSIBLE_ROLES_PATH"] = str(
                Path(temp_dir) / "legacy-roles" / ".ansible" / "roles"
            )
            os.environ["ANSIBLE_COLLECTIONS_PATH"] = str(
                Path(temp_dir) / "legacy-collections" / ".ansible" / "collections"
            )
            try:
                env = build_ansible_runtime_env(runtime_paths)
            finally:
                if original_roles_path is not None:
                    os.environ["ANSIBLE_ROLES_PATH"] = original_roles_path
                else:
                    os.environ.pop("ANSIBLE_ROLES_PATH", None)
                if original_collections_path is not None:
                    os.environ["ANSIBLE_COLLECTIONS_PATH"] = original_collections_path
                else:
                    os.environ.pop("ANSIBLE_COLLECTIONS_PATH", None)

            if ".ansible/roles" in env["ANSIBLE_ROLES_PATH"]:
                raise AssertionError(
                    "expected runtime roles path to exclude .ansible/roles"
                )
            if ".ansible/collections" in env["ANSIBLE_COLLECTIONS_PATH"]:
                raise AssertionError(
                    "expected runtime collections path to exclude .ansible/collections"
                )
            if env["ANSIBLE_LOG_PATH"] != str(runtime_paths.ansible_log_file):
                raise AssertionError("expected ansible log path to point to ~/.envmgr")

    def check_runtime_subprocess_helpers_use_runtime_paths() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")

            with patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess(
                    ["ansible-playbook", "--version"],
                    0,
                ),
            ) as mock_run:
                run_runtime_subprocess(
                    ["ansible-playbook", "--version"],
                    runtime_paths=runtime_paths,
                    extra_env={"ENVMGR_TEST_FLAG": "run"},
                )

            run_env = mock_run.call_args.kwargs.get("env")
            if not isinstance(run_env, dict):
                raise AssertionError("expected run helper to pass an env mapping")
            if run_env.get("ANSIBLE_LOG_PATH") != str(runtime_paths.ansible_log_file):
                raise AssertionError(
                    "expected run helper to point ansible logs at ~/.envmgr"
                )
            if run_env.get("ENVMGR_TEST_FLAG") != "run":
                raise AssertionError(
                    "expected run helper to merge extra environment variables"
                )
            run_records = sorted(runtime_paths.runs_log_dir.glob("*.json"))
            if len(run_records) != 1:
                raise AssertionError("expected run helper to write one runtime record")
            run_payload = json.loads(run_records[0].read_text(encoding="utf-8"))
            if run_payload["status"] != "succeeded":
                raise AssertionError("expected run helper to mark successful records")
            if run_payload["mode"] != "run":
                raise AssertionError("expected run helper to record mode=run")
            if run_payload["return_code"] != 0:
                raise AssertionError("expected run helper to persist return_code=0")
            if run_payload["ansible_log_file"] != str(runtime_paths.ansible_log_file):
                raise AssertionError(
                    "expected run helper to persist the ansible log path"
                )
            if run_payload["completed_at"] is None:
                raise AssertionError(
                    "expected run helper to persist completion timestamps"
                )

            mock_process = Mock()
            mock_process.pid = 4242
            mock_process.wait.return_value = 0
            mock_process.poll.return_value = None
            mock_process.returncode = 0

            with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
                process = popen_runtime_subprocess(
                    ["ansible-playbook", "--version"],
                    runtime_paths=runtime_paths,
                    extra_env={"ENVMGR_TEST_FLAG": "popen"},
                    stdout=subprocess.PIPE,
                )
                process.wait()

            popen_env = mock_popen.call_args.kwargs.get("env")
            if not isinstance(popen_env, dict):
                raise AssertionError("expected popen helper to pass an env mapping")
            if popen_env.get("ANSIBLE_LOCAL_TEMP") != str(runtime_paths.tmp_dir):
                raise AssertionError(
                    "expected popen helper to point ansible temp files at ~/.envmgr"
                )
            if popen_env.get("ENVMGR_TEST_FLAG") != "popen":
                raise AssertionError(
                    "expected popen helper to merge extra environment variables"
                )
            popen_records = sorted(runtime_paths.runs_log_dir.glob("*.json"))
            if len(popen_records) != 2:
                raise AssertionError(
                    "expected popen helper to append a second runtime record"
                )
            popen_payload = json.loads(popen_records[-1].read_text(encoding="utf-8"))
            if popen_payload["mode"] != "popen":
                raise AssertionError("expected popen helper to record mode=popen")
            if popen_payload["status"] != "succeeded":
                raise AssertionError("expected popen helper to mark successful records")
            if popen_payload["pid"] != 4242:
                raise AssertionError("expected popen helper to persist the child pid")
            if popen_payload["return_code"] != 0:
                raise AssertionError(
                    "expected popen helper to persist the child return code"
                )

    def check_setup_logs_ansible_galaxy_runs() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            captured_output = io.StringIO()

            def fake_run(
                command: list[str],
                *,
                env: dict[str, str] | None = None,
                **_kwargs: Any,
            ) -> subprocess.CompletedProcess[Any]:
                return subprocess.CompletedProcess(command, 0)

            with (
                patch("subprocess.run", side_effect=fake_run),
                patch("sys.stdout", new=captured_output),
                patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            ):
                setup()

            runtime_paths = get_runtime_paths(envmgr_home)
            run_records = sorted(runtime_paths.runs_log_dir.glob("*.json"))
            if len(run_records) != 2:
                raise AssertionError(
                    "expected setup to log the role and collection galaxy installs"
                )

            payloads = [
                json.loads(record.read_text(encoding="utf-8")) for record in run_records
            ]
            commands = [payload["command"][:3] for payload in payloads]
            if ["ansible-galaxy", "role", "install"] not in commands:
                raise AssertionError(
                    "expected setup to log the Galaxy role installation command"
                )
            if ["ansible-galaxy", "collection", "install"] not in commands:
                raise AssertionError(
                    "expected setup to log the Galaxy collection installation command"
                )
            if not runtime_paths.setup_marker_file.exists():
                raise AssertionError(
                    "expected setup to keep writing the runtime setup marker"
                )

    def check_history_text_output() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)

            records = [
                (
                    "20260418T100000000000Z-ansible-11111111.json",
                    {
                        "schema_version": RUNTIME_RUN_RECORD_SCHEMA_VERSION,
                        "mode": "run",
                        "command_name": "ansible",
                        "command": ["ansible", "-m", "ping", "all"],
                        "cwd": str(Path.cwd()),
                        "runtime_home": str(runtime_paths.home),
                        "ansible_log_file": str(runtime_paths.ansible_log_file),
                        "status": "failed",
                        "pid": 1001,
                        "return_code": 2,
                        "started_at": "2026-04-18T10:00:00Z",
                        "completed_at": "2026-04-18T10:00:01Z",
                        "duration_seconds": 1.0,
                        "error": None,
                    },
                ),
                (
                    "20260418T110000000000Z-ansible-playbook-22222222.json",
                    {
                        "schema_version": RUNTIME_RUN_RECORD_SCHEMA_VERSION,
                        "mode": "run",
                        "command_name": "ansible-playbook",
                        "command": [
                            "ansible-playbook",
                            "playbooks/workstation.yml",
                            "--syntax-check",
                        ],
                        "cwd": str(Path.cwd()),
                        "runtime_home": str(runtime_paths.home),
                        "ansible_log_file": str(runtime_paths.ansible_log_file),
                        "status": "succeeded",
                        "pid": 1002,
                        "return_code": 0,
                        "started_at": "2026-04-18T11:00:00Z",
                        "completed_at": "2026-04-18T11:00:02Z",
                        "duration_seconds": 2.0,
                        "error": None,
                    },
                ),
                (
                    "20260418T120000000000Z-ansible-galaxy-33333333.json",
                    {
                        "schema_version": RUNTIME_RUN_RECORD_SCHEMA_VERSION,
                        "mode": "run",
                        "command_name": "ansible-galaxy",
                        "command": ["ansible-galaxy", "role", "install"],
                        "cwd": str(Path.cwd()),
                        "runtime_home": str(runtime_paths.home),
                        "ansible_log_file": str(runtime_paths.ansible_log_file),
                        "status": "running",
                        "pid": 1003,
                        "return_code": None,
                        "started_at": "2026-04-18T12:00:00Z",
                        "completed_at": None,
                        "duration_seconds": None,
                        "error": None,
                    },
                ),
            ]

            for filename, payload in records:
                write_runtime_run_record(runtime_paths.runs_log_dir / filename, payload)

            captured_output = io.StringIO()
            with (
                patch("sys.argv", ["history", "--limit", "2"]),
                patch("sys.stdout", new=captured_output),
                patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            ):
                history()

            output = captured_output.getvalue()
            if "Envmgr History" not in output:
                raise AssertionError("expected history text output to include a title")
            if "Showing 2 of 3 recorded runtime commands" not in output:
                raise AssertionError("expected history text output to honor the limit")
            if (
                "2026-04-18T12:00:00Z" not in output
                or "ansible-galaxy role install" not in output
            ):
                raise AssertionError(
                    "expected history text output to include the newest record"
                )
            if (
                "2026-04-18T11:00:00Z" not in output
                or "ansible-playbook playbooks/workstation.yml --syntax-check"
                not in output
            ):
                raise AssertionError(
                    "expected history text output to include the second-newest record"
                )
            if "2026-04-18T10:00:00Z" in output:
                raise AssertionError(
                    "expected history text output to omit records beyond the limit"
                )

    def check_history_json_output() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)

            write_runtime_run_record(
                runtime_paths.runs_log_dir
                / "20260418T120000000000Z-ansible-44444444.json",
                {
                    "schema_version": RUNTIME_RUN_RECORD_SCHEMA_VERSION,
                    "mode": "run",
                    "command_name": "ansible",
                    "command": ["ansible", "-m", "ping", "all"],
                    "cwd": str(Path.cwd()),
                    "runtime_home": str(runtime_paths.home),
                    "ansible_log_file": str(runtime_paths.ansible_log_file),
                    "status": "succeeded",
                    "pid": 1004,
                    "return_code": 0,
                    "started_at": "2026-04-18T12:00:00Z",
                    "completed_at": "2026-04-18T12:00:01Z",
                    "duration_seconds": 1.0,
                    "error": None,
                },
            )

            captured_output = io.StringIO()
            with (
                patch("sys.argv", ["history", "--json"]),
                patch("sys.stdout", new=captured_output),
                patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            ):
                history()

            payload = json.loads(captured_output.getvalue())
            if payload["count"] != 1 or payload["total"] != 1:
                raise AssertionError("expected history --json to report record counts")
            if payload["runtime"]["home"] != str(runtime_paths.home):
                raise AssertionError(
                    "expected history --json to report the runtime home"
                )
            if payload["records"][0]["command_name"] != "ansible":
                raise AssertionError(
                    "expected history --json to expose stored runtime records"
                )

    def check_inventory_aliases_stay_under_runtime_inventory_dir() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            runtime_paths.config_file.write_text(
                """
[default]
inventory = "default"

[inventory]
default = "../outside/default.yaml"
""".lstrip(),
                encoding="utf-8",
            )

            try:
                load_runtime_config(envmgr_home)
            except ConfigError as error:
                if "must stay under" not in str(error):
                    raise AssertionError(
                        "expected inventory aliases outside ~/.envmgr/inventory to fail"
                    ) from error
                return

            raise AssertionError("expected out-of-tree inventory aliases to fail")

    def check_invalid_toml_surfaces_config_error() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            runtime_paths.config_file.write_text(
                '[default]\ninventory = "default"\ninvalid = [\n',
                encoding="utf-8",
            )

            try:
                load_runtime_config(envmgr_home)
            except ConfigError as error:
                if "contains invalid TOML" not in str(error):
                    raise AssertionError(
                        "expected invalid TOML errors to be wrapped in ConfigError"
                    ) from error
                return

            raise AssertionError("expected invalid TOML to raise ConfigError")

    def check_missing_runtime_inventory_file_is_recreated() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            runtime_paths.default_inventory_file.unlink()

            resolved_path, resolved_label = resolve_inventory_reference(
                None, envmgr_home=envmgr_home
            )
            if resolved_label != "default":
                raise AssertionError(
                    "expected recreated runtime inventory to keep alias"
                )
            if resolved_path != runtime_paths.default_inventory_file.resolve():
                raise AssertionError(
                    "expected recreated runtime inventory path to match ~/.envmgr"
                )
            if not runtime_paths.default_inventory_file.exists():
                raise AssertionError(
                    "expected missing runtime inventory file to be recreated"
                )

    def check_multi_node_inventory_topology() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            runtime_paths.config_file.write_text(
                """
[default]
inventory = "ci_cluster"
playbook = "node"
ask_vault_pass = false

[inventory]
default = "inventory/default.yaml"
remote = "inventory/remote.yaml"
password = "inventory/password.yaml"
ci_cluster = "inventory/ci-cluster.yaml"
""".lstrip(),
                encoding="utf-8",
            )

            ci_inventory_path = runtime_paths.inventory_dir / "ci-cluster.yaml"
            ci_inventory_path.write_text(
                """
all:
  children:
    node:
      children:
        master:
          hosts:
            master-ci:
              ansible_connection: local
              ansible_python_interpreter: "{{ ansible_playbook_python }}"
        worker:
          hosts:
            worker-ci-1:
              ansible_connection: local
              ansible_python_interpreter: "{{ ansible_playbook_python }}"
            worker-ci-2:
              ansible_connection: local
              ansible_python_interpreter: "{{ ansible_playbook_python }}"
""".lstrip(),
                encoding="utf-8",
            )

            inventory_path, inventory_label = resolve_inventory_reference(
                "ci_cluster",
                envmgr_home=envmgr_home,
            )
            if inventory_label != "ci_cluster":
                raise AssertionError("expected ci_cluster inventory alias to resolve")

            try:
                list_hosts_result = run_runtime_subprocess(
                    [
                        "ansible-playbook",
                        "-i",
                        str(inventory_path),
                        "playbooks/node.yml",
                        "--list-hosts",
                    ],
                    check=True,
                    runtime_paths=runtime_paths,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as error:
                output = (error.stdout or error.stderr or "").strip()
                raise AssertionError(
                    "expected node playbook to list hosts for ci_cluster inventory"
                    + (f": {output}" if output else "")
                ) from error

            list_hosts_output = list_hosts_result.stdout
            for host_name in ("master-ci", "worker-ci-1", "worker-ci-2"):
                if host_name not in list_hosts_output:
                    raise AssertionError(
                        f"expected node playbook to target {host_name}"
                    )

            topology_playbook_path = Path(temp_dir) / "ci-cluster-topology.yml"
            topology_playbook_path.write_text(
                """
- name: Verify master topology
  hosts: master
  gather_facts: false
  tasks:
    - name: Assert master inventory wiring
      ansible.builtin.assert:
        that:
          - inventory_hostname == 'master-ci'
          - groups['master'] | length == 1
          - groups['worker'] | length == 2
          - groups['node'] | sort | join(',') == 'master-ci,worker-ci-1,worker-ci-2'
          - "'master' in group_names"
          - "'worker' not in group_names"

- name: Verify worker topology
  hosts: worker
  gather_facts: false
  tasks:
    - name: Assert worker inventory wiring
      ansible.builtin.assert:
        that:
          - inventory_hostname in groups['worker']
          - groups['master'][0] == 'master-ci'
          - groups['worker'] | sort | join(',') == 'worker-ci-1,worker-ci-2'
          - "'worker' in group_names"
          - "'master' not in group_names"
""".lstrip(),
                encoding="utf-8",
            )

            try:
                run_runtime_subprocess(
                    [
                        "ansible-playbook",
                        "-i",
                        str(inventory_path),
                        str(topology_playbook_path),
                    ],
                    check=True,
                    runtime_paths=runtime_paths,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as error:
                output = "\n".join(
                    part
                    for part in (
                        (error.stdout or "").strip(),
                        (error.stderr or "").strip(),
                    )
                    if part
                )
                raise AssertionError(
                    "expected ci_cluster topology playbook to validate master and "
                    "worker group wiring" + (f": {output}" if output else "")
                ) from error

    def check_doctor_report_detects_unbootstrapped_runtime() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            report = build_doctor_report(envmgr_home)
            check_statuses = {check.name: check.status for check in report.checks}

            if check_statuses.get("runtime home") != DOCTOR_FAIL:
                raise AssertionError(
                    "expected doctor to fail when the runtime home is missing"
                )
            if check_statuses.get("runtime config") != DOCTOR_FAIL:
                raise AssertionError(
                    "expected doctor to fail when config.toml is missing"
                )
            if check_statuses.get("setup state") != DOCTOR_FAIL:
                raise AssertionError(
                    "expected doctor to fail when setup has not completed"
                )

    def check_doctor_report_passes_bootstrapped_runtime() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
            (runtime_paths.galaxy_collections_dir / "community").mkdir()
            mark_runtime_setup_complete(runtime_paths)

            report = build_doctor_report(envmgr_home)
            failures = [
                check.name for check in report.checks if check.status == DOCTOR_FAIL
            ]
            if failures:
                raise AssertionError(
                    "expected doctor to pass a bootstrapped runtime, got failures: "
                    + ", ".join(failures)
                )

            check_statuses = {check.name: check.status for check in report.checks}
            if "runtime config" in check_statuses:
                raise AssertionError(
                    "expected doctor to omit runtime config from healthy output"
                )
            if check_statuses.get("setup state") != DOCTOR_OK:
                raise AssertionError("expected doctor to report setup as complete")
            if "default playbook" in check_statuses:
                raise AssertionError(
                    "expected doctor to fold default playbook into runtime config"
                )
            if check_statuses.get("inventory alias `default`") != DOCTOR_OK:
                raise AssertionError(
                    "expected doctor to validate the default inventory alias"
                )

    def check_doctor_ignores_non_default_inventory_aliases() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
            (runtime_paths.galaxy_collections_dir / "community").mkdir()
            mark_runtime_setup_complete(runtime_paths)
            runtime_paths.remote_inventory_file.unlink()
            runtime_paths.password_inventory_file.unlink()

            report = build_doctor_report(envmgr_home)
            failures = [
                check.name for check in report.checks if check.status == DOCTOR_FAIL
            ]
            if failures:
                raise AssertionError(
                    "expected doctor to ignore non-default inventory aliases, got "
                    "failures: " + ", ".join(failures)
                )

            if any(
                check.name == "inventory alias `remote`" for check in report.checks
            ) or any(
                check.name == "inventory alias `password`" for check in report.checks
            ):
                raise AssertionError(
                    "expected doctor to skip non-default inventory alias checks"
                )

    def check_doctor_text_output() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
            (runtime_paths.galaxy_collections_dir / "community").mkdir()
            mark_runtime_setup_complete(runtime_paths)
            captured_output = io.StringIO()

            with (
                patch("sys.argv", ["doctor"]),
                patch("sys.stdout", new=captured_output),
                patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            ):
                doctor()

            output = captured_output.getvalue()
            for expected_fragment in (
                "Envmgr Doctor",
                "Runtime home",
                "(from ENVMGR_HOME)",
                "Defaults",
                "STATUS",
                "CHECK",
                "DETAIL",
                "commands",
                "inventory default",
                "setup",
            ):
                if expected_fragment not in output:
                    raise AssertionError(
                        f"expected doctor text output to include {expected_fragment!r}"
                    )
            if "runtime dirs" in output:
                raise AssertionError(
                    "expected doctor text output to omit runtime dirs when healthy"
                )
            if "Default playbook" in output:
                raise AssertionError(
                    "expected doctor text output to fold the default playbook into "
                    "the defaults/runtime config lines"
                )
            if "runtime config" in output:
                raise AssertionError(
                    "expected doctor text output to omit runtime config when healthy"
                )
            if "ENVMGR_HOME   " in output:
                raise AssertionError(
                    "expected doctor text output to fold ENVMGR_HOME into runtime home"
                )

    def check_doctor_json_output() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
            (runtime_paths.galaxy_collections_dir / "community").mkdir()
            mark_runtime_setup_complete(runtime_paths)
            captured_output = io.StringIO()

            with (
                patch("sys.argv", ["doctor", "--json"]),
                patch("sys.stdout", new=captured_output),
                patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            ):
                doctor()

            payload = json.loads(captured_output.getvalue())
            if payload["status"] != DOCTOR_OK:
                raise AssertionError("expected doctor --json to report ok status")
            if payload["runtime"]["home"] != str(envmgr_home.resolve()):
                raise AssertionError(
                    "expected doctor --json to report the resolved runtime home"
                )
            if payload["runtime"]["configured_home"] != str(envmgr_home.resolve()):
                raise AssertionError(
                    "expected doctor --json to include ENVMGR_HOME when set"
                )
            if payload["summary"]["fail"] != 0:
                raise AssertionError(
                    "expected doctor --json to report zero failures for a "
                    "bootstrapped runtime"
                )
            if payload["runtime"]["config_file"] != str(runtime_paths.config_file):
                raise AssertionError(
                    "expected doctor --json to expose the runtime config path"
                )
            if payload["defaults"]["inventory"] != "default":
                raise AssertionError(
                    "expected doctor --json to expose the default inventory"
                )
            if payload["defaults"]["playbook"] != "playbooks/workstation.yml":
                raise AssertionError(
                    "expected doctor --json to expose the resolved default playbook"
                )
            if not isinstance(payload["checks"], list) or not payload["checks"]:
                raise AssertionError(
                    "expected doctor --json to include per-check entries"
                )
            if payload["checks"][0]["name"] != "commands":
                raise AssertionError(
                    "expected doctor --json to summarize command checks into one row"
                )
            if any(check["name"] == "default playbook" for check in payload["checks"]):
                raise AssertionError(
                    "expected doctor --json to fold default playbook into runtime config"
                )
            if any(check["name"] == "runtime config" for check in payload["checks"]):
                raise AssertionError(
                    "expected doctor --json to omit runtime config when healthy"
                )

    parser = argparse.ArgumentParser(
        description="Run lightweight smoke tests for metadata, scaffolds, and playbooks"
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

    args = parser.parse_args()

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
        run_assertion_step("metadata catalog", check_metadata_catalog),
        run_assertion_step("role scaffold", check_scaffold_generation),
        run_assertion_step("playbook resolution", check_playbook_resolution),
        run_assertion_step(
            "execution playbook generation",
            check_execution_playbook_generation,
        ),
        run_assertion_step("runtime config bootstrap", check_runtime_config_bootstrap),
        run_assertion_step(
            "setup marker is written after setup",
            check_setup_marker_is_written_after_setup,
        ),
        run_assertion_step(
            "unbootstrapped runtime surfaces setup guidance",
            check_unbootstrapped_runtime_surfaces_setup_guidance,
        ),
        run_assertion_step(
            "outdated setup stamp requires setup",
            check_outdated_setup_stamp_requires_setup,
        ),
        run_assertion_step(
            "AI tools install options resolve correctly",
            check_ai_tools_install_option_resolution,
        ),
        run_assertion_step(
            "AI tools setup wizard flow",
            check_ai_tools_setup_wizard_flow,
        ),
        run_assertion_step(
            "unknown inventory aliases are rejected",
            check_unknown_inventory_alias_is_rejected,
        ),
        run_assertion_step(
            "runtime env uses ~/.envmgr paths only",
            check_runtime_env_uses_runtime_paths_only,
        ),
        run_assertion_step(
            "runtime subprocess helpers use ~/.envmgr paths",
            check_runtime_subprocess_helpers_use_runtime_paths,
        ),
        run_assertion_step(
            "setup logs ansible-galaxy runtime runs",
            check_setup_logs_ansible_galaxy_runs,
        ),
        run_assertion_step(
            "history renders readable text output",
            check_history_text_output,
        ),
        run_assertion_step(
            "history emits json output",
            check_history_json_output,
        ),
        run_assertion_step(
            "inventory aliases stay under ~/.envmgr/inventory",
            check_inventory_aliases_stay_under_runtime_inventory_dir,
        ),
        run_assertion_step(
            "invalid TOML surfaces config error",
            check_invalid_toml_surfaces_config_error,
        ),
        run_assertion_step(
            "missing runtime inventory file is recreated",
            check_missing_runtime_inventory_file_is_recreated,
        ),
        run_assertion_step(
            "multi-node inventory topology",
            check_multi_node_inventory_topology,
        ),
        run_assertion_step(
            "doctor detects an unbootstrapped runtime",
            check_doctor_report_detects_unbootstrapped_runtime,
        ),
        run_assertion_step(
            "doctor passes a bootstrapped runtime",
            check_doctor_report_passes_bootstrapped_runtime,
        ),
        run_assertion_step(
            "doctor ignores non-default inventory aliases",
            check_doctor_ignores_non_default_inventory_aliases,
        ),
        run_assertion_step(
            "doctor renders readable text output",
            check_doctor_text_output,
        ),
        run_assertion_step(
            "doctor emits json output",
            check_doctor_json_output,
        ),
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
