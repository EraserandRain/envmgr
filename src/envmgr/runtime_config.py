from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast

from .command_text import SETUP_HINT

if sys.version_info >= (3, 11):
    import tomllib as _tomllib
else:  # pragma: no cover - Python 3.10 fallback
    _tomllib = importlib.import_module("tomli")


class _TomlModule(Protocol):
    TOMLDecodeError: type[Exception]

    def load(self, file: BinaryIO, /) -> dict[str, Any]: ...


tomllib = cast(_TomlModule, _tomllib)


ENVMGR_HOME_ENV_VAR = "ENVMGR_HOME"
DEFAULT_PLAYBOOK = "workstation"
SETUP_SCHEMA_VERSION = 1
DEFAULT_CONFIG_TEXT = """[default]
inventory = "default"
playbook = "workstation"
ask_vault_pass = false

[inventory]
default = "inventory/default.yaml"
remote = "inventory/remote.yaml"
password = "inventory/password.yaml"
"""
DEFAULT_INVENTORY_TEXT = """all:
  children:
    workstation:
      hosts:
        localhost:
          ansible_connection: local
          ansible_python_interpreter: "{{ ansible_playbook_python }}"
    node:
      children:
        master:
          hosts:
            localhost:
              ansible_connection: local
              ansible_python_interpreter: "{{ ansible_playbook_python }}"
"""
REMOTE_INVENTORY_TEXT = """# Remote host configuration example
# Modify the values accordingly before use.

all:
  children:
    workstation:
      hosts:
        devbox:
          ansible_host: 192.168.1.50
          ansible_user: your_username
          ansible_ssh_private_key_file: ~/.ssh/id_rsa
          ansible_become: yes
          ansible_become_method: sudo
          ansible_python_interpreter: /usr/bin/python3
    node:
      children:
        master:
          hosts:
            remote-host:
              ansible_host: 192.168.1.100
              ansible_user: your_username
              ansible_ssh_private_key_file: ~/.ssh/id_rsa
              ansible_become: yes
              ansible_become_method: sudo
              ansible_python_interpreter: /usr/bin/python3
        worker:
          hosts:
            worker1:
              ansible_host: 192.168.1.101
              ansible_user: your_username
              ansible_ssh_private_key_file: ~/.ssh/id_rsa
              ansible_become: yes
              ansible_become_method: sudo
              ansible_python_interpreter: /usr/bin/python3
            worker2:
              ansible_host: 192.168.1.102
              ansible_user: your_username
              ansible_ssh_private_key_file: ~/.ssh/id_rsa
              ansible_become: yes
              ansible_become_method: sudo
              ansible_python_interpreter: /usr/bin/python3
"""
PASSWORD_INVENTORY_TEXT = """# Password authentication configuration example (requires sshpass)
# It is recommended to keep the real passwords in ~/.envmgr/inventory/group_vars/all/vault.yml
# and encrypt that file with ansible-vault.

all:
  children:
    workstation:
      hosts:
        devbox:
          ansible_host: 192.168.1.50
          ansible_user: your_username
          ansible_ssh_pass: "{{ vault_ssh_password }}"
          ansible_become: yes
          ansible_become_method: sudo
          ansible_become_pass: "{{ vault_sudo_password }}"
          ansible_python_interpreter: /usr/bin/python3
    node:
      children:
        master:
          hosts:
            remote-host:
              ansible_host: 192.168.1.100
              ansible_user: your_username
              ansible_ssh_pass: "{{ vault_ssh_password }}"
              ansible_become: yes
              ansible_become_method: sudo
              ansible_become_pass: "{{ vault_sudo_password }}"
              ansible_python_interpreter: /usr/bin/python3
"""


class ConfigError(ValueError):
    """Raised when the user-level envmgr configuration is missing or invalid."""


@dataclass(frozen=True)
class RuntimePaths:
    home: Path
    config_file: Path
    setup_marker_file: Path
    inventory_dir: Path
    default_inventory_file: Path
    remote_inventory_file: Path
    password_inventory_file: Path
    group_vars_all_dir: Path
    log_dir: Path
    ansible_log_file: Path
    runs_log_dir: Path
    cache_dir: Path
    galaxy_roles_dir: Path
    galaxy_collections_dir: Path
    tmp_dir: Path


@dataclass(frozen=True)
class RuntimeConfig:
    paths: RuntimePaths
    default_inventory: str
    default_playbook: str
    default_ask_vault_pass: bool
    inventories: dict[str, Path]


