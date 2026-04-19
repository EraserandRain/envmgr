from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from ..catalog import CatalogError, get_available_tags
from ..scaffold import generate_role
from ..services.install import (
    build_execution_playbook,
    read_playbook_role_name,
    read_playbook_role_tags,
    resolve_install_playbook,
)


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
