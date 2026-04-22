from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import Result
from typer.testing import CliRunner

from scripts.commands.dev_shared import DEV_HELPER_BOUNDARY_MESSAGE
from scripts.main import app
from scripts.runtime_config import ensure_runtime_layout, mark_runtime_setup_complete

CLI_RUNNER = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def invoke_envmgr(*args: str) -> Result:
    return CLI_RUNNER.invoke(app, list(args), prog_name="envmgr")


def _normalize_cli_output(*streams: str) -> str:
    """Normalize stdout/stderr because Click/Typer may split Rich output by stream."""
    normalized_parts = [
        _ANSI_ESCAPE_RE.sub("", stream).replace("\r\n", "\n")
        for stream in streams
        if stream
    ]
    return "\n".join(normalized_parts)


def _collapse_whitespace(text: str) -> str:
    """Keep help assertions stable even when Rich reflows text across lines."""
    return " ".join(text.split())


def _invoke_dev_helper_entrypoint(
    module_name: str,
    *args: str,
    cwd: Path = REPO_ROOT,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if extra_env is not None:
        env.update(extra_env)

    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(REPO_ROOT)!r}); "
                f"from scripts.commands.{module_name} import main; "
                "main()"
            ),
            *args,
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _invoke_dev_helper_entrypoint_help(
    module_name: str,
) -> subprocess.CompletedProcess[str]:
    return _invoke_dev_helper_entrypoint(module_name, "--help")