def _resolve_envmgr_home(envmgr_home: str | Path | None = None) -> Path:
    if envmgr_home is not None:
        return Path(envmgr_home).expanduser().resolve()

    configured_home = os.environ.get(ENVMGR_HOME_ENV_VAR)
    if configured_home:
        return Path(configured_home).expanduser().resolve()

    return (Path.home() / ".envmgr").resolve()


def get_runtime_paths(envmgr_home: str | Path | None = None) -> RuntimePaths:
    home = _resolve_envmgr_home(envmgr_home)
    inventory_dir = home / "inventory"
    log_dir = home / "log"
    cache_dir = home / "cache"

    return RuntimePaths(
        home=home,
        config_file=home / "config.toml",
        setup_marker_file=home / ".setup-complete",
        inventory_dir=inventory_dir,
        default_inventory_file=inventory_dir / "default.yaml",
        remote_inventory_file=inventory_dir / "remote.yaml",
        password_inventory_file=inventory_dir / "password.yaml",
        group_vars_all_dir=inventory_dir / "group_vars" / "all",
        log_dir=log_dir,
        ansible_log_file=log_dir / "ansible.log",
        runs_log_dir=log_dir / "runs",
        cache_dir=cache_dir,
        galaxy_roles_dir=cache_dir / "galaxy" / "roles",
        galaxy_collections_dir=cache_dir / "galaxy" / "collections",
        tmp_dir=cache_dir / "tmp",
    )


def _write_file_if_missing(path: Path, contents: str) -> None:
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def ensure_runtime_layout(envmgr_home: str | Path | None = None) -> RuntimePaths:
    paths = get_runtime_paths(envmgr_home)

    directories = [
        paths.home,
        paths.inventory_dir,
        paths.group_vars_all_dir,
        paths.log_dir,
        paths.runs_log_dir,
        paths.cache_dir,
        paths.galaxy_roles_dir,
        paths.galaxy_collections_dir,
        paths.tmp_dir,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    _write_file_if_missing(paths.config_file, DEFAULT_CONFIG_TEXT)
    _write_file_if_missing(paths.default_inventory_file, DEFAULT_INVENTORY_TEXT)
    _write_file_if_missing(paths.remote_inventory_file, REMOTE_INVENTORY_TEXT)
    _write_file_if_missing(paths.password_inventory_file, PASSWORD_INVENTORY_TEXT)

    return paths


def mark_runtime_setup_complete(paths: RuntimePaths) -> None:
    """Persist a marker showing that envmgr runtime bootstrap completed."""
    completed_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    paths.setup_marker_file.write_text(
        (f'schema_version = {SETUP_SCHEMA_VERSION}\ncompleted_at = "{completed_at}"\n'),
        encoding="utf-8",
    )


def _load_runtime_setup_stamp(paths: RuntimePaths) -> dict[str, Any] | None:
    if not paths.setup_marker_file.exists():
        return None

    try:
        with paths.setup_marker_file.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError):
        return None

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, int):
        return None

    completed_at = data.get("completed_at")
    if completed_at is not None and not isinstance(completed_at, str):
        return None

    return data


def is_runtime_setup_complete(paths: RuntimePaths) -> bool:
    """Return whether setup installed the runtime assets required by envmgr."""
    is_complete, _detail = get_runtime_setup_status(paths)
    return is_complete


def get_runtime_setup_status(paths: RuntimePaths) -> tuple[bool, str]:
    """Describe whether setup installed the runtime assets required by envmgr."""
    setup_stamp = _load_runtime_setup_stamp(paths)
    if setup_stamp is None:
        if not paths.setup_marker_file.exists():
            return False, f"setup marker is missing: {paths.setup_marker_file}"
        return False, f"setup marker is invalid: {paths.setup_marker_file}"

    if setup_stamp["schema_version"] < SETUP_SCHEMA_VERSION:
        return (
            False,
            "setup marker schema version "
            f"{setup_stamp['schema_version']} is older than required "
            f"{SETUP_SCHEMA_VERSION}",
        )

    try:
        galaxy_roles_ready = paths.galaxy_roles_dir.exists() and any(
            paths.galaxy_roles_dir.iterdir()
        )
        galaxy_collections_ready = paths.galaxy_collections_dir.exists() and any(
            paths.galaxy_collections_dir.iterdir()
        )
    except OSError as error:
        return False, f"failed to inspect Galaxy cache directories: {error}"

    if not galaxy_roles_ready:
        return False, f"Galaxy roles cache is empty: {paths.galaxy_roles_dir}"

    if not galaxy_collections_ready:
        return (
            False,
            f"Galaxy collections cache is empty: {paths.galaxy_collections_dir}",
        )

    completed_at = setup_stamp.get("completed_at")
    if completed_at:
        return True, f"setup completed at {completed_at}"

    return True, "setup marker is current"


