from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..runtime_config import RuntimePaths

RUNTIME_RUN_RECORD_SCHEMA_VERSION = 1


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


def build_effective_command_path(env: dict[str, str] | None = None) -> str:
    """Build PATH so envmgr can discover executables from its current tool env."""
    source_env = os.environ if env is None else env
    path_entries: list[str] = []

    scripts_dir = sysconfig.get_path("scripts")
    if scripts_dir:
        path_entries.append(str(Path(scripts_dir).expanduser().resolve()))

    if sys.executable:
        path_entries.append(str(Path(sys.executable).expanduser().resolve().parent))

    inherited_path = source_env.get("PATH")
    if inherited_path:
        path_entries.extend(inherited_path.split(os.pathsep))

    return merge_path_entries(path_entries)


def build_ansible_runtime_env(paths: RuntimePaths) -> dict[str, str]:
    """Build a consistent Ansible runtime environment rooted in ~/.envmgr."""
    env = os.environ.copy()
    env["PATH"] = build_effective_command_path(env)
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
        env["PATH"] = build_effective_command_path(env)
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
        env["PATH"] = build_effective_command_path(env)
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
