from __future__ import annotations

import importlib
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast

from ..runtime_config import get_runtime_paths

if sys.version_info >= (3, 11):
    import tomllib as _tomllib
else:  # pragma: no cover - Python 3.10 fallback
    _tomllib = importlib.import_module("tomli")


class _TomlModule(Protocol):
    TOMLDecodeError: type[Exception]

    def load(self, file: BinaryIO, /) -> dict[str, Any]: ...


tomllib = cast(_TomlModule, _tomllib)

HELPER_SHIMS = (
    "create",
    "lint",
    "ansible-check",
    "typecheck",
    "validate",
    "smoke-test",
)
SUPPORTED_INSTALL_GUIDANCE = (
    "envmgr self-management only supports install.sh-managed GitHub Release "
    "installs. Reinstall with the GitHub Release installer, or use the package "
    "manager that originally installed envmgr."
)


class SelfManagementError(RuntimeError):
    """Raised when an installer-managed self-management action cannot continue."""


@dataclass(frozen=True)
class InstallState:
    state_file: Path
    source: str
    manager: str
    owner: str
    repo: str
    version: str
    release_tag: str
    wheel_url: str
    uv: Path
    uv_tool_bin_dir: Path
    installed_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class SelfUpdateResult:
    state: InstallState
    version_output: str


@dataclass(frozen=True)
class SelfUninstallResult:
    state: InstallState
    kept_runtime_home: Path


def load_installer_state(envmgr_home: str | Path | None = None) -> InstallState:
    """Load the install.sh-managed GitHub Release state file."""
    state_file = get_runtime_paths(envmgr_home).home / "install.toml"
    if not state_file.exists():
        raise SelfManagementError(
            f"Installer state not found at {state_file}. {SUPPORTED_INSTALL_GUIDANCE}"
        )

    try:
        with state_file.open("rb") as file:
            document = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise SelfManagementError(
            f"Installer state at {state_file} is invalid TOML: {error}. "
            f"{SUPPORTED_INSTALL_GUIDANCE}"
        ) from error
    except OSError as error:
        raise SelfManagementError(
            f"Could not read installer state at {state_file}: {error}. "
            f"{SUPPORTED_INSTALL_GUIDANCE}"
        ) from error

    install_section = document.get("install")
    if not isinstance(install_section, Mapping):
        raise SelfManagementError(
            f"Installer state at {state_file} is missing an [install] table. "
            f"{SUPPORTED_INSTALL_GUIDANCE}"
        )

    install = cast(Mapping[str, Any], install_section)
    source = _required_string(install, "source", state_file)
    manager = _required_string(install, "manager", state_file)
    if source != "github-release" or manager != "install.sh":
        raise SelfManagementError(
            f"Installer state at {state_file} is not an install.sh-managed "
            f"GitHub Release install. {SUPPORTED_INSTALL_GUIDANCE}"
        )

    return InstallState(
        state_file=state_file,
        source=source,
        manager=manager,
        owner=_required_string(install, "owner", state_file),
        repo=_required_string(install, "repo", state_file),
        version=_required_string(install, "version", state_file),
        release_tag=_required_string(install, "release_tag", state_file),
        wheel_url=_required_string(install, "wheel_url", state_file),
        installed_at=_optional_string(install, "installed_at"),
        updated_at=_optional_string(install, "updated_at"),
        uv=Path(_required_string(install, "uv", state_file)).expanduser(),
        uv_tool_bin_dir=Path(
            _required_string(install, "uv_tool_bin_dir", state_file)
        ).expanduser(),
    )


def update_installer_managed_envmgr(
    *,
    requested_version: str | None,
    envmgr_home: str | Path | None = None,
) -> SelfUpdateResult:
    """Update envmgr through the wheel URL derived from installer state."""
    state = load_installer_state(envmgr_home)
    if requested_version is None:
        raise SelfManagementError(
            "Automatic latest-release resolution is not available yet. "
            "Pass --version VERSION to update to a specific GitHub Release."
        )

    target_state = _build_target_state(state, requested_version)
    _require_executable(state.uv, "recorded uv executable")
    _run_uv_command(
        [str(state.uv), "tool", "install", "--force", target_state.wheel_url]
    )
    version_output = verify_envmgr_version(state.uv_tool_bin_dir)
    verify_no_helper_shims(state.uv_tool_bin_dir)
    write_install_state(target_state)
    return SelfUpdateResult(state=target_state, version_output=version_output)


def uninstall_installer_managed_envmgr(state: InstallState) -> SelfUninstallResult:
    """Uninstall envmgr from the recorded uv tool environment."""
    _require_executable(state.uv, "recorded uv executable")
    _run_uv_command([str(state.uv), "tool", "uninstall", "envmgr"])
    try:
        state.state_file.unlink()
    except OSError as error:
        raise SelfManagementError(
            f"envmgr was uninstalled, but installer state could not be removed "
            f"at {state.state_file}: {error}"
        ) from error
    return SelfUninstallResult(state=state, kept_runtime_home=state.state_file.parent)


