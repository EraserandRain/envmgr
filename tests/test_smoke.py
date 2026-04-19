from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import yaml

from scripts.catalog import CatalogError, get_available_tags
from scripts.command_text import SETUP_COMMAND
from scripts.commands.install import resolve_ai_tools_install_options
from scripts.main import (
    doctor,
    history,
    install,
    main,
    require_setup_completed,
    setup,
)
from scripts.runtime_config import (
    SETUP_SCHEMA_VERSION,
    ConfigError,
    ensure_runtime_layout,
    get_runtime_paths,
    is_runtime_setup_complete,
    load_runtime_config,
    mark_runtime_setup_complete,
    resolve_inventory_reference,
)
from scripts.scaffold import generate_role
from scripts.services.doctor import (
    DOCTOR_FAIL,
    DOCTOR_OK,
    build_doctor_report,
)
from scripts.services.install import (
    AiToolsInstallDefaults,
    InstallPlan,
    build_execution_playbook,
    read_playbook_role_name,
    read_playbook_role_tags,
    resolve_install_playbook,
)
from scripts.services.runtime import (
    RUNTIME_RUN_RECORD_SCHEMA_VERSION,
    build_ansible_runtime_env,
    popen_runtime_subprocess,
    run_runtime_subprocess,
    write_runtime_run_record,
)

