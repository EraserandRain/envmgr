from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..runtime_config import ensure_runtime_layout
from ..services.doctor import DOCTOR_OK
from ..services.runtime import (
    RUNTIME_RUN_RECORD_SCHEMA_VERSION,
    write_runtime_run_record,
)
from .helpers import REPO_ROOT, bootstrap_cli_runtime, run_envmgr_cli


def check_envmgr_help_contract() -> None:
    result = run_envmgr_cli("--help")
    if result.returncode != 0:
        raise AssertionError(
            "expected `envmgr --help` to exit successfully"
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    output = result.stdout
    for expected_fragment in (
        "Usage: envmgr",
        "doctor",
        "history",
        "install",
        "ping",
        "setup",
    ):
        if expected_fragment not in output:
            raise AssertionError(
                f"expected `envmgr --help` to include {expected_fragment!r}"
            )
    if "validate" in output:
        raise AssertionError(
            "expected `envmgr --help` to omit development-only subcommands"
        )
    if result.stderr:
        raise AssertionError("expected `envmgr --help` to keep stderr empty")


def check_envmgr_invalid_command_contract() -> None:
    result = run_envmgr_cli("validate")
    if result.returncode != 2:
        raise AssertionError(
            "expected an unknown `envmgr` subcommand to exit with Click/Typer code 2"
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    stderr = result.stderr
    if "No such command 'validate'" not in stderr:
        raise AssertionError(
            "expected invalid subcommands to surface the Click/Typer unknown-command error"
        )
    if "Try 'envmgr --help' for help." not in stderr:
        raise AssertionError(
            "expected invalid subcommands to point users at `envmgr --help`"
        )


def check_doctor_json_cli_contract() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = bootstrap_cli_runtime(envmgr_home)
        result = run_envmgr_cli(
            "doctor",
            "--json",
            env_overrides={"ENVMGR_HOME": str(envmgr_home)},
        )

        if result.returncode != 0:
            raise AssertionError(
                "expected `envmgr doctor --json` to succeed for a bootstrapped runtime"
                f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        if result.stderr:
            raise AssertionError("expected `envmgr doctor --json` to keep stderr empty")

        payload = json.loads(result.stdout)
        if payload["status"] != DOCTOR_OK:
            raise AssertionError("expected `envmgr doctor --json` to report ok status")
        if payload["summary"]["fail"] != 0:
            raise AssertionError(
                "expected `envmgr doctor --json` to report zero failed checks"
            )
        if payload["runtime"]["home"] != str(envmgr_home.resolve()):
            raise AssertionError(
                "expected `envmgr doctor --json` to report the resolved runtime home"
            )
        if payload["runtime"]["configured_home"] != str(envmgr_home.resolve()):
            raise AssertionError(
                "expected `envmgr doctor --json` to expose ENVMGR_HOME explicitly"
            )
        if payload["runtime"]["config_file"] != str(runtime_paths.config_file):
            raise AssertionError(
                "expected `envmgr doctor --json` to expose the runtime config path"
            )
        if not isinstance(payload["checks"], list) or not payload["checks"]:
            raise AssertionError(
                "expected `envmgr doctor --json` to include per-check details"
            )


def check_history_json_cli_contract() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = ensure_runtime_layout(envmgr_home)
        record_path = (
            runtime_paths.runs_log_dir / "20260419T000000000000Z-ansible-12345678.json"
        )
        write_runtime_run_record(
            record_path,
            {
                "schema_version": RUNTIME_RUN_RECORD_SCHEMA_VERSION,
                "mode": "run",
                "command_name": "ansible",
                "command": ["ansible", "-m", "ping", "all"],
                "cwd": str(REPO_ROOT),
                "runtime_home": str(envmgr_home.resolve()),
                "ansible_log_file": str(runtime_paths.ansible_log_file),
                "status": "succeeded",
                "pid": 1234,
                "return_code": 0,
                "started_at": "2026-04-19T00:00:00Z",
                "completed_at": "2026-04-19T00:00:01Z",
                "duration_seconds": 1.0,
                "error": None,
            },
        )

        result = run_envmgr_cli(
            "history",
            "--json",
            "-n",
            "1",
            env_overrides={"ENVMGR_HOME": str(envmgr_home)},
        )

        if result.returncode != 0:
            raise AssertionError(
                "expected `envmgr history --json` to succeed"
                f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        if result.stderr:
            raise AssertionError(
                "expected `envmgr history --json` to keep stderr empty"
            )

        payload = json.loads(result.stdout)
        if payload["count"] != 1 or payload["total"] != 1:
            raise AssertionError(
                "expected `envmgr history --json` to report the selected and total counts"
            )
        if payload["runtime"]["home"] != str(envmgr_home.resolve()):
            raise AssertionError(
                "expected `envmgr history --json` to report the resolved runtime home"
            )
        if payload["runtime"]["configured_home"] != str(envmgr_home.resolve()):
            raise AssertionError(
                "expected `envmgr history --json` to expose ENVMGR_HOME explicitly"
            )
        if payload["records"][0]["command"] != ["ansible", "-m", "ping", "all"]:
            raise AssertionError(
                "expected `envmgr history --json` to expose the stored command"
            )
        if payload["records"][0]["record_path"] != str(record_path):
            raise AssertionError(
                "expected `envmgr history --json` to expose the record path"
            )


def check_install_list_tags_cli_contract() -> None:
    result = run_envmgr_cli("install", "-l")
    if result.returncode != 0:
        raise AssertionError(
            "expected `envmgr install -l` to exit successfully"
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    if result.stderr:
        raise AssertionError("expected `envmgr install -l` to keep stderr empty")

    output = result.stdout
    for expected_fragment in (
        "Envmgr available tags:",
        "Role level tags:",
        "Task level tags:",
        "  - init",
        "  - codex",
        "  - rtk",
    ):
        if expected_fragment not in output:
            raise AssertionError(
                f"expected `envmgr install -l` to include {expected_fragment!r}"
            )
    if "init_core" in output:
        raise AssertionError(
            "expected `envmgr install -l` to keep hidden task tags out of the public CLI"
        )


def check_ping_cli_contract() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = bootstrap_cli_runtime(envmgr_home)
        result = run_envmgr_cli(
            "ping",
            env_overrides={"ENVMGR_HOME": str(runtime_paths.home)},
        )

        if result.returncode != 0:
            raise AssertionError(
                "expected `envmgr ping` to succeed for the bootstrapped local runtime"
                f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        if result.stderr:
            raise AssertionError("expected `envmgr ping` to keep stderr empty")

        output = result.stdout
        if "Testing connection with inventory: default ->" not in output:
            raise AssertionError(
                "expected `envmgr ping` to print the selected default inventory"
            )
        if "localhost" not in output or "SUCCESS" not in output:
            raise AssertionError(
                "expected `envmgr ping` to report a successful localhost ansible ping"
            )
