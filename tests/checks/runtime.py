from __future__ import annotations

import importlib
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import typer
from rich.console import Console

from envmgr.command_text import SETUP_COMMAND
from envmgr.commands.setup import run_setup
from envmgr.main import require_setup_completed
from envmgr.runtime_config import (
    SETUP_SCHEMA_VERSION,
    ConfigError,
    ensure_runtime_layout,
    is_runtime_setup_complete,
    load_runtime_config,
    mark_runtime_setup_complete,
    resolve_inventory_reference,
)
from envmgr.services.assets import resolve_runtime_assets
from envmgr.services.runtime import (
    build_ansible_runtime_env,
    popen_runtime_subprocess,
    run_runtime_subprocess,
)


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
        marker_contents = runtime_paths.setup_marker_file.read_text(encoding="utf-8")
        if f"schema_version = {SETUP_SCHEMA_VERSION}" not in marker_contents:
            raise AssertionError(
                "expected setup marker to persist the setup schema version"
            )
        if 'completed_at = "' not in marker_contents:
            raise AssertionError(
                "expected setup marker to persist the completion timestamp"
            )


def check_setup_uses_shared_runtime_output() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        captured_output = io.StringIO()

        with (
            patch("sys.stdout", new=captured_output),
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            patch(
                "envmgr.commands.setup.run_runtime_subprocess",
                return_value=subprocess.CompletedProcess(
                    ["ansible-galaxy", "--version"],
                    0,
                ),
            ),
        ):
            run_setup()

        runtime_paths = ensure_runtime_layout(envmgr_home)
        output = captured_output.getvalue()
        expected_fragments = (
            "Envmgr Setup",
            "Info: Initializing ~/.envmgr...",
            f"Runtime config: {runtime_paths.config_file}",
            f"Ansible log: {runtime_paths.ansible_log_file}",
            f"Galaxy roles cache: {runtime_paths.galaxy_roles_dir}",
            f"Galaxy collections cache: {runtime_paths.galaxy_collections_dir}",
            "Info: Installing Ansible roles and collections...",
            "Success: Ansible roles and collections installed successfully.",
            "Success: Setup completed successfully.",
        )
        if any(fragment not in output for fragment in expected_fragments):
            raise AssertionError(
                "expected setup to use the shared heading, summary, and status output"
            )


def check_setup_uses_resolved_runtime_assets() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = ensure_runtime_layout(envmgr_home)
        expected_requirements = str(repo_root / "requirements.yaml")
        original_cwd = Path.cwd()

        try:
            os.chdir(temp_dir)
            with (
                patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
                patch(
                    "envmgr.commands.setup.run_runtime_subprocess",
                    return_value=subprocess.CompletedProcess(
                        ["ansible-galaxy", "--version"],
                        0,
                    ),
                ) as mock_run_runtime_subprocess,
            ):
                run_setup()
        finally:
            os.chdir(original_cwd)

        if mock_run_runtime_subprocess.call_count != 2:
            raise AssertionError("expected setup to install both roles and collections")

        for call in mock_run_runtime_subprocess.call_args_list:
            command = call.args[0]
            if command[command.index("-r") + 1] != expected_requirements:
                raise AssertionError(
                    "expected setup to pass the resolved requirements file path"
                )
            if call.kwargs.get("runtime_paths") != runtime_paths:
                raise AssertionError(
                    "expected setup to install against the resolved runtime paths"
                )
            runtime_assets = call.kwargs.get("assets")
            if runtime_assets is None:
                raise AssertionError(
                    "expected setup to reuse shared runtime assets for subprocess env"
                )
            if str(runtime_assets.requirements_file) != expected_requirements:
                raise AssertionError(
                    "expected setup to pass runtime assets resolved outside the cwd"
                )