SmokeCheck = tuple[str, Callable[[], None]]


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
        metadata = yaml.safe_load(metadata_contents)
        if metadata["name"] != "smoke-role":
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
            raise AssertionError("expected generated codex playbook to contain a play")
        if not isinstance(rtk_data, list) or not rtk_data:
            raise AssertionError("expected generated rtk playbook to contain a play")
        if not isinstance(init_data, list) or not init_data:
            raise AssertionError("expected generated init playbook to contain a play")
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
        marker_contents = runtime_paths.setup_marker_file.read_text(encoding="utf-8")
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
                    "expected unbootstrapped runtime to require setup guidance"
                )

        if f"`{SETUP_COMMAND}`" not in captured_output.getvalue():
            raise AssertionError(
                f"expected setup guidance to mention `{SETUP_COMMAND}`"
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
        raise AssertionError("expected Codex Context7 method override to be honored")

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


def check_dispatcher_routes_install_subcommand() -> None:
    captured_output = io.StringIO()

    with (
        patch("sys.stdout", new=captured_output),
        patch(
            "scripts.commands.install.load_available_tags",
            return_value=(["zsh"], ["codex"]),
        ),
    ):
        main(["install", "-l"])

    output = captured_output.getvalue()
    if "Envmgr available tags:" not in output:
        raise AssertionError("expected dispatcher to route to the install subcommand")
    if "  - zsh" not in output:
        raise AssertionError("expected dispatcher to print install role tags")
    if "  - codex" not in output:
        raise AssertionError("expected dispatcher to print install task tags")


def check_dispatcher_rejects_dev_only_subcommands() -> None:
    captured_error = io.StringIO()

    with patch("sys.stderr", new=captured_error):
        try:
            main(["validate"])
        except SystemExit as error:
            if error.code != 2:
                raise AssertionError(
                    "expected dispatcher to reject dev-only subcommands with exit code 2"
                ) from error
        else:
            raise AssertionError("expected dispatcher to reject dev-only subcommands")

    if "invalid choice" not in captured_error.getvalue():
        raise AssertionError("expected dispatcher rejection to come from argparse")


def check_install_rejects_unknown_tags_with_exit_code() -> None:
    captured_output = io.StringIO()

    with (
        patch("sys.stdout", new=captured_output),
        patch(
            "scripts.commands.install.load_available_tags",
            return_value=(["zsh"], ["codex"]),
        ),
    ):
        try:
            install(["does-not-exist"])
        except SystemExit as error:
            if error.code != 1:
                raise AssertionError(
                    "expected install to exit with code 1 for unknown tags"
                ) from error
        else:
            raise AssertionError("expected install to reject unknown tags")

    output = captured_output.getvalue()
    if "unknown tags: does-not-exist" not in output.lower():
        raise AssertionError("expected install to report the unknown tag")
    if "Use -l or --list-tags to see all available tags" not in output:
        raise AssertionError("expected install to suggest listing available tags")


def check_install_rejects_all_plus_other_tags() -> None:
    captured_output = io.StringIO()

    with patch("sys.stdout", new=captured_output):
        try:
            install(["all", "zsh"])
        except SystemExit as error:
            if error.code != 1:
                raise AssertionError(
                    "expected install to exit with code 1 for mixed all-tag selections"
                ) from error
        else:
            raise AssertionError("expected install to reject mixed all-tag selections")

    if "tag 'all' cannot be combined with other tags" not in captured_output.getvalue():
        raise AssertionError(
            "expected install to explain that `all` cannot be mixed with other tags"
        )


def check_install_interrupt_exits_cleanly() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
        execution_playbook_path = Path(temp_dir) / "execution.yml"
        execution_playbook_path.write_text("---\n", encoding="utf-8")
        install_plan = InstallPlan(
            selected_tags=["zsh"],
            role_tags=["zsh"],
            task_tags=[],
            source_playbook_path="playbooks/workstation.yml",
            execution_playbook_path=str(execution_playbook_path),
            uses_temporary_execution_playbook=True,
            inventory_path=runtime_paths.default_inventory_file,
            inventory_label="default",
            runtime_paths=runtime_paths,
            default_ask_vault_pass=False,
            ai_tools_defaults=AiToolsInstallDefaults(
                applicable=False,
                manage_claude_code=False,
                manage_codex=False,
                manage_rtk=False,
            ),
        )

        with (
            patch("scripts.commands.install.require_setup_completed"),
            patch(
                "scripts.commands.install.build_install_plan", return_value=install_plan
            ),
            patch(
                "scripts.commands.install.resolve_ai_tools_install_options",
                return_value=None,
            ),
            patch(
                "scripts.commands.install.popen_runtime_subprocess",
                side_effect=KeyboardInterrupt,
            ),
        ):
            try:
                install(["zsh", "--ask-vault-pass"])
            except SystemExit as error:
                if error.code != 130:
                    raise AssertionError(
                        "expected install to exit with code 130 on Ctrl+C"
                    ) from error
            else:
                raise AssertionError("expected install to exit on Ctrl+C")

        if execution_playbook_path.exists():
            raise AssertionError(
                "expected install to clean up temporary execution playbooks on Ctrl+C"
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
            raise AssertionError("expected run helper to persist the ansible log path")
        if run_payload["completed_at"] is None:
            raise AssertionError("expected run helper to persist completion timestamps")

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

        def fake_run(
            command: list[str],
            *,
            env: dict[str, str] | None = None,
            **_kwargs: Any,
        ) -> subprocess.CompletedProcess[Any]:
            return subprocess.CompletedProcess(command, 0)

        with (
            patch("subprocess.run", side_effect=fake_run),
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
                raise AssertionError(f"expected node playbook to target {host_name}")

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


SMOKE_TEST_CHECKS: tuple[SmokeCheck, ...] = (
    ("metadata catalog", check_metadata_catalog),
    ("role scaffold", check_scaffold_generation),
    ("playbook resolution", check_playbook_resolution),
    ("execution playbook generation", check_execution_playbook_generation),
    ("runtime config bootstrap", check_runtime_config_bootstrap),
    ("setup marker is written after setup", check_setup_marker_is_written_after_setup),
    (
        "unbootstrapped runtime surfaces setup guidance",
        check_unbootstrapped_runtime_surfaces_setup_guidance,
    ),
    ("outdated setup stamp requires setup", check_outdated_setup_stamp_requires_setup),
    (
        "AI tools install options resolve correctly",
        check_ai_tools_install_option_resolution,
    ),
    ("AI tools setup wizard flow", check_ai_tools_setup_wizard_flow),
    (
        "dispatcher routes install subcommands",
        check_dispatcher_routes_install_subcommand,
    ),
    (
        "dispatcher rejects dev-only subcommands",
        check_dispatcher_rejects_dev_only_subcommands,
    ),
    (
        "install rejects unknown tags with exit code 1",
        check_install_rejects_unknown_tags_with_exit_code,
    ),
    (
        "install rejects mixed all-tag selections",
        check_install_rejects_all_plus_other_tags,
    ),
    ("install exits cleanly on Ctrl+C", check_install_interrupt_exits_cleanly),
    (
        "unknown inventory aliases are rejected",
        check_unknown_inventory_alias_is_rejected,
    ),
    (
        "runtime env uses ~/.envmgr paths only",
        check_runtime_env_uses_runtime_paths_only,
    ),
    (
        "runtime subprocess helpers use ~/.envmgr paths",
        check_runtime_subprocess_helpers_use_runtime_paths,
    ),
    ("setup logs ansible-galaxy runtime runs", check_setup_logs_ansible_galaxy_runs),
    ("history renders readable text output", check_history_text_output),
    ("history emits json output", check_history_json_output),
    (
        "inventory aliases stay under ~/.envmgr/inventory",
        check_inventory_aliases_stay_under_runtime_inventory_dir,
    ),
    ("invalid TOML surfaces config error", check_invalid_toml_surfaces_config_error),
    (
        "missing runtime inventory file is recreated",
        check_missing_runtime_inventory_file_is_recreated,
    ),
    ("multi-node inventory topology", check_multi_node_inventory_topology),
    (
        "doctor detects an unbootstrapped runtime",
        check_doctor_report_detects_unbootstrapped_runtime,
    ),
    (
        "doctor passes a bootstrapped runtime",
        check_doctor_report_passes_bootstrapped_runtime,
    ),
    (
        "doctor ignores non-default inventory aliases",
        check_doctor_ignores_non_default_inventory_aliases,
    ),
    ("doctor renders readable text output", check_doctor_text_output),
    ("doctor emits json output", check_doctor_json_output),
)


def _slugify_smoke_test_name(step_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", step_name.lower()).strip("_")
    return slug or "smoke_test"


class SmokeTests(unittest.TestCase):
    """Repository smoke tests runnable via `python -m unittest tests.test_smoke`."""

    maxDiff = None


SMOKE_TEST_METHODS: tuple[tuple[str, str], ...] = tuple(
    (
        step_name,
        f"test_{index:02d}_{_slugify_smoke_test_name(step_name)}",
    )
    for index, (step_name, _check) in enumerate(SMOKE_TEST_CHECKS, start=1)
)


for (step_name, check), (_registered_name, method_name) in zip(
    SMOKE_TEST_CHECKS,
    SMOKE_TEST_METHODS,
    strict=True,
):

    def _make_test(
        current_check: Callable[[], None],
        current_step_name: str,
        current_method_name: str,
    ) -> Callable[[SmokeTests], None]:
        def test(self: SmokeTests) -> None:
            current_check()

        test.__name__ = current_method_name
        test.__doc__ = current_step_name
        return test

    setattr(SmokeTests, method_name, _make_test(check, step_name, method_name))


def build_smoke_test_suite() -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for _step_name, method_name in SMOKE_TEST_METHODS:
        suite.addTest(SmokeTests(method_name))
    return suite


def iter_smoke_tests() -> tuple[tuple[str, unittest.TestCase], ...]:
    return tuple(
        (step_name, SmokeTests(method_name))
        for step_name, method_name in SMOKE_TEST_METHODS
    )


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_smoke_test_suite()
