from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import NoReturn

from rich.prompt import Confirm, Prompt
from rich.text import Text

from ..catalog import CatalogError
from ..runtime_config import ConfigError
from ..services.install import (
    AI_TOOLS_CONTEXT7_METHODS,
    AiToolsInstallDefaults,
    AiToolsInstallOptions,
    build_ai_tools_install_defaults,
    build_install_command,
    build_install_plan,
    cleanup_install_plan,
    is_all_tag_selection,
    normalize_selected_tags,
    resolve_noninteractive_ai_tools_install_options,
    validate_selected_tags,
)
from ..services.runtime import RuntimePopenProcess, popen_runtime_subprocess
from .shared import (
    console,
    exit_with_error,
    load_available_tags,
    print_warning,
    require_setup_completed,
)


class WizardCancelled(RuntimeError):
    """Raised when the interactive setup wizard is cancelled by the user."""


def _abort_prompt(error: KeyboardInterrupt) -> NoReturn:
    """Exit like the shared prompt helpers when an interactive prompt is interrupted."""
    console.print()
    raise SystemExit(130) from error


def _print_section_title(title: str, *, style: str = "bold cyan") -> None:
    """Render a simple, consistently styled install section heading."""
    console.print(Text(title, style=style))


def _print_bullet_list(title: str, values: list[str]) -> None:
    """Render a titled bullet list without changing the public text content."""
    console.print()
    console.print(Text(title, style="bold"))
    for value in values:
        console.print(Text(f"  - {value}"))


def _format_enabled_status(enabled: bool) -> Text:
    """Return a styled enabled/disabled label for setup summaries."""
    return Text("enabled", style="green") if enabled else Text("disabled", style="dim")


def _print_labeled_value(
    label: str,
    value: str | Text,
    *,
    prefix: str = "  ",
) -> None:
    """Render a label/value line while preserving the historical wording."""
    line = Text()
    line.append(f"{prefix}{label}: ", style="bold")
    if isinstance(value, Text):
        line.append_text(value)
    else:
        line.append(value)
    console.print(line)


def prompt_bool(message: str, *, default: bool) -> bool:
    """Prompt for a yes/no decision and return the selected value."""
    try:
        return bool(Confirm.ask(message, console=console, default=default))
    except EOFError:
        return default
    except KeyboardInterrupt as error:
        _abort_prompt(error)


def render_context7_method_label(method: str) -> str:
    """Return a user-facing label for a Context7 connection mode."""
    if method == "remote":
        return "Remote service"
    return "Local MCP process"


def prompt_context7_method(tool_name: str, *, default: str) -> str:
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

    try:
        response = Prompt.ask(
            "Choose 1 or 2",
            console=console,
            choices=list(option_by_token),
            case_sensitive=False,
            show_choices=False,
            default=default_token,
        )
    except EOFError:
        return default
    except KeyboardInterrupt as error:
        _abort_prompt(error)

    return option_by_token[response.lower()]


def build_ai_tools_setup_summary(
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
                    render_context7_method_label(options.claude_context7_method),
                )
            )
        if options.manage_codex:
            lines.append(
                (
                    "Codex CLI Context7",
                    render_context7_method_label(options.codex_context7_method),
                )
            )
        if not context7_api_key_present:
            lines.append(
                ("Context7 API key", "not set; envmgr will continue without it")
            )
    return lines