def check_unbootstrapped_runtime_surfaces_setup_guidance() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        ensure_runtime_layout(envmgr_home)
        captured_stderr = io.StringIO()
        capturing_console = Console(
            file=captured_stderr,
            force_terminal=False,
            color_system=None,
            stderr=True,
        )

        with patch("envmgr.commands.shared.error_console", capturing_console):
            try:
                require_setup_completed("ping", envmgr_home=envmgr_home)
            except typer.Exit as error:
                if error.exit_code != 1:
                    raise AssertionError(
                        "expected unbootstrapped runtime to exit with code 1"
                    ) from error
            else:
                raise AssertionError(
                    "expected unbootstrapped runtime to require setup guidance"
                )

        if f"`{SETUP_COMMAND}`" not in captured_stderr.getvalue():
            raise AssertionError(
                f"expected stderr setup guidance to mention `{SETUP_COMMAND}`"
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
            if "inventory alias 'inventory/default.yaml' is not defined" not in message:
                raise AssertionError(
                    "expected unknown inventory inputs to be rejected as aliases"
                ) from error
            return

        raise AssertionError("expected unknown inventory aliases to raise ConfigError")


def check_runtime_assets_resolve_outside_repo_cwd() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        shadow_playbooks_dir = Path(temp_dir) / "playbooks"
        shadow_playbooks_dir.mkdir()
        shadow_workstation_playbook = shadow_playbooks_dir / "workstation.yml"
        shadow_workstation_playbook.write_text(
            "- hosts: localhost\n  gather_facts: false\n  tasks: []\n",
            encoding="utf-8",
        )
        original_cwd = Path.cwd()
        os.chdir(temp_dir)
        try:
            assets = resolve_runtime_assets(envmgr_home=envmgr_home)
            resolved_shadow_playbook = assets.resolve_playbook(
                "playbooks/workstation.yml"
            )
            resolved_missing_node_playbook = assets.resolve_playbook(
                "playbooks/node.yml"
            )
        finally:
            os.chdir(original_cwd)

        if assets.root != repo_root:
            raise AssertionError(
                "expected runtime assets to resolve from the repo root"
            )
        if assets.resolve_playbook("workstation") != (
            repo_root / "playbooks" / "workstation.yml"
        ):
            raise AssertionError(
                "expected logical scenario names to resolve to absolute playbook paths"
            )
        if resolved_shadow_playbook != shadow_workstation_playbook.resolve():
            raise AssertionError(
                "expected path-like playbook references to resolve from the caller cwd first"
            )
        missing_node_playbook = (Path(temp_dir) / "playbooks" / "node.yml").resolve()
        if resolved_missing_node_playbook != missing_node_playbook:
            raise AssertionError(
                "expected missing path-like playbook references to avoid packaged fallback"
            )
        if assets.roles_dir != (repo_root / "roles"):
            raise AssertionError(
                "expected runtime assets to expose an absolute roles dir"
            )
        if assets.ansible_config_file != (repo_root / "ansible.cfg"):
            raise AssertionError(
                "expected runtime assets to expose an absolute ansible.cfg path"
            )
        if assets.requirements_file != (repo_root / "requirements.yaml"):
            raise AssertionError(
                "expected runtime assets to expose an absolute requirements file path"
            )
        if assets.vars_dir != (repo_root / "vars"):
            raise AssertionError(
                "expected runtime assets to expose an absolute vars dir"
            )
        if assets.scratch_dir != (envmgr_home / "cache" / "tmp"):
            raise AssertionError(
                "expected runtime assets scratch dir to follow the runtime home"
            )


def check_runtime_assets_resolve_from_packaged_assets_outside_repo_cwd() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        envmgr_home = workspace / ".envmgr"
        package_dir = workspace / "site-packages" / "envmgr"
        packaged_assets_root = package_dir / "_assets"
        packaged_playbooks_dir = packaged_assets_root / "playbooks"
        packaged_roles_dir = packaged_assets_root / "roles"
        packaged_vars_dir = packaged_assets_root / "vars"
        packaged_workstation_playbook = packaged_playbooks_dir / "workstation.yml"

        package_dir.mkdir(parents=True)
        packaged_playbooks_dir.mkdir(parents=True)
        packaged_roles_dir.mkdir()
        packaged_vars_dir.mkdir()
        (packaged_assets_root / "ansible.cfg").write_text(
            "[defaults]\n",
            encoding="utf-8",
        )
        (packaged_assets_root / "requirements.yaml").write_text(
            "---\nroles: []\ncollections: []\n",
            encoding="utf-8",
        )
        packaged_workstation_playbook.write_text(
            "- hosts: localhost\n  gather_facts: false\n  tasks: []\n",
            encoding="utf-8",
        )

        outside_cwd = workspace / "outside-cwd"
        outside_cwd.mkdir()
        original_cwd = Path.cwd()
        os.chdir(outside_cwd)
        try:
            assets = resolve_runtime_assets(
                envmgr_home=envmgr_home,
                package_dir=package_dir,
            )
            resolved_workstation_playbook = assets.resolve_playbook("workstation")
            resolved_repo_relative_playbook = assets.resolve_playbook(
                "playbooks/workstation.yml"
            )
        finally:
            os.chdir(original_cwd)

        if assets.root != packaged_assets_root.resolve():
            raise AssertionError(
                "expected runtime assets to resolve from the packaged _assets dir"
            )
        if assets.root == repo_root:
            raise AssertionError(
                "expected packaged runtime assets to avoid the live repo root"
            )
        if resolved_workstation_playbook != packaged_workstation_playbook:
            raise AssertionError(
                "expected scenario playbooks to resolve from packaged assets"
            )
        expected_caller_playbook = (
            outside_cwd / "playbooks" / "workstation.yml"
        ).resolve()
        if resolved_repo_relative_playbook != expected_caller_playbook:
            raise AssertionError(
                "expected path-like playbook references to avoid packaged fallback"
            )
        if assets.roles_dir != packaged_roles_dir:
            raise AssertionError(
                "expected packaged runtime assets to expose the packaged roles dir"
            )
        if assets.ansible_config_file != (packaged_assets_root / "ansible.cfg"):
            raise AssertionError(
                "expected packaged runtime assets to expose packaged ansible.cfg"
            )
        if assets.requirements_file != (packaged_assets_root / "requirements.yaml"):
            raise AssertionError(
                "expected packaged runtime assets to expose packaged requirements"
            )
        if assets.vars_dir != packaged_vars_dir:
            raise AssertionError(
                "expected packaged runtime assets to expose the packaged vars dir"
            )
        if assets.scratch_dir != (envmgr_home / "cache" / "tmp"):
            raise AssertionError(
                "expected packaged runtime assets scratch dir to follow the runtime home"
            )


def check_runtime_env_uses_runtime_paths_only() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
        tool_bin = (Path(temp_dir) / "tool-env" / "bin").resolve()
        inherited_bin = (Path(temp_dir) / "ambient-bin").resolve()
        extra_bin = (Path(temp_dir) / "fallback-bin").resolve()
        with (
            patch.dict(
                os.environ,
                {
                    "ANSIBLE_ROLES_PATH": str(
                        Path(temp_dir) / "legacy-roles" / ".ansible" / "roles"
                    ),
                    "ANSIBLE_COLLECTIONS_PATH": str(
                        Path(temp_dir)
                        / "legacy-collections"
                        / ".ansible"
                        / "collections"
                    ),
                    "PATH": os.pathsep.join(
                        [str(inherited_bin), str(tool_bin), str(extra_bin)]
                    ),
                },
                clear=False,
            ),
            patch(
                "envmgr.services.runtime.sysconfig.get_path",
                return_value=str(tool_bin),
            ),
            patch("envmgr.services.runtime.sys.executable", str(tool_bin / "python3")),
        ):
            env = build_ansible_runtime_env(runtime_paths)

        if ".ansible/roles" in env["ANSIBLE_ROLES_PATH"]:
            raise AssertionError(
                "expected runtime roles path to exclude .ansible/roles"
            )
        if ".ansible/collections" in env["ANSIBLE_COLLECTIONS_PATH"]:
            raise AssertionError(
                "expected runtime collections path to exclude .ansible/collections"
            )
        expected_ansible_config = Path(__file__).resolve().parents[2] / "ansible.cfg"
        if env["ANSIBLE_CONFIG"] != str(expected_ansible_config):
            raise AssertionError(
                "expected runtime ansible config to resolve independently of the cwd"
            )
        if env["ANSIBLE_LOG_PATH"] != str(runtime_paths.ansible_log_file):
            raise AssertionError("expected ansible log path to point to ~/.envmgr")
        if env["PATH"].split(os.pathsep) != [
            str(tool_bin),
            str(inherited_bin),
            str(extra_bin),
        ]:
            raise AssertionError(
                "expected runtime PATH to prepend the current tool bin once"
            )


def check_runtime_subprocess_helpers_use_runtime_paths() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
        tool_bin = (Path(temp_dir) / "tool-env" / "bin").resolve()
        inherited_bin = (Path(temp_dir) / "ambient-bin").resolve()
        extra_bin = (Path(temp_dir) / "child-bin").resolve()

        with (
            patch.dict(
                os.environ,
                {"PATH": str(inherited_bin)},
                clear=False,
            ),
            patch(
                "envmgr.services.runtime.sysconfig.get_path",
                return_value=str(tool_bin),
            ),
            patch("envmgr.services.runtime.sys.executable", str(tool_bin / "python3")),
            patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess(
                    ["ansible-playbook", "--version"],
                    0,
                ),
            ) as mock_run,
        ):
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
        if run_env.get("PATH", "").split(os.pathsep) != [
            str(tool_bin),
            str(inherited_bin),
        ]:
            raise AssertionError(
                "expected run helper to prepend the current tool bin to PATH"
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
            raise AssertionError("expected run helper to persist the ansible log path")
        if run_payload["completed_at"] is None:
            raise AssertionError("expected run helper to persist completion timestamps")

        mock_process = Mock()
        mock_process.pid = 4242
        mock_process.wait.return_value = 0
        mock_process.poll.return_value = None
        mock_process.returncode = 0

        with (
            patch.dict(
                os.environ,
                {"PATH": str(inherited_bin)},
                clear=False,
            ),
            patch(
                "envmgr.services.runtime.sysconfig.get_path",
                return_value=str(tool_bin),
            ),
            patch("envmgr.services.runtime.sys.executable", str(tool_bin / "python3")),
            patch("subprocess.Popen", return_value=mock_process) as mock_popen,
        ):
            process = popen_runtime_subprocess(
                ["ansible-playbook", "--version"],
                runtime_paths=runtime_paths,
                extra_env={
                    "ENVMGR_TEST_FLAG": "popen",
                    "PATH": os.pathsep.join([str(extra_bin), str(inherited_bin)]),
                },
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
        if popen_env.get("PATH", "").split(os.pathsep) != [
            str(tool_bin),
            str(extra_bin),
            str(inherited_bin),
        ]:
            raise AssertionError(
                "expected popen helper to preserve extra PATH entries after the tool bin"
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


def check_package_root_helper_exports_resolve_to_command_modules() -> None:
    expected_exports = {
        "create": ("envmgr.commands.create", "create"),
        "lint": ("envmgr.commands.lint", "lint"),
        "ansible_lint": ("envmgr.commands.ansible_check", "ansible_lint"),
        "typecheck": ("envmgr.commands.typecheck", "typecheck"),
        "validate": ("envmgr.commands.validate", "validate"),
        "smoke_test": ("envmgr.commands.smoke_test", "smoke_test"),
    }
    package = __import__("envmgr", fromlist=list(expected_exports))
    package_all = getattr(package, "__all__", None)
    if not isinstance(package_all, list):
        raise AssertionError("expected envmgr.__all__ to remain a list of exports")

    for export_name, (module_name, attr_name) in expected_exports.items():
        exported = getattr(package, export_name, None)
        target = getattr(importlib.import_module(module_name), attr_name)
        if exported is not target:
            raise AssertionError(
                f"expected envmgr.{export_name} to resolve to {module_name}.{attr_name}"
            )
        if export_name not in package_all:
            raise AssertionError(
                f"expected envmgr.__all__ to keep {export_name!r} available"
            )


def check_envmgr_main_keeps_only_root_command_exports() -> None:
    expected_exports = [
        "app",
        "doctor",
        "history",
        "install",
        "main",
        "ping",
        "require_setup_completed",
        "setup",
    ]
    removed_helper_exports = (
        "create",
        "lint",
        "ansible_lint",
        "typecheck",
        "validate",
        "smoke_test",
    )
    main_module = importlib.import_module("envmgr.main")
    if getattr(main_module, "__all__", None) != expected_exports:
        raise AssertionError(
            "expected envmgr.main.__all__ to describe only the retained "
            "root-command surface"
        )

    for export_name in expected_exports:
        if not hasattr(main_module, export_name):
            raise AssertionError(
                f"expected envmgr.main to keep {export_name!r} available"
            )

    for export_name in removed_helper_exports:
        if hasattr(main_module, export_name):
            raise AssertionError(
                f"expected envmgr.main to stop exposing {export_name!r}"
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
            raise AssertionError("expected recreated runtime inventory to keep alias")
        if resolved_path != runtime_paths.default_inventory_file.resolve():
            raise AssertionError(
                "expected recreated runtime inventory path to match ~/.envmgr"
            )
        if not runtime_paths.default_inventory_file.exists():
            raise AssertionError(
                "expected missing runtime inventory file to be recreated"
            )
