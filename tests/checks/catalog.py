from __future__ import annotations

import os
import tempfile
from pathlib import Path

from envmgr.catalog import CatalogError, get_available_tags, load_playbook_tags
from envmgr.services.assets import resolve_runtime_assets
from envmgr.services.install import resolve_install_playbook


def check_playbook_resolution() -> None:
    assets = resolve_runtime_assets()
    workstation_playbook = str(assets.resolve_playbook("workstation"))
    node_playbook = str(assets.resolve_playbook("node"))

    if (
        resolve_install_playbook(["zsh"], explicit_playbook=None)
        != workstation_playbook
    ):
        raise AssertionError("expected zsh to resolve to workstation playbook")

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
            relative_workstation_tags = load_playbook_tags("playbooks/workstation.yml")
            logical_workstation_tags = load_playbook_tags("workstation")
            resolved_workstation_playbook = resolve_install_playbook(
                ["zsh"],
                explicit_playbook=None,
            )
        finally:
            os.chdir(original_cwd)

    if role_tags != expected_role_tags or task_tags != expected_task_tags:
        raise AssertionError(
            "expected catalog defaults to resolve first-party roles outside the repo cwd"
        )
    if relative_workstation_tags != expected_workstation_tags:
        raise AssertionError(
            "expected repo-relative playbook paths to resolve outside the repo cwd"
        )
    if logical_workstation_tags != expected_workstation_tags:
        raise AssertionError(
            "expected logical scenario names to resolve outside the repo cwd"
        )
    if resolved_workstation_playbook != expected_workstation_playbook:
        raise AssertionError(
            "expected tag-based playbook resolution to keep working outside the repo cwd"
        )