def verify_envmgr_version(uv_tool_bin_dir: Path) -> str:
    """Run the installed envmgr shim and return its first version line."""
    envmgr_command = _find_tool_in_bin_dir(uv_tool_bin_dir, "envmgr")
    if envmgr_command is None:
        raise SelfManagementError(
            f"Expected envmgr in the uv tool bin directory after update: "
            f"{uv_tool_bin_dir}"
        )
    _require_executable(envmgr_command, "envmgr shim")

    try:
        result = subprocess.run(
            [str(envmgr_command), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise SelfManagementError(
            f"Installed envmgr failed verification: {envmgr_command} --version: {error}"
        ) from error

    version_lines = [
        line.strip()
        for stream in (result.stdout, result.stderr)
        for line in stream.splitlines()
        if line.strip()
    ]
    version_output = version_lines[0] if version_lines else ""
    if result.returncode != 0:
        raise SelfManagementError(
            f"Installed envmgr failed verification with exit code "
            f"{result.returncode}: {envmgr_command} --version"
        )
    if not version_output.startswith("envmgr "):
        raise SelfManagementError(
            f"Installed envmgr returned unexpected version output: "
            f"{version_output or '<empty>'}"
        )
    return version_output


def verify_no_helper_shims(uv_tool_bin_dir: Path) -> None:
    """Reject stale checkout-only helper shims in the uv tool bin directory."""
    for helper in HELPER_SHIMS:
        helper_path = _find_tool_in_bin_dir(uv_tool_bin_dir, helper)
        if helper_path is not None:
            raise SelfManagementError(
                "Unexpected checkout-only helper shim found after update: "
                f"{helper_path}. Remove stale envmgr tool shims with "
                "`uv tool uninstall envmgr`, rerun the installer, then run "
                "`hash -r` in existing shells."
            )


def write_install_state(state: InstallState) -> None:
    """Rewrite install.toml using the installer-compatible schema."""
    lines = [
        "[install]",
        f'source = "{_toml_escape(state.source)}"',
        f'manager = "{_toml_escape(state.manager)}"',
        f'owner = "{_toml_escape(state.owner)}"',
        f'repo = "{_toml_escape(state.repo)}"',
        f'version = "{_toml_escape(state.version)}"',
        f'release_tag = "{_toml_escape(state.release_tag)}"',
        f'wheel_url = "{_toml_escape(state.wheel_url)}"',
    ]
    if state.installed_at is not None:
        lines.append(f'installed_at = "{_toml_escape(state.installed_at)}"')
    if state.updated_at is not None:
        lines.append(f'updated_at = "{_toml_escape(state.updated_at)}"')
    lines.extend(
        (
            f'uv = "{_toml_escape(str(state.uv))}"',
            f'uv_tool_bin_dir = "{_toml_escape(str(state.uv_tool_bin_dir))}"',
        )
    )

    try:
        state.state_file.parent.mkdir(parents=True, exist_ok=True)
        state.state_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as error:
        raise SelfManagementError(
            f"Could not write installer state at {state.state_file}: {error}"
        ) from error


def _required_string(
    install: Mapping[str, Any],
    key: str,
    state_file: Path,
) -> str:
    value = install.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SelfManagementError(
            f"Installer state at {state_file} is missing required field "
            f"install.{key}. {SUPPORTED_INSTALL_GUIDANCE}"
        )
    return value


def _optional_string(install: Mapping[str, Any], key: str) -> str | None:
    value = install.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _build_target_state(state: InstallState, requested_version: str) -> InstallState:
    package_version = _normalize_package_version(requested_version)
    release_tag = _release_tag_for_version(requested_version)
    wheel_url = (
        f"https://github.com/{state.owner}/{state.repo}/releases/download/"
        f"{release_tag}/{state.repo}-{package_version}-py3-none-any.whl"
    )
    timestamp = _utc_timestamp()
    return InstallState(
        state_file=state.state_file,
        source=state.source,
        manager=state.manager,
        owner=state.owner,
        repo=state.repo,
        version=package_version,
        release_tag=release_tag,
        wheel_url=wheel_url,
        uv=state.uv,
        uv_tool_bin_dir=state.uv_tool_bin_dir,
        installed_at=state.installed_at or timestamp,
        updated_at=timestamp,
    )


def _normalize_package_version(requested_version: str) -> str:
    requested = requested_version.strip()
    package_version = requested[1:] if requested.startswith("v") else requested
    if not package_version:
        raise SelfManagementError(
            "Version must be a concrete release such as 0.1.0 or v0.1.0."
        )
    return package_version


def _release_tag_for_version(requested_version: str) -> str:
    requested = requested_version.strip()
    return requested if requested.startswith("v") else f"v{requested}"


def _run_uv_command(command: Sequence[str]) -> None:
    try:
        result = subprocess.run(list(command), check=False)
    except OSError as error:
        raise SelfManagementError(
            f"Failed to run uv command {' '.join(command)}: {error}"
        ) from error

    if result.returncode != 0:
        raise SelfManagementError(
            f"uv command failed with exit code {result.returncode}: {' '.join(command)}"
        )


def _find_tool_in_bin_dir(bin_dir: Path, command_name: str) -> Path | None:
    for candidate in (bin_dir / command_name, bin_dir / f"{command_name}.exe"):
        if candidate.exists():
            return candidate
    return None


def _require_executable(path: Path, description: str) -> None:
    if not path.exists():
        raise SelfManagementError(f"{description} not found: {path}")
    if not os.access(path, os.X_OK):
        raise SelfManagementError(f"{description} is not executable: {path}")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
