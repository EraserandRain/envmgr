from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from ..runtime_config import ensure_runtime_layout, get_runtime_paths
from ..services.doctor import DOCTOR_OK
from ..services.runtime import (
    RUNTIME_RUN_RECORD_SCHEMA_VERSION,
    write_runtime_run_record,
)
from .helpers import REPO_ROOT, bootstrap_cli_runtime, run_envmgr_cli

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    """Normalize subprocess output before asserting on human-readable content."""
    return _ANSI_ESCAPE_RE.sub("", text)


def _combined_cli_output(stdout: str, stderr: str) -> str:
    """Normalize both streams because Click/Typer may route help text differently."""
    normalized_parts = [
        _strip_ansi(stream).replace("\r\n", "\n")
        for stream in (stdout, stderr)
        if stream
    ]
    return "\n".join(normalized_parts)


def _collapse_whitespace(text: str) -> str:
    """Keep help and setup-hint assertions stable even when Rich wraps lines."""
    return " ".join(text.split())


def _write_fake_command(command_path: Path, body: str) -> None:
    """Create a small executable used to stub ansible binaries in smoke tests."""
    command_path.write_text(body, encoding="utf-8")
    command_path.chmod(0o755)


def _prepend_path(fake_bin_dir: Path) -> str:
    """Put a temporary bin directory ahead of the current PATH."""
    current_path = os.environ.get("PATH", "")
    if not current_path:
        return str(fake_bin_dir)
    return f"{fake_bin_dir}{os.pathsep}{current_path}"


def check_envmgr_help_contract() -> None:
    result = run_envmgr_cli("--help")
    if result.returncode != 0:
        raise AssertionError(
            "expected `envmgr --help` to exit successfully"
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    output = _collapse_whitespace(_combined_cli_output(result.stdout, result.stderr))
    for expected_fragment in (
        "Usage: envmgr",
        "Direct runtime commands for envmgr.",
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


def check_envmgr_invalid_command_contract() -> None:
    result = run_envmgr_cli("validate")
    if result.returncode != 2:
        raise AssertionError(
            "expected an unknown `envmgr` subcommand to exit with Click/Typer code 2"
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    output = _combined_cli_output(result.stdout, result.stderr)
    if "No such command 'validate'" not in output:
        raise AssertionError(
            "expected invalid subcommands to surface the Click/Typer unknown-command error"
        )
    if "Try 'envmgr --help' for help." not in output:
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


def check_setup_cli_contract() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        envmgr_home = temp_root / ".envmgr"
        fake_bin_dir = temp_root / "bin"
        fake_bin_dir.mkdir()
        _write_fake_command(
            fake_bin_dir / "ansible-galaxy",
            "#!/bin/sh\nexit 0\n",
        )

        result = run_envmgr_cli(
            "setup",
            env_overrides={
                "ENVMGR_HOME": str(envmgr_home),
                "PATH": _prepend_path(fake_bin_dir),
            },
        )

        if result.returncode != 0:
            raise AssertionError(
                "expected `envmgr setup` to succeed with a fake ansible-galaxy binary"
                f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        if result.stderr:
            raise AssertionError("expected `envmgr setup` to keep stderr empty")

        runtime_paths = get_runtime_paths(envmgr_home)
        output = _strip_ansi(result.stdout)
        for expected_fragment in (
            "Envmgr Setup",
            "Bootstrap the envmgr runtime under ~/.envmgr.",
            "Info: Initializing ~/.envmgr...",
            f"Runtime config: {runtime_paths.config_file}",
            f"Ansible log: {runtime_paths.ansible_log_file}",
            f"Galaxy roles cache: {runtime_paths.galaxy_roles_dir}",
            f"Galaxy collections cache: {runtime_paths.galaxy_collections_dir}",
            "Info: Installing Ansible roles and collections...",
            "Success: Ansible roles and collections installed successfully.",
            "Success: Setup completed successfully.",
        ):
            if expected_fragment not in output:
                raise AssertionError(
                    f"expected `envmgr setup` to include {expected_fragment!r}"
                )

        if not runtime_paths.setup_marker_file.exists():
            raise AssertionError(
                "expected `envmgr setup` to mark the runtime as bootstrapped"
            )


def check_ping_cli_contract() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        envmgr_home = temp_root / ".envmgr"
        missing_runtime_result = run_envmgr_cli(
            "ping",
            env_overrides={"ENVMGR_HOME": str(envmgr_home)},
        )
        if missing_runtime_result.returncode != 1:
            raise AssertionError(
                "expected `envmgr ping` to exit with code 1 before setup"
                f"\nstdout:\n{missing_runtime_result.stdout}"
                f"\nstderr:\n{missing_runtime_result.stderr}"
            )

        missing_runtime_output = _collapse_whitespace(
            _combined_cli_output(
                missing_runtime_result.stdout,
                missing_runtime_result.stderr,
            )
        )
        if "Please run `envmgr setup` first." not in missing_runtime_output:
            raise AssertionError(
                "expected `envmgr ping` to point users at `envmgr setup` before setup"
            )
        if "uv run envmgr" in missing_runtime_output:
            raise AssertionError(
                "expected `envmgr ping` setup guidance to avoid `uv run envmgr`"
            )

        runtime_paths = bootstrap_cli_runtime(envmgr_home)
        fake_bin_dir = temp_root / "bin"
        fake_bin_dir.mkdir()
        _write_fake_command(
            fake_bin_dir / "ansible",
            (
                "#!/bin/sh\n"
                "printf 'localhost | SUCCESS => {\\n'\n"
                'printf \'    "ping": "pong"\\n\'\n'
                "printf '}\\n'\n"
            ),
        )
        result = run_envmgr_cli(
            "ping",
            env_overrides={
                "ENVMGR_HOME": str(runtime_paths.home),
                "PATH": _prepend_path(fake_bin_dir),
            },
        )

        if result.returncode != 0:
            raise AssertionError(
                "expected `envmgr ping` to succeed for the bootstrapped local runtime"
                f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        if result.stderr:
            raise AssertionError("expected `envmgr ping` to keep stderr empty")

        output = _strip_ansi(result.stdout)
        for expected_fragment in (
            "Envmgr Ping",
            "Test inventory connectivity with ansible ping.",
            "Inventory: default",
            f"Inventory path: {runtime_paths.default_inventory_file}",
            "Info: Running ansible ping against all hosts...",
            "localhost | SUCCESS =>",
            '"ping": "pong"',
            "Success: Ping completed successfully.",
        ):
            if expected_fragment not in output:
                raise AssertionError(
                    f"expected `envmgr ping` to include {expected_fragment!r}"
                )
