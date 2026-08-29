from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class AiToolSpec:
    """Declarative description of one AI tool envmgr can install.

    `key` is the Python config field suffix (for example `manage_claude_code`),
    `tool_tag` is the install task tag, `label` is the user-facing name, and
    `extra_var` is the Ansible per-tool override variable. `trigger_tags` are the
    role/task tags that enable the tool during tag-driven planning.
    """

    key: str
    tool_tag: str
    label: str
    extra_var: str
    default_enabled: bool
    trigger_tags: tuple[str, ...]


AI_TOOLS_ROLE_TAG = "ai_tools"

AI_TOOLS: tuple[AiToolSpec, ...] = (
    AiToolSpec(
        key="manage_claude_code",
        tool_tag="claude_code",
        label="Claude Code",
        extra_var="ai_tools_manage_claude_code_override",
        default_enabled=True,
        trigger_tags=("all", AI_TOOLS_ROLE_TAG, "claude_code"),
    ),
    AiToolSpec(
        key="manage_codex",
        tool_tag="codex",
        label="Codex CLI",
        extra_var="ai_tools_manage_codex_override",
        default_enabled=False,
        trigger_tags=("all", "codex"),
    ),
    AiToolSpec(
        key="manage_rtk",
        tool_tag="rtk",
        label="RTK",
        extra_var="ai_tools_manage_rtk_override",
        default_enabled=True,
        trigger_tags=("all", AI_TOOLS_ROLE_TAG, "rtk"),
    ),
)


def ai_tool_specs_by_key() -> dict[str, AiToolSpec]:
    """Return the AI-tool registry keyed by config field name."""
    return {spec.key: spec for spec in AI_TOOLS}


def ai_tool_specs_by_tag() -> dict[str, AiToolSpec]:
    """Return the AI-tool registry keyed by install task tag."""
    return {spec.tool_tag: spec for spec in AI_TOOLS}


def ai_tool_extra_vars(enabled: dict[str, bool]) -> dict[str, bool]:
    """Build the Ansible extra-vars mapping from a per-key enabled state."""
    return {spec.extra_var: bool(enabled.get(spec.key, False)) for spec in AI_TOOLS}


def validate_ai_tools_registry_task_tags(
    available_task_tags: Iterable[str],
) -> list[str]:
    """Return AI-tool tag names missing from the role catalog."""
    available = set(available_task_tags)
    return [spec.tool_tag for spec in AI_TOOLS if spec.tool_tag not in available]