def _bootstrap_runtime(envmgr_home: Path) -> None:
    """Create a minimal bootstrapped runtime for CLI contract checks."""
    runtime_paths = ensure_runtime_layout(envmgr_home)
    (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
    (runtime_paths.galaxy_collections_dir / "community").mkdir()
    mark_runtime_setup_complete(runtime_paths)


def check_dispatcher_routes_install_subcommand() -> None:
    help_result = invoke_envmgr("--help")
    if help_result.exit_code != 0:
        raise AssertionError(
            "expected `envmgr --help` to exit successfully"
            f"\noutput:\n{help_result.output}"
        )

    help_output = _collapse_whitespace(
        _normalize_cli_output(help_result.stdout, help_result.stderr)
    )
    for expected_fragment in (
        "Usage: envmgr",
        "Direct runtime commands for envmgr.",
        "doctor",
        "history",
        "install",
        "ping",
        "setup",
    ):
        if expected_fragment not in help_output:
            raise AssertionError(
                f"expected `envmgr --help` to include {expected_fragment!r}"
            )
    if "validate" in help_output:
        raise AssertionError(
            "expected `envmgr --help` to omit development-only subcommands"
        )

    with patch(
        "scripts.commands.install.load_available_tags",
        return_value=(["zsh"], ["codex"]),
    ):
        result = invoke_envmgr("install", "-l")

    if result.exit_code != 0:
        raise AssertionError(
            "expected dispatcher to route to the install subcommand"
            f"\noutput:\n{result.output}"
        )

    output = result.output
    if "Envmgr available tags:" not in output:
        raise AssertionError("expected dispatcher to route to the install subcommand")
    if "  - zsh" not in output:
        raise AssertionError("expected dispatcher to print install role tags")
    if "  - codex" not in output:
        raise AssertionError("expected dispatcher to print install task tags")


def check_runtime_subcommands_use_typer_help() -> None:
    help_expectations = (
        (
            ("install", "--help"),
            (
                "Usage: envmgr install",
                "Run Ansible roles and task tags.",
                "--list-tags",
                "--inventory",
            ),
        ),
        (
            ("setup", "--help"),
            (
                "Usage: envmgr setup",
                "Bootstrap the envmgr runtime under ~/.envmgr.",
                "--help",
            ),
        ),
        (
            ("ping", "--help"),
            (
                "Usage: envmgr ping",
                "Test inventory connectivity with ansible ping.",
                "--inventory",
            ),
        ),
    )

    for args, expected_fragments in help_expectations:
        result = invoke_envmgr(*args)
        if result.exit_code != 0:
            raise AssertionError(
                f"expected `{' '.join(args)}` to exit successfully"
                f"\noutput:\n{result.output}"
            )

        output = _normalize_cli_output(result.stdout, result.stderr)
        for expected_fragment in expected_fragments:
            if expected_fragment not in output:
                raise AssertionError(
                    f"expected `{' '.join(args)}` to include {expected_fragment!r}"
                )


def check_dev_helper_entrypoints_use_typer_help() -> None:
    help_expectations = (
        (
            "create",
            "create",
            (
                "Usage: create [OPTIONS] [ROLE]",
                "Create a new Ansible role by generating the role directory.",
                "The name of the role to create",
                "--help",
            ),
        ),
        (
            "lint",
            "lint",
            (
                "Usage: lint [OPTIONS]",
                "Run ruff linting and formatting on Python code.",
                "--help",
            ),
        ),
        (
            "ansible-check",
            "ansible_check",
            (
                "Usage: ansible-check [OPTIONS]",
                "Run ansible-lint on the roles directory.",
                "--help",
            ),
        ),
        (
            "typecheck",
            "typecheck",
            (
                "Usage: typecheck [OPTIONS]",
                "Run mypy type checking on the Python source directories.",
                "--help",
            ),
        ),
        (
            "validate",
            "validate",
            (
                "Usage: validate [OPTIONS]",
                "Run lint, typecheck, ansible lint, and playbook syntax checks.",
                "--inventory",
                "--playbook",
            ),
        ),
        (
            "smoke-test",
            "smoke_test",
            (
                "Usage: smoke-test [OPTIONS]",
                "Run lightweight smoke tests for metadata, scaffolds, and playbooks.",
                "--inventory",
                "--playbook",
            ),
        ),
    )

    for command_name, module_name, expected_fragments in help_expectations:
        result = _invoke_dev_helper_entrypoint_help(module_name)
        if result.returncode != 0:
            raise AssertionError(
                f"expected `uv run {command_name} --help` to exit successfully"
                f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

        output = _collapse_whitespace(
            _normalize_cli_output(result.stdout, result.stderr)
        )
        for expected_fragment in expected_fragments:
            if expected_fragment not in output:
                raise AssertionError(
                    f"expected `uv run {command_name} --help` to include "
                    f"{expected_fragment!r}\noutput:\n{output}"
                )


def check_dev_helpers_reject_unsupported_non_repo_cwds() -> None:
    helper_expectations = (
        ("validate", "validate"),
        ("smoke-test", "smoke_test"),
        ("lint", "lint"),
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        unsupported_cwd = Path(temp_dir) / "outside-checkout"
        unsupported_cwd.mkdir()
        helper_env = {
            "ENVMGR_HOME": str(Path(temp_dir) / ".envmgr"),
            "PATH": "",
        }

        for command_name, module_name in helper_expectations:
            result = _invoke_dev_helper_entrypoint(
                module_name,
                cwd=unsupported_cwd,
                extra_env=helper_env,
            )
            if result.returncode != 1:
                raise AssertionError(
                    f"expected `{command_name}` to fail with exit code 1 outside "
                    "a repo checkout"
                    f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                )

            output = _collapse_whitespace(
                _normalize_cli_output(result.stdout, result.stderr)
            )
            expected_message = DEV_HELPER_BOUNDARY_MESSAGE.format(
                command_name=command_name
            )
            if expected_message not in output:
                raise AssertionError(
                    f"expected `{command_name}` to report the shared repo-only "
                    "boundary message outside a checkout"
                    f"\noutput:\n{output}"
                )


def check_dispatcher_routes_setup_subcommand() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        with (
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            patch(
                "scripts.commands.setup.run_runtime_subprocess",
                return_value=subprocess.CompletedProcess(
                    ["ansible-galaxy", "--version"],
                    0,
                ),
            ),
        ):
            result = invoke_envmgr("setup")

        if result.exit_code != 0:
            raise AssertionError(
                "expected dispatcher to route to the setup subcommand"
                f"\noutput:\n{result.output}"
            )

        runtime_paths = ensure_runtime_layout(envmgr_home)
        output = result.output
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


def check_dispatcher_routes_ping_subcommand() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        with patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False):
            missing_runtime_result = invoke_envmgr("ping")

        if missing_runtime_result.exit_code != 1:
            raise AssertionError(
                "expected `envmgr ping` to exit with code 1 before setup"
                f"\noutput:\n{missing_runtime_result.output}"
            )

        missing_runtime_output = _collapse_whitespace(
            _normalize_cli_output(
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

        _bootstrap_runtime(envmgr_home)

        with (
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            patch(
                "scripts.commands.ping.run_runtime_subprocess",
                return_value=subprocess.CompletedProcess(
                    ["ansible", "-m", "ping", "all"],
                    0,
                ),
            ),
        ):
            result = invoke_envmgr("ping", "-i", "remote")

        if result.exit_code != 0:
            raise AssertionError(
                "expected dispatcher to route to the ping subcommand"
                f"\noutput:\n{result.output}"
            )

        runtime_paths = ensure_runtime_layout(envmgr_home)
        output = result.output
        for expected_fragment in (
            "Envmgr Ping",
            "Test inventory connectivity with ansible ping.",
            "Inventory: remote",
            f"Inventory path: {runtime_paths.remote_inventory_file}",
            "Info: Running ansible ping against all hosts...",
            "Success: Ping completed successfully.",
        ):
            if expected_fragment not in output:
                raise AssertionError(
                    f"expected `envmgr ping -i remote` to include {expected_fragment!r}"
                )


def check_dispatcher_rejects_dev_only_subcommands() -> None:
    result = invoke_envmgr("validate")
    if result.exit_code != 2:
        raise AssertionError(
            "expected dispatcher to reject dev-only subcommands with exit code 2"
            f"\noutput:\n{result.output}"
        )

    output = _normalize_cli_output(result.stdout, result.stderr)
    if "No such command 'validate'" not in output:
        raise AssertionError(
            "expected dispatcher rejection to use Click/Typer unknown-command wording"
        )
    if "Try 'envmgr --help' for help." not in output:
        raise AssertionError(
            "expected dispatcher rejection to point users at `envmgr --help`"
        )
