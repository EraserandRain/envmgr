from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..command_text import SETUP_HINT
from ..runtime_config import (
    ConfigError,
    RuntimePaths,
    get_runtime_paths,
    get_runtime_setup_status,
    load_runtime_config,
)
from .assets import RuntimeAssetError, RuntimeAssets, resolve_runtime_assets
from .runtime import build_effective_command_path

DOCTOR_COMMANDS = ("uv", "ansible", "ansible-playbook", "ansible-galaxy")
DOCTOR_OK = "ok"
DOCTOR_WARN = "warn"
DOCTOR_FAIL = "fail"
REQUIRED_RUNTIME_DIRECTORIES = (
    "inventory_dir",
    "group_vars_all_dir",
    "log_dir",
    "runs_log_dir",
    "cache_dir",
    "galaxy_roles_dir",
    "galaxy_collections_dir",
    "tmp_dir",
)


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    paths: RuntimePaths
    default_inventory: str | None
    default_playbook_path: str | None
    checks: list[DoctorCheck]


def build_doctor_report(envmgr_home: str | Path | None = None) -> DoctorReport:
    """Collect a read-only health report for the envmgr runtime."""
    paths = get_runtime_paths(envmgr_home)
    checks: list[DoctorCheck] = []
    default_inventory: str | None = None
    default_playbook_path: str | None = None
    runtime_assets: RuntimeAssets | None = None

    def add_check(name: str, status: str, detail: str) -> None:
        checks.append(DoctorCheck(name=name, status=status, detail=detail))

    try:
        runtime_assets = resolve_runtime_assets(runtime_paths=paths)
    except RuntimeAssetError as error:
        add_check("runtime assets", DOCTOR_FAIL, str(error))

    effective_path = build_effective_command_path()
    missing_commands = [
        command_name
        for command_name in DOCTOR_COMMANDS
        if shutil.which(command_name, path=effective_path) is None
    ]
    if missing_commands:
        add_check(
            "commands",
            DOCTOR_FAIL,
            "missing: " + ", ".join(missing_commands),
        )
    else:
        add_check(
            "commands",
            DOCTOR_OK,
            ", ".join(DOCTOR_COMMANDS),
        )

    if not paths.home.exists():
        add_check(
            "runtime home",
            DOCTOR_FAIL,
            f"missing: {paths.home}; {SETUP_HINT}",
        )

    missing_runtime_directories = [
        str(getattr(paths, attribute_name))
        for attribute_name in REQUIRED_RUNTIME_DIRECTORIES
        if not getattr(paths, attribute_name).exists()
    ]
    if missing_runtime_directories:
        add_check(
            "runtime directories",
            DOCTOR_FAIL,
            "missing " + ", ".join(missing_runtime_directories),
        )

    if not paths.config_file.exists():
        add_check(
            "runtime config",
            DOCTOR_FAIL,
            f"missing {paths.config_file}; {SETUP_HINT}",
        )
    else:
        try:
            config = load_runtime_config(envmgr_home, ensure_layout=False)
        except ConfigError as error:
            add_check("runtime config", DOCTOR_FAIL, str(error))
        else:
            default_inventory = config.default_inventory
            if runtime_assets is not None:
                try:
                    default_playbook_path = str(
                        runtime_assets.resolve_playbook(config.default_playbook)
                    )
                except RuntimeAssetError as error:
                    add_check("runtime config", DOCTOR_FAIL, str(error))
            elif Path(config.default_playbook).is_absolute():
                default_playbook_path = str(
                    Path(config.default_playbook).expanduser().resolve()
                )

            if default_playbook_path is None:
                add_check(
                    "runtime config",
                    DOCTOR_FAIL,
                    (
                        "default playbook could not be resolved because runtime "
                        "assets are unavailable"
                    ),
                )
            elif not Path(default_playbook_path).exists():
                add_check(
                    "runtime config",
                    DOCTOR_FAIL,
                    "inventory="
                    f"{config.default_inventory} playbook={config.default_playbook} "
                    f"(missing playbook: {default_playbook_path})",
                )

            default_inventory_path = config.inventories.get(config.default_inventory)
            if default_inventory_path is None:
                add_check(
                    "runtime config",
                    DOCTOR_FAIL,
                    f"default inventory alias '{config.default_inventory}' is missing from config",
                )
            elif default_inventory_path.exists():
                add_check(
                    f"inventory alias `{config.default_inventory}`",
                    DOCTOR_OK,
                    str(default_inventory_path),
                )
            else:
                add_check(
                    f"inventory alias `{config.default_inventory}`",
                    DOCTOR_FAIL,
                    f"missing: {default_inventory_path}",
                )

    setup_is_complete, setup_detail = get_runtime_setup_status(paths)
    add_check(
        "setup state",
        DOCTOR_OK if setup_is_complete else DOCTOR_FAIL,
        setup_detail,
    )

    return DoctorReport(
        paths=paths,
        default_inventory=default_inventory,
        default_playbook_path=default_playbook_path,
        checks=checks,
    )


def summarize_doctor_report(report: DoctorReport) -> tuple[int, int, int]:
    """Count ok, warn, and fail checks for a doctor report."""
    ok_count = sum(1 for check in report.checks if check.status == DOCTOR_OK)
    warn_count = sum(1 for check in report.checks if check.status == DOCTOR_WARN)
    fail_count = sum(1 for check in report.checks if check.status == DOCTOR_FAIL)
    return ok_count, warn_count, fail_count


def get_doctor_overall_status(report: DoctorReport) -> str:
    """Return the overall doctor status derived from its checks."""
    _ok_count, warn_count, fail_count = summarize_doctor_report(report)
    if fail_count:
        return DOCTOR_FAIL
    if warn_count:
        return DOCTOR_WARN
    return DOCTOR_OK


def build_doctor_json_payload(
    report: DoctorReport,
    *,
    configured_home: str | None,
) -> dict[str, Any]:
    """Serialize a doctor report into a machine-readable payload."""
    ok_count, warn_count, fail_count = summarize_doctor_report(report)
    resolved_configured_home = None
    if configured_home:
        resolved_configured_home = str(Path(configured_home).expanduser().resolve())

    return {
        "status": get_doctor_overall_status(report),
        "summary": {
            "ok": ok_count,
            "warn": warn_count,
            "fail": fail_count,
            "total": len(report.checks),
        },
        "runtime": {
            "home": str(report.paths.home),
            "configured_home": resolved_configured_home,
            "config_file": str(report.paths.config_file),
        },
        "defaults": {
            "inventory": report.default_inventory,
            "playbook": report.default_playbook_path,
        },
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
            }
            for check in report.checks
        ],
    }
