from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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


def load_role_catalog(roles_dir: str | Path = "roles") -> list[RoleMetadata]:
    catalog: list[RoleMetadata] = []
    roles_path = Path(roles_dir)

    if not roles_path.exists():
        raise CatalogError(f"roles directory not found: {roles_path}")

    for role_dir in sorted(path for path in roles_path.iterdir() if path.is_dir()):
        metadata_path = role_dir / "meta" / "envmgr.yml"
        if metadata_path.exists():
            catalog.append(load_role_metadata(metadata_path))

    return catalog


def get_available_tags(roles_dir: str | Path = "roles") -> tuple[list[str], list[str]]:
    role_tags: set[str] = set()
    task_tags: set[str] = set()

    for metadata in load_role_catalog(roles_dir):
        if not metadata.enabled:
            continue
        role_tags.update(metadata.tags)
        task_tags.update(metadata.task_tags)

    return sorted(role_tags), sorted(task_tags)
