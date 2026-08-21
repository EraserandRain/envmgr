from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.text import Text

from ..catalog import CatalogError
from ..runtime_config import AiToolsConfig
from .console import (
    InstallConsole,
    print_labeled_value,
    print_section_title,
    print_warning,
)
from .install_playbooks import playbook_includes_role


class WizardCancelled(RuntimeError):
    """Raised when the interactive AI tools setup wizard is cancelled by the user."""


@dataclass(frozen=True)
class AiToolsInstallOptions:
    manage_claude_code: bool
    manage_codex: bool
    manage_rtk: bool


@dataclass(frozen=True)
class AiToolsInstallDefaults:
    applicable: bool
    manage_claude_code: bool
    manage_codex: bool
    manage_rtk: bool


@dataclass(frozen=True)
class AiToolsResolution:
    """A resolved AI-tools install plan and whether it should be persisted."""

    options: AiToolsInstallOptions | None
    persist: bool = False


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


def build_ai_tools_extra_vars(options: AiToolsInstallOptions) -> dict[str, Any]:
    """Build Ansible extra vars for AI-tools install-time choices."""
    return {
        "ai_tools_manage_claude_code_override": options.manage_claude_code,
        "ai_tools_manage_codex_override": options.manage_codex,
        "ai_tools_manage_rtk_override": options.manage_rtk,
    }


def _options_from_config(config: AiToolsConfig) -> AiToolsInstallOptions:
    """Build effective install options from the saved `[ai_tools]` config."""
    options = AiToolsInstallOptions(
        manage_claude_code=config.manage_claude_code,
        manage_codex=config.manage_codex,
        manage_rtk=config.manage_rtk,
    )
    _ensure_at_least_one_tool(options)
    return options


def _options_from_defaults(
    defaults: AiToolsInstallDefaults,
) -> AiToolsInstallOptions:
    """Build effective install options from tag-derived defaults."""
    options = AiToolsInstallOptions(
        manage_claude_code=defaults.manage_claude_code,
        manage_codex=defaults.manage_codex,
        manage_rtk=defaults.manage_rtk,
    )
    _ensure_at_least_one_tool(options)
    return options


def _ensure_at_least_one_tool(options: AiToolsInstallOptions) -> None:
    """Raise when every AI tool is disabled for a run that targets this role."""
    if not (options.manage_claude_code or options.manage_codex or options.manage_rtk):
        raise CatalogError(
            "AI tools selection disabled Claude Code, Codex CLI, and RTK; "
            "choose at least one tool"
        )


def _format_enabled_status(enabled: bool) -> Text:
    """Return a styled enabled/disabled label for setup summaries."""
    return Text("enabled", style="green") if enabled else Text("disabled", style="dim")


def _build_ai_tools_setup_summary(
    options: AiToolsInstallOptions,
) -> list[tuple[str, str | Text]]:
    """Build a short setup summary for the interactive AI tools wizard."""
    return [
        ("Claude Code", _format_enabled_status(options.manage_claude_code)),
        ("Codex CLI", _format_enabled_status(options.manage_codex)),
        ("RTK", _format_enabled_status(options.manage_rtk)),
    ]


def _prompt_bool(console: InstallConsole, message: str, *, default: bool) -> bool:
    """Prompt for a yes/no decision through the install console."""
    return console.confirm(message, default=default)


def _run_ai_tools_setup_wizard(
    *,
    defaults: AiToolsInstallDefaults,
    console: InstallConsole,
) -> AiToolsInstallOptions:
    """Run the interactive AI tools setup wizard and return the selected options."""
    console.print()
    print_section_title(console, "AI Tools Setup")
    console.print("We'll help you choose which AI tools to install on this machine.")
    console.print(Text("Press Ctrl+C at any time to cancel.", style="dim"))

    while True:
        resolved_manage_claude_code = _prompt_bool(
            console,
            "Install Claude Code?",
            default=defaults.manage_claude_code,
        )
        resolved_manage_codex = _prompt_bool(
            console,
            "Install Codex CLI?",
            default=defaults.manage_codex,
        )
        resolved_manage_rtk = _prompt_bool(
            console,
            "Install RTK?",
            default=defaults.manage_rtk,
        )

        if resolved_manage_claude_code or resolved_manage_codex or resolved_manage_rtk:
            break

        print_warning(console, "Select at least one tool to continue.")

    options = AiToolsInstallOptions(
        manage_claude_code=resolved_manage_claude_code,
        manage_codex=resolved_manage_codex,
        manage_rtk=resolved_manage_rtk,
    )

    console.print()
    print_section_title(console, "AI Tools Setup Summary")
    for label, value in _build_ai_tools_setup_summary(options):
        print_labeled_value(console, label, value, prefix="- ")

    if not _prompt_bool(console, "Install with these settings?", default=True):
        raise WizardCancelled("AI Tools Setup cancelled before installation.")

    return options


def resolve_ai_tools_choices(
    selected_tags: list[str],
    *,
    execution_playbook_path: str,
    ai_tools_config: AiToolsConfig,
    interactive: bool,
    console: InstallConsole,
) -> AiToolsResolution:
    """Resolve AI-tools install choices from config, tags, and first-run wizard."""
    defaults = build_ai_tools_install_defaults(
        selected_tags,
        execution_playbook_path=execution_playbook_path,
    )
    if not defaults.applicable:
        return AiToolsResolution(options=None)

    requested_tags = {tag.lower() for tag in selected_tags}
    default_scope = "all" in requested_tags or "ai_tools" in requested_tags

    if default_scope and ai_tools_config.configured:
        return AiToolsResolution(options=_options_from_config(ai_tools_config))

    if default_scope and interactive:
        options = _run_ai_tools_setup_wizard(
            defaults=defaults,
            console=console,
        )
        return AiToolsResolution(options=options, persist=True)

    if default_scope:
        # Non-interactive first run: fall back to tag-derived defaults without
        # prompting, and do not persist (the caller may be a script or CI run).
        options = _options_from_defaults(defaults)
        return AiToolsResolution(options=options)

    # Targeted task-tag run (claude_code / codex / rtk): tool selection comes from
    # the tags themselves.
    options = _options_from_defaults(defaults)
    return AiToolsResolution(options=options)
