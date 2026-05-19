from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml

from envmgr.catalog import (
    CatalogError,
    get_available_tags,
    load_playbook_tags,
    load_role_catalog,
)
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


def _read_playbook_role_names(playbook_path: Path) -> set[str]:
    with playbook_path.open(encoding="utf-8") as file:
        playbook_data = yaml.safe_load(file)

    if not isinstance(playbook_data, list):
        raise AssertionError(f"expected {playbook_path} to contain a play list")

    role_names: set[str] = set()
    for play in playbook_data:
        if not isinstance(play, dict):
            raise AssertionError(f"expected {playbook_path} plays to be mappings")

        roles = play.get("roles", [])
        if not isinstance(roles, list):
            raise AssertionError(f"expected {playbook_path} roles to be a list")

        for role_entry in roles:
            role_names.add(read_playbook_role_name(role_entry, playbook_path))

    return role_names


def check_builtin_playbooks_match_enabled_role_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    roles_dir = repo_root / "roles"
    built_in_playbooks = {
        "workstation": repo_root / "playbooks" / "workstation.yml",
        "node": repo_root / "playbooks" / "node.yml",
    }
    playbook_roles = {
        scenario: _read_playbook_role_names(playbook_path)
        for scenario, playbook_path in built_in_playbooks.items()
    }

    enabled_metadata = [
        metadata for metadata in load_role_catalog(roles_dir) if metadata.enabled
    ]
    declared_playbook_roles = {
        role_name
        for metadata in enabled_metadata
        for role_name in metadata.playbook_roles
    }
    declared_external_roles = {
        role_name
        for metadata in enabled_metadata
        for role_name in metadata.galaxy_roles
    }
    allowed_playbook_roles = declared_playbook_roles | declared_external_roles

    undeclared_by_playbook = {
        scenario: sorted(role_names - allowed_playbook_roles)
        for scenario, role_names in playbook_roles.items()
        if role_names - allowed_playbook_roles
    }
    if undeclared_by_playbook:
        raise AssertionError(
            "expected built-in playbook roles to be declared by enabled metadata "
            f"or known external Galaxy roles; got {undeclared_by_playbook}"
        )

    missing_by_metadata: dict[str, list[str]] = {}
    for metadata in enabled_metadata:
        for target in metadata.targets:
            if target not in playbook_roles:
                continue
            missing_roles = sorted(
                set(metadata.playbook_roles) - playbook_roles[target]
            )
            if missing_roles:
                missing_by_metadata[f"{metadata.name}:{target}"] = missing_roles

    if missing_by_metadata:
        raise AssertionError(
            "expected enabled role metadata playbook_roles to appear in each target "
            f"built-in playbook; got {missing_by_metadata}"
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