def run_ai_tools_setup_wizard(
    *,
    defaults: AiToolsInstallDefaults,
    manage_claude_code: bool | None,
    manage_codex: bool | None,
    manage_rtk: bool | None,
    enable_context7: bool | None,
    claude_context7_method: str | None,
    codex_context7_method: str | None,
    context7_api_key_present: bool,
) -> AiToolsInstallOptions:
    """Run the interactive AI tools setup wizard and return the selected options."""
    console.print()
    _print_section_title("AI Tools Setup")
    console.print("We'll help you choose which AI tools to install on this machine.")
    console.print(Text("Press Ctrl+C at any time to cancel.", style="dim"))

    while True:
        resolved_manage_claude_code = (
            defaults.manage_claude_code
            if manage_claude_code is None
            else manage_claude_code
        )
        resolved_manage_codex = (
            defaults.manage_codex if manage_codex is None else manage_codex
        )
        resolved_manage_rtk = defaults.manage_rtk if manage_rtk is None else manage_rtk

        if manage_claude_code is None:
            resolved_manage_claude_code = prompt_bool(
                "Install Claude Code?",
                default=defaults.manage_claude_code,
            )
        if manage_codex is None:
            resolved_manage_codex = prompt_bool(
                "Install Codex CLI?",
                default=defaults.manage_codex,
            )
        if manage_rtk is None:
            resolved_manage_rtk = prompt_bool(
                "Install RTK?",
                default=defaults.manage_rtk,
            )

        if resolved_manage_claude_code or resolved_manage_codex or resolved_manage_rtk:
            break

        if (
            manage_claude_code is not None
            or manage_codex is not None
            or manage_rtk is not None
        ):
            raise CatalogError(
                "AI tools selection disabled Claude Code, Codex CLI, and RTK; choose at least one tool"
            )

        print_warning("Select at least one tool to continue.")

    context7_applicable = resolved_manage_claude_code or resolved_manage_codex
    resolved_enable_context7 = False
    if context7_applicable:
        resolved_enable_context7 = True if enable_context7 is None else enable_context7
    if context7_applicable and enable_context7 is None:
        resolved_enable_context7 = prompt_bool(
            "Enable optional Context7 integration?",
            default=True,
        )

    resolved_claude_context7_method = (
        "remote" if claude_context7_method is None else claude_context7_method
    )
    resolved_codex_context7_method = (
        "remote" if codex_context7_method is None else codex_context7_method
    )

    if resolved_enable_context7:
        if resolved_manage_claude_code and claude_context7_method is None:
            resolved_claude_context7_method = prompt_context7_method(
                "Claude Code",
                default="remote",
            )
        if resolved_manage_codex and codex_context7_method is None:
            resolved_codex_context7_method = prompt_context7_method(
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
    _print_section_title("AI Tools Setup Summary")
    for label, value in build_ai_tools_setup_summary(
        options,
        context7_api_key_present=context7_api_key_present,
    ):
        _print_labeled_value(label, value, prefix="- ")

    if not prompt_bool("Install with these settings?", default=True):
        raise WizardCancelled("AI Tools Setup cancelled before installation.")

    return options


def resolve_ai_tools_install_options(
    selected_tags: list[str],
    *,
    execution_playbook_path: str,
    manage_claude_code: bool | None,
    manage_codex: bool | None,
    manage_rtk: bool | None,
    enable_context7: bool | None,
    claude_context7_method: str | None,
    codex_context7_method: str | None,
    interactive: bool,
) -> AiToolsInstallOptions | None:
    """Resolve AI-tools install choices from tags, flags, and interactive prompts."""
    defaults = build_ai_tools_install_defaults(
        selected_tags,
        execution_playbook_path=execution_playbook_path,
    )
    if not defaults.applicable:
        return None

    if interactive:
        return run_ai_tools_setup_wizard(
            defaults=defaults,
            manage_claude_code=manage_claude_code,
            manage_codex=manage_codex,
            manage_rtk=manage_rtk,
            enable_context7=enable_context7,
            claude_context7_method=claude_context7_method,
            codex_context7_method=codex_context7_method,
            context7_api_key_present=bool(os.environ.get("CONTEXT7_API_KEY")),
        )

    return resolve_noninteractive_ai_tools_install_options(
        defaults,
        manage_claude_code=manage_claude_code,
        manage_codex=manage_codex,
        manage_rtk=manage_rtk,
        enable_context7=enable_context7,
        claude_context7_method=claude_context7_method,
        codex_context7_method=codex_context7_method,
    )


def _build_install_parser() -> argparse.ArgumentParser:
    """Create the legacy install parser used by compatibility entrypoints."""
    from .legacy_argparse import build_command_parser

    parser = build_command_parser(
        "install", description="Install and Configure envmgr with ansible"
    )
    parser.add_argument("tags", nargs="*", help="List of tags: tag1 tag2 ...")
    parser.add_argument(
        "-l", "--list-tags", action="store_true", help="List all available tags"
    )
    parser.add_argument(
        "--playbook",
        help="Specify a playbook file explicitly when tags are ambiguous",
    )
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )
    parser.add_argument(
        "--ask-vault-pass", action="store_true", help="Ask for vault password"
    )
    parser.add_argument(
        "--claude-code",
        dest="ai_tools_manage_claude_code",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, explicitly install Claude Code",
    )
    parser.add_argument(
        "--no-claude-code",
        dest="ai_tools_manage_claude_code",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip Claude Code",
    )
    parser.add_argument(
        "--codex",
        dest="ai_tools_manage_codex",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, explicitly install Codex CLI",
    )
    parser.add_argument(
        "--no-codex",
        dest="ai_tools_manage_codex",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip Codex CLI",
    )
    parser.add_argument(
        "--rtk",
        dest="ai_tools_manage_rtk",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, explicitly install RTK",
    )
    parser.add_argument(
        "--no-rtk",
        dest="ai_tools_manage_rtk",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip RTK",
    )
    parser.add_argument(
        "--context7",
        dest="ai_tools_context7",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, enable Context7 integration",
    )
    parser.add_argument(
        "--no-context7",
        dest="ai_tools_context7",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip Context7 integration",
    )
    parser.add_argument(
        "--claude-context7-method",
        choices=AI_TOOLS_CONTEXT7_METHODS,
        help="Choose the Context7 transport for Claude Code",
    )
    parser.add_argument(
        "--codex-context7-method",
        choices=AI_TOOLS_CONTEXT7_METHODS,
        help="Choose the Context7 transport for Codex CLI",
    )
    return parser


