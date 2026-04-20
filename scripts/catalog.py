from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .services.assets import resolve_runtime_assets


class CatalogError(ValueError):
    """Raised when role metadata is missing or invalid."""


@dataclass(frozen=True)
class RoleMetadata:
    name: str
    description: str
    enabled: bool
    targets: list[str]
    tags: list[str]
    depends_on: list[str]
    task_tags: list[str]
    vars_files: list[str]
    playbook_roles: list[str]
    galaxy_roles: list[str]
    collections: list[str]


def _require_mapping(data: Any, metadata_path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise CatalogError(f"{metadata_path} must contain a YAML mapping")
    return data


def _require_string(value: Any, field_name: str, metadata_path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(
            f"{metadata_path} field '{field_name}' must be a non-empty string"
        )
    return value


def _read_string_list(
    data: dict[str, Any],
    field_name: str,
    metadata_path: Path,
    *,
    default: list[str] | None = None,
) -> list[str]:
    value = data.get(field_name, default if default is not None else [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CatalogError(
            f"{metadata_path} field '{field_name}' must be a list of strings"
        )
    return value


def load_role_metadata(metadata_path: str | Path) -> RoleMetadata:
    path = Path(metadata_path)
    with path.open(encoding="utf-8") as file:
        data = _require_mapping(yaml.safe_load(file), path)

    name = _require_string(data.get("name"), "name", path)
    description = data.get("description", "")
    if not isinstance(description, str):
        raise CatalogError(f"{path} field 'description' must be a string")

    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise CatalogError(f"{path} field 'enabled' must be a boolean")

    return RoleMetadata(
        name=name,
        description=description,
        enabled=enabled,
        targets=_read_string_list(data, "targets", path),
        tags=_read_string_list(data, "tags", path),
        depends_on=_read_string_list(data, "depends_on", path),
        task_tags=_read_string_list(data, "task_tags", path),
        vars_files=_read_string_list(data, "vars_files", path),
        playbook_roles=_read_string_list(data, "playbook_roles", path, default=[name]),
        galaxy_roles=_read_string_list(data, "galaxy_roles", path),
        collections=_read_string_list(data, "collections", path),
    )


def resolve_catalog_roles_dir(
    roles_dir: str | Path | None = None,
) -> Path:
    assets = resolve_runtime_assets()
    if roles_dir is None:
        return assets.roles_dir
    return assets.resolve_repo_path(roles_dir)


def resolve_catalog_playbook_path(playbook_path: str | Path) -> Path:
    assets = resolve_runtime_assets()
    return assets.resolve_playbook(playbook_path)


def load_role_catalog(roles_dir: str | Path | None = None) -> list[RoleMetadata]:
    catalog: list[RoleMetadata] = []
    roles_path = resolve_catalog_roles_dir(roles_dir)

    if not roles_path.exists():
        raise CatalogError(f"roles directory not found: {roles_path}")

    for role_dir in sorted(path for path in roles_path.iterdir() if path.is_dir()):
        metadata_path = role_dir / "meta" / "envmgr.yml"
        if metadata_path.exists():
            catalog.append(load_role_metadata(metadata_path))

    return catalog


def get_available_tags(
    roles_dir: str | Path | None = None,
) -> tuple[list[str], list[str]]:
    role_tags: set[str] = set()
    task_tags: set[str] = set()

    for metadata in load_role_catalog(roles_dir):
        if not metadata.enabled:
            continue
        role_tags.update(metadata.tags)
        task_tags.update(metadata.task_tags)

    return sorted(role_tags), sorted(task_tags)


def _read_playbook_tag_list(
    value: Any,
    playbook_path: Path,
    role_name: str,
) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise CatalogError(
        f"{playbook_path} role '{role_name}' field 'tags' must be a string or list of strings"
    )


def load_playbook_tags(
    playbook_path: str | Path,
    roles_dir: str | Path | None = None,
) -> set[str]:
    path = resolve_catalog_playbook_path(playbook_path)
    if not path.exists():
        raise CatalogError(f"playbook not found: {path}")

    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, list):
        raise CatalogError(f"{path} must contain a YAML list of plays")

    role_task_tags: dict[str, set[str]] = {}
    for metadata in load_role_catalog(roles_dir):
        if not metadata.enabled:
            continue
        for role_name in metadata.playbook_roles:
            role_task_tags.setdefault(role_name, set()).update(metadata.task_tags)

    playbook_tags: set[str] = set()

    for play in data:
        if not isinstance(play, dict):
            raise CatalogError(f"{path} contains an invalid play definition")

        roles = play.get("roles", [])
        if roles is None:
            continue
        if not isinstance(roles, list):
            raise CatalogError(f"{path} field 'roles' must be a list")

        for role_entry in roles:
            if isinstance(role_entry, str):
                role_name = role_entry
                assigned_tags: list[str] = []
            elif isinstance(role_entry, dict):
                role_name_value = role_entry.get("role")
                if not isinstance(role_name_value, str) or not role_name_value.strip():
                    raise CatalogError(
                        f"{path} contains a role entry without a valid 'role' field"
                    )
                role_name = role_name_value
                assigned_tags = _read_playbook_tag_list(
                    role_entry.get("tags"),
                    path,
                    role_name,
                )
            else:
                raise CatalogError(f"{path} contains an invalid role entry")

            playbook_tags.update(assigned_tags)
            playbook_tags.update(role_task_tags.get(role_name, set()))

    return playbook_tags


def build_playbook_tag_index(
    playbook_paths: Iterable[str | Path],
    roles_dir: str | Path | None = None,
) -> dict[str, set[str]]:
    return {
        str(resolve_catalog_playbook_path(playbook_path)): load_playbook_tags(
            playbook_path,
            roles_dir,
        )
        for playbook_path in playbook_paths
    }
