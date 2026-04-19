from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from ..main import doctor, history
from ..runtime_config import ensure_runtime_layout, mark_runtime_setup_complete
from ..services.doctor import DOCTOR_FAIL, DOCTOR_OK, build_doctor_report
from ..services.runtime import (
    RUNTIME_RUN_RECORD_SCHEMA_VERSION,
    write_runtime_run_record,
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
            patch("sys.stdout", new=captured_output),
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
        ):
            history(["--limit", "2"])

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
            or "ansible-playbook playbooks/workstation.yml --syntax-check" not in output
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
            runtime_paths.runs_log_dir / "20260418T120000000000Z-ansible-44444444.json",
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
            patch("sys.stdout", new=captured_output),
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
        ):
            history(["--json"])

        payload = json.loads(captured_output.getvalue())
        if payload["count"] != 1 or payload["total"] != 1:
            raise AssertionError("expected history --json to report record counts")
        if payload["runtime"]["home"] != str(runtime_paths.home):
            raise AssertionError("expected history --json to report the runtime home")
        if payload["records"][0]["command_name"] != "ansible":
            raise AssertionError(
                "expected history --json to expose stored runtime records"
            )


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
            raise AssertionError("expected doctor to fail when config.toml is missing")
        if check_statuses.get("setup state") != DOCTOR_FAIL:
            raise AssertionError("expected doctor to fail when setup has not completed")


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
        ) or any(check.name == "inventory alias `password`" for check in report.checks):
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
            patch("sys.stdout", new=captured_output),
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
        ):
            doctor([])

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
            patch("sys.stdout", new=captured_output),
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
        ):
            doctor(["--json"])

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
            raise AssertionError("expected doctor --json to include per-check entries")
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
