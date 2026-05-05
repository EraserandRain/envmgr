from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from envmgr.catalog import CatalogError, get_available_tags, load_playbook_tags
from envmgr.services.assets import resolve_runtime_assets
from envmgr.services.install import (
    build_execution_playbook,
    read_playbook_role_name,
    read_playbook_role_tags,
    resolve_install_playbook,
)


def check_playbook_resolution() -> None:
    assets = resolve_runtime_assets()
    workstation_playbook = str(assets.resolve_playbook("workstation"))
    node_playbook = str(assets.resolve_playbook("node"))

    if (
        resolve_install_playbook(["zsh"], explicit_playbook=None)
        != workstation_playbook
    ):
        raise AssertionError("expected zsh to resolve to workstation playbook")

    if (
        resolve_install_playbook(["github_cli"], explicit_playbook=None)
        != workstation_playbook
    ):
        raise AssertionError("expected github_cli to resolve to workstation playbook")

    if resolve_install_playbook(["kubeadm"], explicit_playbook=None) != node_playbook:
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
        != workstation_playbook
    ):
        raise AssertionError("expected init to stay valid on workstation playbook")

    try:
        resolve_install_playbook(["init"], explicit_playbook="playbooks/node.yml")
    except CatalogError:
        pass
    else:
        raise AssertionError("expected init to be rejected on node playbook")

    try:
        resolve_install_playbook(["init"], explicit_playbook="workstation.yml")
    except CatalogError:
        return

    raise AssertionError(
        "expected explicit path-like playbook references to stay path-based without scenario fallback"
    )


def check_github_cli_task_tag_catalog_and_execution_playbook() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _role_tags, task_tags = get_available_tags(repo_root / "roles")
    if "github_cli" not in task_tags:
        raise AssertionError("expected github_cli to be exposed as a task tag")

    generated_playbook = build_execution_playbook(
        "workstation",
        ["github_cli"],
        repo_root / "roles",
    )
    try:
        with Path(generated_playbook).open(encoding="utf-8") as file:
            playbook_data = yaml.safe_load(file)

        if not isinstance(playbook_data, list) or not playbook_data:
            raise AssertionError(
                "expected generated github_cli playbook to contain a play"
            )

        roles = playbook_data[0].get("roles", [])
        if not isinstance(roles, list):
            raise AssertionError("expected generated playbook roles to be a list")

        role_names = [
            read_playbook_role_name(role_entry, Path(generated_playbook))
            for role_entry in roles
        ]
        if role_names != ["init_core", "init"]:
            raise AssertionError(
                "expected github_cli execution roles to be "
                f"['init_core', 'init'], got {role_names}"
            )

        init_entry = roles[1]
        if not isinstance(init_entry, dict):
            raise AssertionError("expected init role entry to include tags")
        if "github_cli" not in read_playbook_role_tags(
            init_entry,
            Path(generated_playbook),
        ):
            raise AssertionError(
                "expected generated init role to preserve the github_cli tag"
            )
    finally:
        Path(generated_playbook).unlink(missing_ok=True)


def check_catalog_defaults_resolve_outside_repo_cwd() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    assets = resolve_runtime_assets()
    expected_workstation_playbook = str(assets.resolve_playbook("workstation"))
    expected_role_tags, expected_task_tags = get_available_tags(repo_root / "roles")
    expected_workstation_tags = load_playbook_tags(
        repo_root / "playbooks" / "workstation.yml",
        repo_root / "roles",
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        original_cwd = Path.cwd()
        os.chdir(temp_dir)
        try:
            role_tags, task_tags = get_available_tags()
            try:
                load_playbook_tags("playbooks/workstation.yml")
            except CatalogError:
                relative_workstation_tags_rejected = True
            else:
                relative_workstation_tags_rejected = False
            logical_workstation_tags = load_playbook_tags("workstation")
            resolved_workstation_playbook = resolve_install_playbook(
                ["zsh"],
                explicit_playbook=None,
            )
            explicit_workstation_playbook = resolve_install_playbook(
                ["init"],
                explicit_playbook="workstation",
            )
            try:
                resolve_install_playbook(
                    ["init"],
                    explicit_playbook="playbooks/workstation.yml",
                )
            except CatalogError:
                explicit_relative_playbook_rejected = True
            else:
                explicit_relative_playbook_rejected = False
        finally:
            os.chdir(original_cwd)

    if role_tags != expected_role_tags or task_tags != expected_task_tags:
        raise AssertionError(
            "expected catalog defaults to resolve first-party roles outside the repo cwd"
        )
    if not relative_workstation_tags_rejected:
        raise AssertionError(
            "expected missing path-like playbook references to avoid packaged fallback"
        )
    if logical_workstation_tags != expected_workstation_tags:
        raise AssertionError(
            "expected logical scenario names to resolve outside the repo cwd"
        )
    if resolved_workstation_playbook != expected_workstation_playbook:
        raise AssertionError(
            "expected tag-based playbook resolution to keep working outside the repo cwd"
        )
    if explicit_workstation_playbook != expected_workstation_playbook:
        raise AssertionError(
            "expected explicit scenario playbooks to resolve outside the repo cwd"
        )
    if not explicit_relative_playbook_rejected:
        raise AssertionError(
            "expected explicit path-like playbooks to avoid packaged fallback"
        )
