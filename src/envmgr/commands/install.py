from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

import typer
from rich.text import Text

from ..catalog import CatalogError
from ..runtime_config import ConfigError
from ..services.install import (
    AiToolsInstallDefaults,
    AiToolsInstallOptions,
    InstallPlan,
    build_ai_tools_extra_vars,
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
    confirm_choice,
    console,
    error_console,
    exit_with_error,
    load_available_tags,
    print_bullet_list,
    print_labeled_value,
    print_section_title,
    print_warning,
    prompt_text,
    require_setup_completed,
)

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
IGNORED_AI_TOOLS_FLAGS_WARNING = (
    "AI-tools flags were ignored because this run does not include the ai_tools role"
)


class WizardCancelled(RuntimeError):
    """Raised when the interactive setup wizard is cancelled by the user."""


def _format_enabled_status(enabled: bool) -> Text:
    """Return a styled enabled/disabled label for setup summaries."""
    return Text("enabled", style="green") if enabled else Text("disabled", style="dim")


def prompt_bool(message: str, *, default: bool) -> bool:
    """Prompt for a yes/no decision and return the selected value."""
    return confirm_choice(message, default=default)


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

    while True:
        response = prompt_text("Choose 1 or 2", default=default_token).strip().lower()
        selected_method = option_by_token.get(response)
        if selected_method is not None:
            return selected_method
        print_warning("Choose 1 or 2 to continue.")


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
    print_section_title("AI Tools Setup")
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
    print_section_title("AI Tools Setup Summary")
    for label, value in build_ai_tools_setup_summary(
        options,
        context7_api_key_present=context7_api_key_present,
    ):
        print_labeled_value(label, value, prefix="- ")

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


def print_builtin_scenarios() -> None:
    """Render built-in scenario tokens alongside tag discovery output."""
    console.print()
    console.print(Text("Built-in scenarios:", style="bold"))
    for name, description in BUILTIN_SCENARIOS:
        console.print(Text(f"  - {name}: {description}"))


def _render_selected_tags(install_plan: InstallPlan) -> str | Text:
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


def _render_ai_tools_summary(ai_tools_options: AiToolsInstallOptions | None) -> None:
    if ai_tools_options is None:
        return

    print_labeled_value(
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
        context7_status = "enabled" if ai_tools_options.enable_context7 else "disabled"
        print_labeled_value("Context7", context7_status)
    if ai_tools_options.enable_context7:
        if ai_tools_options.manage_claude_code:
            print_labeled_value(
                "Claude Code Context7 method",
                ai_tools_options.claude_context7_method,
            )
        if ai_tools_options.manage_codex:
            print_labeled_value(
                "Codex Context7 method",
                ai_tools_options.codex_context7_method,
            )
        if not os.environ.get("CONTEXT7_API_KEY"):
            print_labeled_value(
                "Context7 API key",
                "not set (continuing without it)",
            )


def _print_install_plan_summary(
    *,
    title: str,
    install_plan: InstallPlan,
    ask_vault_pass: bool,
    ai_tools_options: AiToolsInstallOptions | None,
    command: list[str],
    show_execution_details: bool = False,
) -> None:
    console.print()
    print_section_title(title)
    print_labeled_value("Playbook", install_plan.source_playbook_path)
    if install_plan.execution_playbook_path != install_plan.source_playbook_path:
        print_labeled_value(
            "Execution playbook",
            install_plan.execution_playbook_path,
        )
    print_labeled_value(
        "Inventory",
        f"{install_plan.inventory_label} -> {install_plan.inventory_path}",
    )
    print_labeled_value("Tags", _render_selected_tags(install_plan))
    _render_ai_tools_summary(ai_tools_options)
    if show_execution_details:
        print_labeled_value("Ask vault pass", str(ask_vault_pass))
        print_labeled_value("Command", shlex.join(command))
    console.print()


def _install_plan_json(
    *,
    install_plan: InstallPlan,
    ask_vault_pass: bool,
    ai_tools_options: AiToolsInstallOptions | None,
    command: list[str],
) -> dict[str, object]:
    ai_tools: dict[str, object] = {"applicable": ai_tools_options is not None}
    if ai_tools_options is not None:
        ai_tools.update(
            {
                "manage_claude_code": ai_tools_options.manage_claude_code,
                "manage_codex": ai_tools_options.manage_codex,
                "manage_rtk": ai_tools_options.manage_rtk,
                "enable_context7": ai_tools_options.enable_context7,
                "claude_context7_method": ai_tools_options.claude_context7_method,
                "codex_context7_method": ai_tools_options.codex_context7_method,
                "extra_vars": build_ai_tools_extra_vars(ai_tools_options),
            }
        )

    return {
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


def _print_ignored_ai_tools_flags_warning(*, json_output: bool) -> None:
    if json_output:
        error_console.print(
            Text(f"Warning: {IGNORED_AI_TOOLS_FLAGS_WARNING}", style="yellow")
        )
        return

    print_warning(IGNORED_AI_TOOLS_FLAGS_WARNING)


def run_install(
    *,
    tags: list[str],
    list_tags: bool,
    dry_run: bool = False,
    json_output: bool = False,
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
        if dry_run or json_output:
            exit_with_error(
                "Error: --dry-run and --json cannot be used with --list-tags"
            )
        role_tags, task_tags = load_available_tags()
        print_section_title("Envmgr available tags:")
        print_builtin_scenarios()
        print_bullet_list("Role level tags:", role_tags)
        print_bullet_list("Task level tags:", task_tags)
        return
    if json_output and not dry_run:
        exit_with_error("Error: --json is only supported with install --dry-run")

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
    use_ai_tools_wizard = (
        interactive_ai_tools and not ai_tools_flags_provided and not dry_run
    )

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
    except typer.Exit:
        cleanup_install_plan(install_plan)
        raise

    try:
        if not install_plan.ai_tools_defaults.applicable and ai_tools_flags_provided:
            _print_ignored_ai_tools_flags_warning(json_output=json_output)

        effective_ask_vault_pass = ask_vault_pass or install_plan.default_ask_vault_pass
        command = build_install_command(
            install_plan,
            ask_vault_pass=effective_ask_vault_pass,
            ai_tools_options=ai_tools_options,
        )

        if dry_run:
            if json_output:
                typer.echo(
                    json.dumps(
                        _install_plan_json(
                            install_plan=install_plan,
                            ask_vault_pass=effective_ask_vault_pass,
                            ai_tools_options=ai_tools_options,
                            command=command,
                        ),
                        sort_keys=True,
                    )
                )
            else:
                _print_install_plan_summary(
                    title="Install dry run:",
                    install_plan=install_plan,
                    ask_vault_pass=effective_ask_vault_pass,
                    ai_tools_options=ai_tools_options,
                    command=command,
                    show_execution_details=True,
                )
            return

        _print_install_plan_summary(
            title="Running Ansible playbook with:",
            install_plan=install_plan,
            ask_vault_pass=effective_ask_vault_pass,
            ai_tools_options=ai_tools_options,
            command=command,
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
            exit_with_error(
                "Install failed with exit code "
                f"{return_code}. Next: review the Ansible output above or "
                f"{install_plan.runtime_paths.ansible_log_file}."
            )
    except KeyboardInterrupt as error:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                process.wait()
            except OSError:
                pass
        raise typer.Exit(code=130) from error
    finally:
        cleanup_install_plan(install_plan)
