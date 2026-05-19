from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from ..catalog import (
    CatalogError,
    RoleMetadata,
    build_playbook_tag_index,
    load_playbook_tags,
    load_role_catalog,
)
from ..runtime_config import RuntimeConfig, RuntimePaths
from .assets import resolve_runtime_assets
from .install_tags import is_all_tag_selection

DEFAULT_PLAYBOOKS = [
    "workstation",
    "node",
]


def resolve_default_playbook_path(config: RuntimeConfig) -> str:
    """Resolve the configured default playbook name into a packaged scenario path."""
    assets = resolve_runtime_assets(runtime_paths=config.paths)
    return str(assets.resolve_playbook(config.default_playbook))


def get_existing_default_playbooks() -> list[str]:
    """Return built-in scenario playbooks that exist in the packaged assets."""
    assets = resolve_runtime_assets()
    return [
        str(assets.resolve_playbook(playbook))
        for playbook in DEFAULT_PLAYBOOKS
        if playbook in assets.scenario_playbooks
    ]


def resolve_selected_role_metadata(
    selected_tags: list[str],
    roles_dir: str | Path | None = None,
) -> dict[str, RoleMetadata]:
    """Resolve selected tags into a role closure that includes declared dependencies."""
    catalog = [
        metadata for metadata in load_role_catalog(roles_dir) if metadata.enabled
    ]
    metadata_by_name = {metadata.name: metadata for metadata in catalog}
    resolved_metadata: dict[str, RoleMetadata] = {}

    def add_metadata(metadata: RoleMetadata) -> None:
        if metadata.name in resolved_metadata:
            return
        resolved_metadata[metadata.name] = metadata
        for dependency_name in metadata.depends_on:
            dependency = metadata_by_name.get(dependency_name)
            if dependency is None:
                raise CatalogError(
                    f"role '{metadata.name}' depends on unknown role '{dependency_name}'"
                )
            add_metadata(dependency)

    for selected_tag in selected_tags:
        matched_metadata = [
            metadata
            for metadata in catalog
            if selected_tag in metadata.tags or selected_tag in metadata.task_tags
        ]
        if not matched_metadata:
            raise CatalogError(
                f"selected tag '{selected_tag}' does not map to a catalog role"
            )

        for metadata in matched_metadata:
            add_metadata(metadata)

    return resolved_metadata


def read_playbook_role_name(role_entry: Any, playbook_path: Path) -> str:
    """Read a role name from a playbook role entry."""
    if isinstance(role_entry, str):
        return role_entry

    if isinstance(role_entry, dict):
        role_name = role_entry.get("role")
        if isinstance(role_name, str) and role_name.strip():
            return role_name

    raise CatalogError(f"{playbook_path} contains an invalid role entry")


def read_playbook_role_tags(
    role_entry: dict[str, Any], playbook_path: Path
) -> list[str]:
    """Normalize a playbook role tag list."""
    value = role_entry.get("tags")
    role_name = role_entry.get("role", "<unknown>")
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise CatalogError(
        f"{playbook_path} role '{role_name}' field 'tags' must be a string or list of strings"
    )


def resolve_playbook_file_reference(value: Any, *, playbook_path: Path) -> Any:
    """Resolve static playbook file references relative to the source playbook."""
    if isinstance(value, list):
        return [
            resolve_playbook_file_reference(item, playbook_path=playbook_path)
            for item in value
        ]

    if not isinstance(value, str):
        return value

    if value.startswith(("{{", "{%")) or "{{" in value or "{%" in value:
        return value

    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    return str((playbook_path.parent / path).resolve())


def playbook_includes_role(source_playbook: str, role_name: str) -> bool:
    """Return whether the playbook references a specific role."""
    playbook_path = resolve_runtime_assets().resolve_playbook(source_playbook)
    with playbook_path.open(encoding="utf-8") as file:
        playbook_data = yaml.safe_load(file)

    if not isinstance(playbook_data, list):
        raise CatalogError(f"{playbook_path} must contain a YAML list of plays")

    for play in playbook_data:
        if not isinstance(play, dict):
            raise CatalogError(f"{playbook_path} contains an invalid play definition")

        roles = play.get("roles", [])
        if roles is None:
            continue
        if not isinstance(roles, list):
            raise CatalogError(f"{playbook_path} field 'roles' must be a list")

        for role_entry in roles:
            if read_playbook_role_name(role_entry, playbook_path) == role_name:
                return True

    return False