def run_install(
    *,
    tags: list[str],
    list_tags: bool,
    playbook: str | None,
    inventory: str | None,
    ask_vault_pass: bool,
    manage_claude_code: bool | None,
    manage_codex: bool | None,
    manage_rtk: bool | None,
    enable_context7: bool | None,
    claude_context7_method: str | None,
    codex_context7_method: str | None,
) -> None:
    """Install and configure envmgr using explicit option values."""
    if list_tags:
        role_tags, task_tags = load_available_tags()
        _print_section_title("Envmgr available tags:")
        _print_bullet_list("Role level tags:", role_tags)
        _print_bullet_list("Task level tags:", task_tags)
        return

    try:
        selected_tags = normalize_selected_tags(list(tags))
    except CatalogError as error:
        exit_with_error(f"Error: {error}")

    if not selected_tags:
        exit_with_error("Error: no tags selected for execution")

    role_tags, task_tags = load_available_tags()
    try:
        validate_selected_tags(
            selected_tags,
            role_tags=role_tags,
            task_tags=task_tags,
        )
    except CatalogError as error:
        exit_with_error(f"Error: {error}")

    require_setup_completed("install")

    try:
        install_plan = build_install_plan(
            selected_tags,
            explicit_playbook=playbook,
            inventory_reference=inventory,
            role_tags=role_tags,
            task_tags=task_tags,
        )
    except (CatalogError, ConfigError) as error:
        exit_with_error(f"Error: {error}")

    interactive_ai_tools = sys.stdin.isatty() and sys.stdout.isatty()
    ai_tools_flags_provided = any(
        value is not None
        for value in (
            manage_claude_code,
            manage_codex,
            manage_rtk,
            enable_context7,
            claude_context7_method,
            codex_context7_method,
        )
    )
    use_ai_tools_wizard = interactive_ai_tools and not ai_tools_flags_provided

    process: RuntimePopenProcess | None = None
    try:
        ai_tools_options = resolve_ai_tools_install_options(
            install_plan.selected_tags,
            execution_playbook_path=install_plan.execution_playbook_path,
            manage_claude_code=manage_claude_code,
            manage_codex=manage_codex,
            manage_rtk=manage_rtk,
            enable_context7=enable_context7,
            claude_context7_method=claude_context7_method,
            codex_context7_method=codex_context7_method,
            interactive=use_ai_tools_wizard,
        )
    except WizardCancelled as error:
        console.print(Text(str(error), style="yellow"))
        cleanup_install_plan(install_plan)
        return
    except CatalogError as error:
        cleanup_install_plan(install_plan)
        exit_with_error(f"Error: {error}")

    try:
        if not install_plan.ai_tools_defaults.applicable and ai_tools_flags_provided:
            print_warning(
                "AI-tools flags were ignored because this run does not include the ai_tools role"
            )

        console.print()
        _print_section_title("Running Ansible playbook with:")
        _print_labeled_value("Playbook", install_plan.source_playbook_path)
        if install_plan.execution_playbook_path != install_plan.source_playbook_path:
            _print_labeled_value(
                "Execution playbook",
                install_plan.execution_playbook_path,
            )
        _print_labeled_value(
            "Inventory",
            f"{install_plan.inventory_label} -> {install_plan.inventory_path}",
        )
        if is_all_tag_selection(install_plan.selected_tags):
            _print_labeled_value(
                "Tags",
                Text("All tags will be executed", style="green"),
            )
        else:
            rendered_tags = Text()
            for index, tag in enumerate(install_plan.selected_tags):
                if index:
                    rendered_tags.append(" ")
                label = "Role" if tag in install_plan.role_tags else "Task"
                style = "green" if label == "Role" else "cyan"
                rendered_tags.append(f"[{label}: {tag}]", style=style)
            _print_labeled_value("Tags", rendered_tags)
        if ai_tools_options is not None:
            _print_labeled_value(
                "AI tools",
                (
                    "Claude Code="
                    f"{ai_tools_options.manage_claude_code}, "
                    "Codex CLI="
                    f"{ai_tools_options.manage_codex}, "
                    f"RTK={ai_tools_options.manage_rtk}"
                ),
            )
            if ai_tools_options.manage_claude_code or ai_tools_options.manage_codex:
                context7_status = (
                    "enabled" if ai_tools_options.enable_context7 else "disabled"
                )
                _print_labeled_value("Context7", context7_status)
            if ai_tools_options.enable_context7:
                if ai_tools_options.manage_claude_code:
                    _print_labeled_value(
                        "Claude Code Context7 method",
                        ai_tools_options.claude_context7_method,
                    )
                if ai_tools_options.manage_codex:
                    _print_labeled_value(
                        "Codex Context7 method",
                        ai_tools_options.codex_context7_method,
                    )
                if not os.environ.get("CONTEXT7_API_KEY"):
                    _print_labeled_value(
                        "Context7 API key",
                        "not set (continuing without it)",
                    )
        console.print()

        command = build_install_command(
            install_plan,
            ask_vault_pass=ask_vault_pass or install_plan.default_ask_vault_pass,
            ai_tools_options=ai_tools_options,
        )

        process = popen_runtime_subprocess(
            command,
            runtime_paths=install_plan.runtime_paths,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if process.stdout is not None:
            for line in process.stdout:
                print(line, end="")
            process.stdout.close()
        return_code = process.wait()
        if return_code != 0:
            raise SystemExit(return_code)
    except KeyboardInterrupt as error:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                process.wait()
            except OSError:
                pass
        raise SystemExit(130) from error
    finally:
        cleanup_install_plan(install_plan)


def install(argv: list[str] | None = None) -> None:
    """Install and configure the envmgr project using Ansible."""
    from .legacy_argparse import parse_command_args

    parser = _build_install_parser()
    args = parse_command_args(parser, argv)

    if not args.tags and not args.list_tags:
        parser.print_help()
        return

    run_install(
        tags=list(args.tags),
        list_tags=args.list_tags,
        playbook=args.playbook,
        inventory=args.inventory,
        ask_vault_pass=args.ask_vault_pass,
        manage_claude_code=args.ai_tools_manage_claude_code,
        manage_codex=args.ai_tools_manage_codex,
        manage_rtk=args.ai_tools_manage_rtk,
        enable_context7=args.ai_tools_context7,
        claude_context7_method=args.claude_context7_method,
        codex_context7_method=args.codex_context7_method,
    )
