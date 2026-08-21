from __future__ import annotations

import os
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
    enable_context7: bool
    claude_context7_method: str
    codex_context7_method: str


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
        "ai_tools_context7_enabled": options.enable_context7,
        "ai_tools_claude_context7_method": options.claude_context7_method,
        "ai_tools_codex_context7_method": options.codex_context7_method,
    }


def _options_from_config(config: AiToolsConfig) -> AiToolsInstallOptions:
    """Build effective install options from the saved `[ai_tools]` config."""
    options = AiToolsInstallOptions(
        manage_claude_code=config.manage_claude_code,
        manage_codex=config.manage_codex,
        manage_rtk=config.manage_rtk,
        enable_context7=config.enable_context7,
        claude_context7_method=config.claude_context7_method,
        codex_context7_method=config.codex_context7_method,
    )
    _ensure_at_least_one_tool(options)
    return options


def _options_from_defaults(
    defaults: AiToolsInstallDefaults,
    *,
    enable_context7: bool,
    claude_context7_method: str,
    codex_context7_method: str,
) -> AiToolsInstallOptions:
    """Build effective install options from tag-derived defaults."""
    options = AiToolsInstallOptions(
        manage_claude_code=defaults.manage_claude_code,
        manage_codex=defaults.manage_codex,
        manage_rtk=defaults.manage_rtk,
        enable_context7=enable_context7,
        claude_context7_method=claude_context7_method,
        codex_context7_method=codex_context7_method,
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


def _render_context7_method_label(method: str) -> str:
    """Return a user-facing label for a Context7 connection mode."""
    if method == "remote":
        return "Remote service"
    return "Local MCP process"


def _build_ai_tools_setup_summary(
    options: AiToolsInstallOptions,
    *,
    context7_api_key_present: bool,
) -> list[tuple[str, str | Text]]:
    """Build a short setup summary for the interactive AI tools wizard."""
    context7_applicable = options.manage_claude_code or options.manage_codex
    lines: list[tuple[str, str | Text]] = [
        ("Claude Code", _format_enabled_status(options.manage_claude_code)),
        ("Codex CLI", _format_enabled_status(options.manage_codex)),
        ("RTK", _format_enabled_status(options.manage_rtk)),
    ]
    if context7_applicable:
        lines.append(("Context7", _format_enabled_status(options.enable_context7)))
    if options.enable_context7 and context7_applicable:
        if options.manage_claude_code:
            lines.append(
                (
                    "Claude Code Context7",
                    _render_context7_method_label(options.claude_context7_method),
                )
            )
        if options.manage_codex:
            lines.append(
                (
                    "Codex CLI Context7",
                    _render_context7_method_label(options.codex_context7_method),
                )
            )
        if not context7_api_key_present:
            lines.append(
                ("Context7 API key", "not set; envmgr will continue without it")
            )
    return lines


def _prompt_bool(console: InstallConsole, message: str, *, default: bool) -> bool:
    """Prompt for a yes/no decision through the install console."""
    return console.confirm(message, default=default)


def _prompt_context7_method(
    console: InstallConsole,
    tool_name: str,
    *,
    default: str,
) -> str:
    """Prompt for a user-friendly Context7 connection mode."""
    options = [
        (
            "1",
            "remote",
            "Remote service",
            "Connect to the hosted Context7 MCP endpoint.",
        ),
        (
            "2",
            "local",
            "Local MCP process",
            "Run Context7 locally through `npx` on this machine.",
        ),
    ]
    option_by_token = {token: method for token, method, _label, _description in options}
    option_by_token.update(
        {method: method for _token, method, _label, _description in options}
    )
    default_token = next(
        token for token, method, _label, _description in options if method == default
    )

    console.print()
    console.print(Text(f"{tool_name} Context7 connection:", style="bold"))
    for token, method, label, description in options:
        option_line = Text()
        option_line.append(f"  {token}) ", style="bold cyan")
        option_line.append(label, style="bold")
        if method == default:
            option_line.append(" (Recommended)", style="green")
        console.print(option_line)
        console.print(Text(f"     {description}", style="dim"))

    while True:
        response = console.prompt_text("Choose 1 or 2", default=default_token)
        selected_method = option_by_token.get(response.strip().lower())
        if selected_method is not None:
            return selected_method
        print_warning(console, "Choose 1 or 2 to continue.")


def _run_ai_tools_setup_wizard(
    *,
    defaults: AiToolsInstallDefaults,
    context7_api_key_present: bool,
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

    context7_applicable = resolved_manage_claude_code or resolved_manage_codex
    resolved_enable_context7 = False
    if context7_applicable:
        resolved_enable_context7 = _prompt_bool(
            console,
            "Enable optional Context7 integration?",
            default=True,
        )

    resolved_claude_context7_method = "remote"
    resolved_codex_context7_method = "remote"
    if resolved_enable_context7:
        if resolved_manage_claude_code:
            resolved_claude_context7_method = _prompt_context7_method(
                console,
                "Claude Code",
                default="remote",
            )
        if resolved_manage_codex:
            resolved_codex_context7_method = _prompt_context7_method(
                console,
                "Codex CLI",
                default="remote",
            )

    options = AiToolsInstallOptions(
        manage_claude_code=resolved_manage_claude_code,
        manage_codex=resolved_manage_codex,
        manage_rtk=resolved_manage_rtk,
        enable_context7=resolved_enable_context7,
        claude_context7_method=resolved_claude_context7_method,
        codex_context7_method=resolved_codex_context7_method,
    )

    console.print()
    print_section_title(console, "AI Tools Setup Summary")
    for label, value in _build_ai_tools_setup_summary(
        options,
        context7_api_key_present=context7_api_key_present,
    ):
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
            context7_api_key_present=bool(os.environ.get("CONTEXT7_API_KEY")),
            console=console,
        )
        return AiToolsResolution(options=options, persist=True)

    if default_scope:
        # Non-interactive first run: fall back to tag-derived defaults without
        # prompting, and do not persist (the caller may be a script or CI run).
        context7_applicable = defaults.manage_claude_code or defaults.manage_codex
        options = _options_from_defaults(
            defaults,
            enable_context7=context7_applicable,
            claude_context7_method="remote",
            codex_context7_method="remote",
        )
        return AiToolsResolution(options=options)

    # Targeted task-tag run (claude_code / codex / rtk): tool selection comes from
    # the tags themselves, while Context7 preferences come from saved config.
    enable_context7 = (
        ai_tools_config.enable_context7 if ai_tools_config.configured else True
    )
    context7_applicable = defaults.manage_claude_code or defaults.manage_codex
    options = _options_from_defaults(
        defaults,
        enable_context7=enable_context7 and context7_applicable,
        claude_context7_method=(
            ai_tools_config.claude_context7_method
            if ai_tools_config.configured
            else "remote"
        ),
        codex_context7_method=(
            ai_tools_config.codex_context7_method
            if ai_tools_config.configured
            else "remote"
        ),
    )
    return AiToolsResolution(options=options)
