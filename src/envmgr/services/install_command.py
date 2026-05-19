from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..catalog import CatalogError
from ..runtime_config import (
    RuntimePaths,
    ensure_runtime_layout,
    load_runtime_config,
    resolve_inventory_reference,
)
from .install_ai_tools import (
    AiToolsInstallDefaults,
    AiToolsInstallOptions,
    build_ai_tools_extra_vars,
    build_ai_tools_install_defaults,
)
from .install_playbooks import (
    build_execution_playbook,
    resolve_default_playbook_path,
    resolve_install_playbook,
)
from .install_tags import (
    is_all_tag_selection,
    load_available_tags,
    validate_selected_tags,
)


@dataclass(frozen=True)
class InstallPlan:
    selected_tags: list[str]
    role_tags: list[str]
    task_tags: list[str]
    source_playbook_path: str
    execution_playbook_path: str
    uses_temporary_execution_playbook: bool
    inventory_path: Path
    inventory_label: str
    runtime_paths: RuntimePaths
    default_ask_vault_pass: bool
    ai_tools_defaults: AiToolsInstallDefaults


def build_install_plan(
    selected_tags: list[str],
    *,
    explicit_playbook: str | None,
    inventory_reference: str | None,
    role_tags: list[str] | None = None,
    task_tags: list[str] | None = None,
    envmgr_home: str | Path | None = None,
) -> InstallPlan:
    """Build the execution plan for one `envmgr install` invocation."""
    if not selected_tags:
        raise CatalogError("no tags selected for execution")

    if role_tags is None or task_tags is None:
        resolved_role_tags, resolved_task_tags = load_available_tags()
    else:
        resolved_role_tags, resolved_task_tags = role_tags, task_tags
    validate_selected_tags(
        selected_tags,
        role_tags=resolved_role_tags,
        task_tags=resolved_task_tags,
    )

    runtime_paths = ensure_runtime_layout(envmgr_home)
    runtime_config = load_runtime_config(envmgr_home)

    resolved_explicit_playbook = explicit_playbook
    if is_all_tag_selection(selected_tags) and resolved_explicit_playbook is None:
        resolved_explicit_playbook = resolve_default_playbook_path(runtime_config)

    source_playbook_path = resolve_install_playbook(
        selected_tags,
        explicit_playbook=resolved_explicit_playbook,
    )
    if not Path(source_playbook_path).exists():
        raise CatalogError(f"playbook not found: {source_playbook_path}")

    inventory_path, inventory_label = resolve_inventory_reference(
        inventory_reference,
        envmgr_home=envmgr_home,
    )

    execution_playbook_path = source_playbook_path
    uses_temporary_execution_playbook = False
    try:
        if not is_all_tag_selection(selected_tags):
            execution_playbook_path = build_execution_playbook(
                source_playbook_path,
                selected_tags,
                runtime_paths=runtime_paths,
            )
            uses_temporary_execution_playbook = True
        ai_tools_defaults = build_ai_tools_install_defaults(
            selected_tags,
            execution_playbook_path=execution_playbook_path,
        )
    except Exception:
        if uses_temporary_execution_playbook:
            Path(execution_playbook_path).unlink(missing_ok=True)
        raise

    return InstallPlan(
        selected_tags=list(selected_tags),
        role_tags=list(resolved_role_tags),
        task_tags=list(resolved_task_tags),
        source_playbook_path=source_playbook_path,
        execution_playbook_path=execution_playbook_path,
        uses_temporary_execution_playbook=uses_temporary_execution_playbook,
        inventory_path=inventory_path,
        inventory_label=inventory_label,
        runtime_paths=runtime_paths,
        default_ask_vault_pass=runtime_config.default_ask_vault_pass,
        ai_tools_defaults=ai_tools_defaults,
    )


def build_install_command(
    install_plan: InstallPlan,
    *,
    ask_vault_pass: bool,
    ai_tools_options: AiToolsInstallOptions | None,
) -> list[str]:
    """Build the final ansible-playbook command for an install plan."""
    command = [
        "ansible-playbook",
        "-i",
        str(install_plan.inventory_path),
        install_plan.execution_playbook_path,
    ]
    if not is_all_tag_selection(install_plan.selected_tags):
        command.extend(["-t", ",".join(install_plan.selected_tags)])
    if ask_vault_pass:
        command.append("--ask-vault-pass")
    if ai_tools_options is not None:
        command.extend(
            ["--extra-vars", json.dumps(build_ai_tools_extra_vars(ai_tools_options))]
        )
    return command


def cleanup_install_plan(install_plan: InstallPlan) -> None:
    """Delete the temporary execution playbook created for a scoped install."""
    if install_plan.uses_temporary_execution_playbook:
        Path(install_plan.execution_playbook_path).unlink(missing_ok=True)
