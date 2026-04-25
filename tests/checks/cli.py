from __future__ import annotations

import configparser
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import cast
from unittest.mock import patch

from click.testing import Result
from typer.testing import CliRunner

from scripts.main import app
from scripts.runtime_config import ensure_runtime_layout, mark_runtime_setup_complete

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

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


def _create_checkout_stub(base_dir: Path) -> Path:
    """Create the minimal checkout markers required by repo-only helpers."""
    checkout_root = base_dir / "envmgr-checkout"
    checkout_root.mkdir()
    (checkout_root / "pyproject.toml").write_text("", encoding="utf-8")
    for relative_path in (
        Path("playbooks"),
        Path("roles"),
        Path("scripts/commands"),
        Path("tests"),
    ):
        (checkout_root / relative_path).mkdir(parents=True, exist_ok=True)
    return checkout_root


def _bootstrap_runtime(envmgr_home: Path) -> None:
    """Create a minimal bootstrapped runtime for CLI contract checks."""
    runtime_paths = ensure_runtime_layout(envmgr_home)
    (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
    (runtime_paths.galaxy_collections_dir / "community").mkdir()
    mark_runtime_setup_complete(runtime_paths)


def _load_toml_document(path: Path) -> dict[str, object]:
    return cast(dict[str, object], tomllib.loads(path.read_text(encoding="utf-8")))


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
        "self",
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


def check_public_cli_help_aliases_version_and_completion() -> None:
    for args in (("--help",), ("-h",)):
        result = invoke_envmgr(*args)
        if result.exit_code != 0:
            raise AssertionError(
                f"expected `envmgr {' '.join(args)}` to exit successfully"
                f"\noutput:\n{result.output}"
            )

        output = _collapse_whitespace(
            _normalize_cli_output(result.stdout, result.stderr)
        )
        for expected_fragment in (
            "Usage: envmgr",
            "--version",
            "--help",
            "-h",
        ):
            if expected_fragment not in output:
                raise AssertionError(
                    f"expected `envmgr {' '.join(args)}` to include "
                    f"{expected_fragment!r}"
                )
        for completion_fragment in ("--install-completion", "--show-completion"):
            if completion_fragment in output:
                raise AssertionError(
                    f"expected public help to omit {completion_fragment!r}"
                )

    version_result = invoke_envmgr("--version")
    if version_result.exit_code != 0:
        raise AssertionError(
            "expected `envmgr --version` to exit successfully"
            f"\noutput:\n{version_result.output}"
        )

    version_output = _normalize_cli_output(
        version_result.stdout,
        version_result.stderr,
    ).strip()
    if re.fullmatch(r"envmgr \S+", version_output) is None:
        raise AssertionError(
            "expected `envmgr --version` to print a version string"
            f"\noutput:\n{version_output}"
        )

    for args in (("--install-completion",), ("--show-completion",)):
        result = invoke_envmgr(*args)
        if result.exit_code != 2:
            raise AssertionError(
                f"expected `envmgr {' '.join(args)}` to be rejected"
                f"\noutput:\n{result.output}"
            )


def check_runtime_subcommands_use_typer_help() -> None:
    help_expectations = (
        (
            ("install", "--help"),
            (
                "Usage: envmgr install",
                "Run Ansible roles and task tags.",
                "--help",
                "-h",
                "--list-tags",
                "--inventory",
                "Output",
                "Runtime options",
                "AI tools",
            ),
        ),
        (
            ("install", "-h"),
            (
                "Usage: envmgr install",
                "Run Ansible roles and task tags.",
                "--help",
                "-h",
                "--list-tags",
                "--inventory",
                "Output",
                "Runtime options",
                "AI tools",
            ),
        ),
        (
            ("install",),
            (
                "Usage: envmgr install",
                "Run Ansible roles and task tags.",
                "--help",
                "-h",
                "--list-tags",
                "--inventory",
                "Output",
                "Runtime options",
                "AI tools",
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
        (
            ("self", "--help"),
            (
                "Usage: envmgr self",
                "Manage installer-managed envmgr releases.",
                "update",
                "uninstall",
                "--help",
            ),
        ),
        (
            ("self", "update", "--help"),
            (
                "Usage: envmgr self update",
                "Update an install.sh-managed GitHub Release install.",
                "--version",
                "Self-management options",
            ),
        ),
        (
            ("self", "uninstall", "--help"),
            (
                "Usage: envmgr self uninstall",
                "Uninstall envmgr while keeping runtime data under ~/.envmgr.",
                "--yes",
                "Self-management options",
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


def check_create_helper_fails_when_scaffold_is_missing() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        checkout_root = _create_checkout_stub(Path(temp_dir))
        result = _invoke_dev_helper_entrypoint("create", "demo-role", cwd=checkout_root)

    if result.returncode == 0:
        raise AssertionError(
            "expected `create demo-role` to fail when the scaffold directory is missing"
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    output = _collapse_whitespace(_normalize_cli_output(result.stdout, result.stderr))
    if "Error: scaffold directory not found: scaffolds/role" not in output:
        raise AssertionError(
            "expected `create demo-role` to report the missing scaffold directory"
            f"\noutput:\n{output}"
        )


def check_create_helper_fails_when_role_already_exists() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        checkout_root = _create_checkout_stub(Path(temp_dir))
        (checkout_root / "scaffolds/role").mkdir(parents=True)
        (checkout_root / "roles/demo-role").mkdir(parents=True)

        result = _invoke_dev_helper_entrypoint("create", "demo-role", cwd=checkout_root)

    if result.returncode == 0:
        raise AssertionError(
            "expected `create demo-role` to fail when the role directory already exists"
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    output = _collapse_whitespace(_normalize_cli_output(result.stdout, result.stderr))
    if "Error: Role 'demo-role' already exists." not in output:
        raise AssertionError(
            "expected `create demo-role` to report the existing role directory"
            f"\noutput:\n{output}"
        )


def check_create_helper_succeeds_with_expected_output() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        checkout_root = _create_checkout_stub(Path(temp_dir))
        scaffold_root = checkout_root / "scaffolds/role"
        scaffold_root.mkdir(parents=True)
        (scaffold_root / "tasks").mkdir()
        (scaffold_root / "tasks/main.yml").write_text(
            "- name: Install {{ role_title }}\n",
            encoding="utf-8",
        )

        result = _invoke_dev_helper_entrypoint("create", "demo-role", cwd=checkout_root)

        generated_task = checkout_root / "roles/demo-role/tasks/main.yml"
        if not generated_task.exists():
            raise AssertionError("expected `create demo-role` to generate role files")
        rendered_task = generated_task.read_text(encoding="utf-8")

    if result.returncode != 0:
        raise AssertionError(
            "expected `create demo-role` to succeed when the scaffold exists"
            f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    output = _normalize_cli_output(result.stdout, result.stderr)
    for expected_fragment in (
        "Role 'demo-role' generated successfully.",
        "Update roles/demo-role/meta/envmgr.yml and add the role to the appropriate playbook.",
    ):
        if expected_fragment not in output:
            raise AssertionError(
                f"expected `create demo-role` to include {expected_fragment!r}"
                f"\noutput:\n{output}"
            )
    if "Install Demo Role" not in rendered_task:
        raise AssertionError("expected scaffold placeholders to render in role files")


def check_plan_a_packaging_keeps_runtime_and_checkout_scripts_split() -> None:
    root_pyproject = _load_toml_document(REPO_ROOT / "pyproject.toml")
    project = cast(dict[str, object], root_pyproject.get("project", {}))
    project_scripts = project.get("scripts")
    expected_runtime_scripts = {"envmgr": "scripts.main:main"}
    if project_scripts != expected_runtime_scripts:
        raise AssertionError(
            "expected the root package to install only the `envmgr` runtime script"
        )

    dependency_groups = cast(
        dict[str, object],
        root_pyproject.get("dependency-groups", {}),
    )
    dev_dependencies = cast(list[str] | None, dependency_groups.get("dev"))
    if dev_dependencies is None or "envmgr-dev-helpers" not in dev_dependencies:
        raise AssertionError(
            "expected checkout dev dependencies to include `envmgr-dev-helpers`"
        )

    tool = cast(dict[str, object], root_pyproject.get("tool", {}))
    uv = cast(dict[str, object], tool.get("uv", {}))
    sources = cast(dict[str, object], uv.get("sources", {}))
    helper_source = sources.get("envmgr-dev-helpers")
    if helper_source != {"path": "dev-helpers"}:
        raise AssertionError(
            "expected checkout helper scripts to come from the repo-local "
            "`dev-helpers` package"
        )

    dev_helper_pyproject = _load_toml_document(REPO_ROOT / "dev-helpers/pyproject.toml")
    helper_project = cast(dict[str, object], dev_helper_pyproject.get("project", {}))
    helper_scripts = helper_project.get("scripts")
    expected_helper_scripts = {
        "create": "scripts.commands.create:main",
        "lint": "scripts.commands.lint:main",
        "ansible-check": "scripts.commands.ansible_check:main",
        "typecheck": "scripts.commands.typecheck:main",
        "validate": "scripts.commands.validate:main",
        "smoke-test": "scripts.commands.smoke_test:main",
    }
    if helper_scripts != expected_helper_scripts:
        raise AssertionError(
            "expected checkout-only helper entry points to stay in "
            "`dev-helpers/pyproject.toml`"
        )


def check_built_wheel_exposes_only_runtime_console_script() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        wheel_dir = Path(temp_dir) / "wheelhouse"
        wheel_dir.mkdir()
        result = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(wheel_dir)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                "expected `uv build --wheel` to build the release wheel"
                f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

        wheel_paths = sorted(wheel_dir.glob("envmgr-*.whl"))
        if len(wheel_paths) != 1:
            raise AssertionError(
                "expected exactly one envmgr wheel to be built"
                f"\nwheels: {[path.name for path in wheel_paths]}"
                f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

        with zipfile.ZipFile(wheel_paths[0]) as wheel:
            entry_point_paths = [
                name
                for name in wheel.namelist()
                if name.endswith(".dist-info/entry_points.txt")
            ]
            if len(entry_point_paths) != 1:
                raise AssertionError(
                    "expected the built wheel to contain exactly one "
                    "entry_points.txt file"
                    f"\nentry_points files: {entry_point_paths}"
                )
            entry_points_text = wheel.read(entry_point_paths[0]).decode("utf-8")

    parser = configparser.ConfigParser()
    parser.read_string(entry_points_text)
    console_scripts = (
        dict(parser.items("console_scripts"))
        if parser.has_section("console_scripts")
        else {}
    )
    expected_console_scripts = {"envmgr": "scripts.main:main"}
    if console_scripts != expected_console_scripts:
        raise AssertionError(
            "expected the built wheel to expose only the `envmgr` runtime "
            "console script"
            f"\nconsole_scripts: {console_scripts}"
            f"\nentry_points.txt:\n{entry_points_text}"
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