def build_execution_playbook(
    source_playbook: str,
    selected_tags: list[str],
    roles_dir: str | Path | None = None,
    *,
    runtime_paths: RuntimePaths | None = None,
) -> str:
    """Build a minimal temporary playbook for the selected tags."""
    assets = resolve_runtime_assets(runtime_paths=runtime_paths)
    playbook_path = assets.resolve_playbook(source_playbook)
    if not playbook_path.exists():
        raise CatalogError(f"playbook not found: {playbook_path}")

    selected_metadata = resolve_selected_role_metadata(selected_tags, roles_dir)
    selected_tag_set = set(selected_tags)
    required_playbook_roles: dict[str, str] = {}
    roles_requiring_selected_tags: set[str] = set()

    for metadata in selected_metadata.values():
        for playbook_role in metadata.playbook_roles:
            required_playbook_roles[playbook_role] = metadata.name
        if set(metadata.tags).isdisjoint(selected_tag_set):
            roles_requiring_selected_tags.add(metadata.name)

    with playbook_path.open(encoding="utf-8") as file:
        playbook_data = yaml.safe_load(file)

    if not isinstance(playbook_data, list):
        raise CatalogError(f"{playbook_path} must contain a YAML list of plays")

    generated_playbook: list[dict[str, Any]] = []
    selected_tag_list = list(dict.fromkeys(selected_tags))

    for play in playbook_data:
        if not isinstance(play, dict):
            raise CatalogError(f"{playbook_path} contains an invalid play definition")

        roles = play.get("roles", [])
        if roles is None:
            filtered_roles: list[Any] = []
        else:
            if not isinstance(roles, list):
                raise CatalogError(f"{playbook_path} field 'roles' must be a list")

            filtered_roles = []
            for role_entry in roles:
                role_name = read_playbook_role_name(role_entry, playbook_path)
                metadata_name = required_playbook_roles.get(role_name)
                if metadata_name is None:
                    continue

                if isinstance(role_entry, dict):
                    filtered_role_entry: Any = deepcopy(role_entry)
                else:
                    filtered_role_entry = role_entry

                if metadata_name in roles_requiring_selected_tags:
                    if isinstance(filtered_role_entry, str):
                        filtered_role_entry = {
                            "role": filtered_role_entry,
                            "tags": selected_tag_list,
                        }
                    else:
                        existing_tags = read_playbook_role_tags(
                            filtered_role_entry, playbook_path
                        )
                        merged_tags = list(
                            dict.fromkeys(existing_tags + selected_tag_list)
                        )
                        filtered_role_entry["tags"] = merged_tags

                filtered_roles.append(filtered_role_entry)

        filtered_play = deepcopy(play)
        if "vars_files" in filtered_play:
            filtered_play["vars_files"] = resolve_playbook_file_reference(
                filtered_play["vars_files"],
                playbook_path=playbook_path,
            )
        filtered_play["roles"] = filtered_roles
        generated_playbook.append(filtered_play)

    if not any(play.get("roles") for play in generated_playbook):
        raise CatalogError("selected tags did not resolve to any playbook roles")

    assets.scratch_dir.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yml",
        prefix=f".envmgr-{playbook_path.stem}-",
        dir=assets.scratch_dir,
        delete=False,
    )
    try:
        with temp_file:
            yaml.safe_dump(generated_playbook, temp_file, sort_keys=False)
    except Exception:
        Path(temp_file.name).unlink(missing_ok=True)
        raise

    return temp_file.name


def resolve_install_playbook(
    selected_tags: list[str],
    *,
    explicit_playbook: str | None,
) -> str:
    """Resolve a playbook for install operations based on explicit input or tag scope."""
    assets = resolve_runtime_assets()
    if explicit_playbook:
        resolved_playbook = str(assets.resolve_playbook(explicit_playbook))
        if selected_tags and not is_all_tag_selection(selected_tags):
            playbook_tags = load_playbook_tags(resolved_playbook)
            requested_tags = set(selected_tags)
            if not requested_tags.issubset(playbook_tags):
                raise CatalogError(
                    f"selected tags are not valid in {explicit_playbook}; "
                    "choose a matching playbook"
                )
        return resolved_playbook

    if not selected_tags:
        raise CatalogError("no tags selected")

    if is_all_tag_selection(selected_tags):
        raise CatalogError("tag 'all' requires --playbook so the scenario is explicit")

    playbook_paths = get_existing_default_playbooks()
    if not playbook_paths:
        raise CatalogError("no scenario playbooks found under playbooks/")

    playbook_tag_index = build_playbook_tag_index(playbook_paths)
    requested_tags = set(selected_tags)
    matching_playbooks = [
        playbook
        for playbook, playbook_tags in playbook_tag_index.items()
        if requested_tags.issubset(playbook_tags)
    ]

    if len(matching_playbooks) == 1:
        return matching_playbooks[0]

    if not matching_playbooks:
        raise CatalogError(
            "selected tags do not map to a scenario playbook; use --playbook explicitly"
        )

    matching_names = ", ".join(matching_playbooks)
    raise CatalogError(
        f"selected tags are valid in multiple playbooks ({matching_names}); use --playbook explicitly"
    )
