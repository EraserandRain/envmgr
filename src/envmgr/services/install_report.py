from __future__ import annotations

import shlex

from rich.text import Text

from ..runtime_config import AiToolsConfig
from .ai_tools_catalog import AI_TOOLS
from .console import (
    InstallConsole,
    print_labeled_value,
    print_section_title,
)
from .install_ai_tools import (
    AiToolsInstallOptions,
    build_ai_tools_extra_vars,
)
from .install_command import INSTALL_PLAN_SCHEMA_VERSION, InstallPlan
from .install_tags import is_all_tag_selection

BUILTIN_SCENARIOS = (
    (
        "workstation",
        "Local workstation setup for the workstation inventory group.",
    ),
    (
        "node",
        "Kubernetes node setup: node prerequisites plus master-only tools.",
    ),
)


def print_builtin_scenarios(console: InstallConsole) -> None:
    """Render built-in scenario tokens alongside tag discovery output."""
    console.print()
    console.print(Text("Built-in scenarios:", style="bold"))
    for name, description in BUILTIN_SCENARIOS:
        console.print(Text(f"  - {name}: {description}"))


def _render_selected_tags(install_plan: InstallPlan) -> str | Text:
    """Render the selected role/task tags for a human install plan summary."""
    if is_all_tag_selection(install_plan.selected_tags):
        return Text("All tags will be executed", style="green")

    rendered_tags = Text()
    for index, tag in enumerate(install_plan.selected_tags):
        if index:
            rendered_tags.append(" ")
        label = "Role" if tag in install_plan.role_tags else "Task"
        style = "green" if label == "Role" else "cyan"
        rendered_tags.append(f"[{label}: {tag}]", style=style)
    return rendered_tags


def _render_ai_tools_summary(
    console: InstallConsole,
    ai_tools_options: AiToolsInstallOptions | None,
) -> None:
    """Render the AI tools choices when a run targets the `ai_tools` role."""
    if ai_tools_options is None:
        return

    parts = ", ".join(
        f"{spec.label}={bool(getattr(ai_tools_options, spec.key))}" for spec in AI_TOOLS
    )
    print_labeled_value(
        console,
        "AI tools",
        parts,
    )


def build_install_plan_json(
    *,
    install_plan: InstallPlan,
    ask_vault_pass: bool,
    ai_tools_options: AiToolsInstallOptions | None,
    command: list[str],
) -> dict[str, object]:
    """Serialize an install plan into the versioned machine-readable contract."""
    ai_tools: dict[str, object] = {"applicable": ai_tools_options is not None}
    if ai_tools_options is not None:
        ai_tools.update(
            {
                "manage_claude_code": ai_tools_options.manage_claude_code,
                "manage_codex": ai_tools_options.manage_codex,
                "manage_rtk": ai_tools_options.manage_rtk,
                "extra_vars": build_ai_tools_extra_vars(ai_tools_options),
            }
        )

    return {
        "schema_version": INSTALL_PLAN_SCHEMA_VERSION,
        "selected_tags": list(install_plan.selected_tags),
        "all_tags": is_all_tag_selection(install_plan.selected_tags),
        "source_playbook_path": install_plan.source_playbook_path,
        "execution_playbook_path": install_plan.execution_playbook_path,
        "uses_temporary_execution_playbook": (
            install_plan.uses_temporary_execution_playbook
        ),
        "inventory": {
            "label": install_plan.inventory_label,
            "path": str(install_plan.inventory_path),
        },
        "ask_vault_pass": ask_vault_pass,
        "ai_tools": ai_tools,
        "command_argv": list(command),
    }


def render_install_plan_summary(
    console: InstallConsole,
    *,
    title: str,
    install_plan: InstallPlan,
    ask_vault_pass: bool,
    ai_tools_options: AiToolsInstallOptions | None,
    command: list[str],
    show_execution_details: bool = False,
) -> None:
    """Render the human install plan summary through the install console."""
    console.print()
    print_section_title(console, title)
    print_labeled_value(console, "Playbook", install_plan.source_playbook_path)
    if install_plan.execution_playbook_path != install_plan.source_playbook_path:
        print_labeled_value(
            console,
            "Execution playbook",
            install_plan.execution_playbook_path,
        )
    print_labeled_value(
        console,
        "Inventory",
        f"{install_plan.inventory_label} -> {install_plan.inventory_path}",
    )
    print_labeled_value(console, "Tags", _render_selected_tags(install_plan))
    _render_ai_tools_summary(console, ai_tools_options)
    if show_execution_details:
        print_labeled_value(console, "Ask vault pass", str(ask_vault_pass))
        print_labeled_value(console, "Command", shlex.join(command))
    console.print()


def build_ai_tools_config_from_options(
    options: AiToolsInstallOptions,
) -> AiToolsConfig:
    """Build a configured `[ai_tools]` config from resolved install options."""
    return AiToolsConfig(
        configured=True,
        manage_claude_code=options.manage_claude_code,
        manage_codex=options.manage_codex,
        manage_rtk=options.manage_rtk,
    )