def _require_mapping(value: Any, field_name: str, config_path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{config_path} field '{field_name}' must be a TOML table")
    return value


def _read_string(
    value: Any,
    field_name: str,
    config_path: Path,
    *,
    default: str | None = None,
) -> str:
    if value is None:
        if default is None:
            raise ConfigError(f"{config_path} field '{field_name}' is required")
        return default

    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"{config_path} field '{field_name}' must be a non-empty string"
        )

    return value


def _read_bool(
    value: Any,
    field_name: str,
    config_path: Path,
    *,
    default: bool,
) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"{config_path} field '{field_name}' must be a boolean")
    return value


def _resolve_config_path(raw_path: str, root: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _require_runtime_inventory_path(
    inventory_path: Path,
    *,
    alias_name: str,
    paths: RuntimePaths,
) -> Path:
    try:
        inventory_path.relative_to(paths.inventory_dir)
    except ValueError as error:
        raise ConfigError(
            f"{paths.config_file} inventory alias '{alias_name}' must stay under "
            f"{paths.inventory_dir}: {inventory_path}"
        ) from error
    return inventory_path


def load_runtime_config(
    envmgr_home: str | Path | None = None,
    *,
    ensure_layout: bool = True,
) -> RuntimeConfig:
    paths = (
        ensure_runtime_layout(envmgr_home)
        if ensure_layout
        else get_runtime_paths(envmgr_home)
    )

    if not paths.config_file.exists():
        raise ConfigError(f"{paths.config_file} does not exist; {SETUP_HINT}")

    try:
        with paths.config_file.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(
            f"{paths.config_file} contains invalid TOML: {error}"
        ) from error

    if not isinstance(data, dict):
        raise ConfigError(f"{paths.config_file} must contain a TOML table")

    default_table = _require_mapping(
        data.get("default", {}), "default", paths.config_file
    )
    inventory_table = _require_mapping(
        data.get("inventory", {}),
        "inventory",
        paths.config_file,
    )

    default_inventory = _read_string(
        default_table.get("inventory"),
        "default.inventory",
        paths.config_file,
        default="default",
    )
    default_playbook = _read_string(
        default_table.get("playbook"),
        "default.playbook",
        paths.config_file,
        default=DEFAULT_PLAYBOOK,
    )
    default_ask_vault_pass = _read_bool(
        default_table.get("ask_vault_pass"),
        "default.ask_vault_pass",
        paths.config_file,
        default=False,
    )

    inventories: dict[str, Path] = {}
    for name, raw_path in inventory_table.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(
                f"{paths.config_file} contains an invalid inventory alias"
            )
        inventories[name] = _require_runtime_inventory_path(
            _resolve_config_path(
                _read_string(raw_path, f"inventory.{name}", paths.config_file),
                paths.home,
            ),
            alias_name=name,
            paths=paths,
        )

    if default_inventory not in inventories:
        raise ConfigError(
            f"{paths.config_file} default inventory '{default_inventory}' is not defined under [inventory]"
        )

    return RuntimeConfig(
        paths=paths,
        default_inventory=default_inventory,
        default_playbook=default_playbook,
        default_ask_vault_pass=default_ask_vault_pass,
        inventories=inventories,
    )


def resolve_inventory_reference(
    reference: str | None,
    *,
    envmgr_home: str | Path | None = None,
    ensure_layout: bool = True,
) -> tuple[Path, str]:
    config = load_runtime_config(envmgr_home, ensure_layout=ensure_layout)
    selected = config.default_inventory if reference is None else reference

    if selected not in config.inventories:
        available_aliases = ", ".join(sorted(config.inventories))
        raise ConfigError(
            f"{config.paths.config_file} inventory alias '{selected}' is not defined under [inventory]; "
            f"available aliases: {available_aliases}"
        )

    inventory_path = config.inventories[selected]

    if not inventory_path.exists():
        raise ConfigError(
            f"{config.paths.config_file} inventory alias '{selected}' points to a missing file: {inventory_path}"
        )

    return inventory_path, selected
