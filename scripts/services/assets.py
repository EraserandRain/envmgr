from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..runtime_config import RuntimePaths, get_runtime_paths

ENVMGR_ASSET_ROOT_ENV_VAR = "ENVMGR_ASSET_ROOT"
_SCENARIO_PLAYBOOK_SUFFIXES = (".yml", ".yaml")


class RuntimeAssetError(ValueError):
    """Raised when envmgr cannot locate its packaged runtime assets."""


@dataclass(frozen=True)
class RuntimeAssets:
    root: Path
    runtime_paths: RuntimePaths
    ansible_config_file: Path
    requirements_file: Path
    roles_dir: Path
    playbooks_dir: Path
    vars_dir: Path
    scenario_playbooks: dict[str, Path]

    @property
    def scratch_dir(self) -> Path:
        return self.runtime_paths.tmp_dir

    def resolve_repo_path(self, reference: str | Path) -> Path:
        path = Path(reference).expanduser()
        if path.is_absolute():
            return path.resolve()

        cwd_candidate = path.resolve()
        if cwd_candidate.exists():
            return cwd_candidate

        return (self.root / path).resolve()

    def resolve_playbook(self, reference: str | Path) -> Path:
        raw_reference = Path(reference).expanduser()
        if raw_reference.is_absolute():
            return raw_reference.resolve()

        if raw_reference.suffix in _SCENARIO_PLAYBOOK_SUFFIXES:
            resolved_path = self.resolve_repo_path(raw_reference)
            if resolved_path.exists():
                return resolved_path
            scenario_candidate = (self.playbooks_dir / raw_reference.name).resolve()
            if scenario_candidate.exists():
                return scenario_candidate
            return resolved_path

        if len(raw_reference.parts) > 1:
            return self.resolve_repo_path(raw_reference)

        scenario_name = raw_reference.name
        if scenario_name in self.scenario_playbooks:
            return self.scenario_playbooks[scenario_name]

        for suffix in _SCENARIO_PLAYBOOK_SUFFIXES:
            candidate = (self.playbooks_dir / f"{scenario_name}{suffix}").resolve()
            if candidate.exists():
                return candidate

        raise RuntimeAssetError(f"unknown scenario playbook: {reference}")

    def resolve_role_dir(self, role_name: str) -> Path:
        return (self.roles_dir / role_name).resolve()


def _build_scenario_playbooks(playbooks_dir: Path) -> dict[str, Path]:
    scenario_playbooks: dict[str, Path] = {}
    for suffix in _SCENARIO_PLAYBOOK_SUFFIXES:
        for playbook_path in sorted(playbooks_dir.glob(f"*{suffix}")):
            scenario_playbooks.setdefault(
                playbook_path.stem,
                playbook_path.resolve(),
            )
    return scenario_playbooks


def _validate_asset_root(root: Path) -> None:
    required_paths = {
        "ansible.cfg": root / "ansible.cfg",
        "requirements.yaml": root / "requirements.yaml",
        "playbooks/": root / "playbooks",
        "roles/": root / "roles",
        "vars/": root / "vars",
    }
    missing = [
        label for label, candidate in required_paths.items() if not candidate.exists()
    ]
    if missing:
        raise RuntimeAssetError(
            f"envmgr runtime assets not found under {root}: missing {', '.join(missing)}"
        )


def resolve_runtime_asset_root(
    *,
    package_dir: str | Path | None = None,
) -> Path:
    configured_root = os.environ.get(ENVMGR_ASSET_ROOT_ENV_VAR)
    if configured_root:
        root = Path(configured_root).expanduser().resolve()
        _validate_asset_root(root)
        return root

    resolved_package_dir = (
        Path(package_dir).expanduser().resolve()
        if package_dir is not None
        else Path(__file__).resolve().parents[1]
    )

    candidates: list[Path] = [
        (resolved_package_dir / "_assets").resolve(),
        resolved_package_dir.parent.resolve(),
        (resolved_package_dir.parent / "envmgr_assets").resolve(),
    ]
    candidates.extend(parent.resolve() for parent in resolved_package_dir.parents)

    seen_candidates: set[Path] = set()
    for candidate in candidates:
        if candidate in seen_candidates:
            continue
        seen_candidates.add(candidate)
        try:
            _validate_asset_root(candidate)
        except RuntimeAssetError:
            continue
        return candidate

    raise RuntimeAssetError(
        "envmgr runtime assets could not be located from the installed package"
    )


def resolve_runtime_assets(
    *,
    envmgr_home: str | Path | None = None,
    runtime_paths: RuntimePaths | None = None,
    package_dir: str | Path | None = None,
) -> RuntimeAssets:
    resolved_runtime_paths = (
        get_runtime_paths(envmgr_home) if runtime_paths is None else runtime_paths
    )
    root = resolve_runtime_asset_root(package_dir=package_dir)
    playbooks_dir = (root / "playbooks").resolve()

    return RuntimeAssets(
        root=root,
        runtime_paths=resolved_runtime_paths,
        ansible_config_file=(root / "ansible.cfg").resolve(),
        requirements_file=(root / "requirements.yaml").resolve(),
        roles_dir=(root / "roles").resolve(),
        playbooks_dir=playbooks_dir,
        vars_dir=(root / "vars").resolve(),
        scenario_playbooks=_build_scenario_playbooks(playbooks_dir),
    )
