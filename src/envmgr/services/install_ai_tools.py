from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..catalog import CatalogError
from .install_playbooks import playbook_includes_role

AI_TOOLS_CONTEXT7_METHODS = ("remote", "local")


@dataclass(frozen=True)
class AiToolsInstallOptions:
    manage_claude_code: bool
    manage_codex: bool
    manage_rtk: bool
    enable_context7: bool
    claude_context7_method: str
    codex_context7_method: str


@dataclass(frozen=True)
class AiToolsInstallDefaults:
    applicable: bool
    manage_claude_code: bool
    manage_codex: bool
    manage_rtk: bool


def build_ai_tools_install_defaults(
    selected_tags: list[str],
    *,
    execution_playbook_path: str,
) -> AiToolsInstallDefaults:
    """Compute default AI-tools selections for the chosen tag set."""
    if not playbook_includes_role(execution_playbook_path, "ai_tools"):
        return AiToolsInstallDefaults(
            applicable=False,
            manage_claude_code=False,
            manage_codex=False,
            manage_rtk=False,
        )

    requested_tags = {tag.lower() for tag in selected_tags}
    return AiToolsInstallDefaults(
        applicable=True,
        manage_claude_code=any(
            tag in requested_tags for tag in ("all", "ai_tools", "claude_code")
        ),
        manage_codex=any(tag in requested_tags for tag in ("all", "codex")),
        manage_rtk=any(tag in requested_tags for tag in ("all", "ai_tools", "rtk")),
    )


def resolve_noninteractive_ai_tools_install_options(
    defaults: AiToolsInstallDefaults,
    *,
    manage_claude_code: bool | None,
    manage_codex: bool | None,
    manage_rtk: bool | None,
    enable_context7: bool | None,
    claude_context7_method: str | None,
    codex_context7_method: str | None,
) -> AiToolsInstallOptions | None:
    """Resolve AI-tools install options without any interactive prompts."""
    if not defaults.applicable:
        return None

    resolved_manage_claude_code = (
        defaults.manage_claude_code
        if manage_claude_code is None
        else manage_claude_code
    )
    resolved_manage_codex = (
        defaults.manage_codex if manage_codex is None else manage_codex
    )
    resolved_manage_rtk = defaults.manage_rtk if manage_rtk is None else manage_rtk

    if not (
        resolved_manage_claude_code or resolved_manage_codex or resolved_manage_rtk
    ):
        raise CatalogError(
            "AI tools selection disabled Claude Code, Codex CLI, and RTK; choose at least one tool"
        )

    context7_applicable = resolved_manage_claude_code or resolved_manage_codex
    resolved_enable_context7 = False
    if context7_applicable:
        resolved_enable_context7 = True if enable_context7 is None else enable_context7
    resolved_claude_context7_method = (
        "remote" if claude_context7_method is None else claude_context7_method
    )
    resolved_codex_context7_method = (
        "remote" if codex_context7_method is None else codex_context7_method
    )

    return AiToolsInstallOptions(
        manage_claude_code=resolved_manage_claude_code,
        manage_codex=resolved_manage_codex,
        manage_rtk=resolved_manage_rtk,
        enable_context7=resolved_enable_context7,
        claude_context7_method=resolved_claude_context7_method,
        codex_context7_method=resolved_codex_context7_method,
    )


def build_ai_tools_extra_vars(options: AiToolsInstallOptions) -> dict[str, Any]:
    """Build Ansible extra vars for AI-tools install-time choices."""
    return {
        "ai_tools_manage_claude_code_override": options.manage_claude_code,
        "ai_tools_manage_codex_override": options.manage_codex,
        "ai_tools_manage_rtk_override": options.manage_rtk,
        "ai_tools_context7_enabled": options.enable_context7,
        "ai_tools_claude_context7_method": options.claude_context7_method,
        "ai_tools_codex_context7_method": options.codex_context7_method,
    }
