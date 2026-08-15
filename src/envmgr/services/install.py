from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import NoReturn, Protocol, TextIO

import typer
from rich.text import Text

from ..catalog import CatalogError
from ..runtime_config import ConfigError
from .console import (
    InstallConsole,
    print_bullet_list,
    print_labeled_value,
    print_section_title,
    print_warning,
)
from .install_ai_tools import (
    AI_TOOLS_CONTEXT7_METHODS,
    AiToolsInstallDefaults,
    AiToolsInstallOptions,
    WizardCancelled,
    build_ai_tools_extra_vars,
    build_ai_tools_install_defaults,
    resolve_ai_tools_choices,
    resolve_noninteractive_ai_tools_install_options,
)
from .install_command import (
    InstallPlan,
    build_install_command,
    build_install_plan,
    cleanup_install_plan,
)
from .install_playbooks import (
    DEFAULT_PLAYBOOKS,
    build_execution_playbook,
    get_existing_default_playbooks,
    playbook_includes_role,
    read_playbook_role_name,
    read_playbook_role_tags,
    resolve_default_playbook_path,
    resolve_install_playbook,
    resolve_playbook_file_reference,
    resolve_selected_role_metadata,
)
from .install_tags import (
    ALL_TAG,
    is_all_tag_selection,
    load_available_tags,
    normalize_selected_tags,
    validate_selected_tags,
)
from .runtime import require_setup_completed

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


@dataclass(frozen=True)
class InstallOptions:
    """Everything a caller must know to run one Install besides the tags."""

    list_tags: bool = False
    dry_run: bool = False
    json_output: bool = False
    playbook: str | None = None
    inventory: str | None = None
    ask_vault_pass: bool = False
    interactive: bool = False
    manage_claude_code: bool | None = None
    manage_codex: bool | None = None
    manage_rtk: bool | None = None
    enable_context7: bool | None = None
    claude_context7_method: str | None = None
    codex_context7_method: str | None = None


class InstallProcess(Protocol):
    """The process surface Install consumes at its execution seam."""

    stdout: TextIO | None

    def wait(self, timeout: float | None = None) -> int: ...
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...


ProcessFactory = Callable[..., InstallProcess]


def _exit_with_error(
    console: InstallConsole,
    message: str,
    *,
    code: int = 1,
) -> NoReturn:
    """Print a user-facing error and exit with a shell-friendly status code."""
    console.error(message)
    raise typer.Exit(code=code)


def _load_available_tags(
    console: InstallConsole,
) -> tuple[list[str], list[str]]:
    """Load role/task tags and surface catalog failures through the console."""
    try:
        return load_available_tags()
    except CatalogError as error:
        _exit_with_error(console, f"Metadata error: {error}")


def print_builtin_scenarios(console: InstallConsole) -> None:
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


def _render_ai_tools_summary(
    console: InstallConsole,
    ai_tools_options: AiToolsInstallOptions | None,
) -> None:
    if ai_tools_options is None:
        return

    print_labeled_value(
        console,
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
        print_labeled_value(console, "Context7", context7_status)
    if ai_tools_options.enable_context7:
        if ai_tools_options.manage_claude_code:
            print_labeled_value(
                console,
                "Claude Code Context7 method",
                ai_tools_options.claude_context7_method,
            )
        if ai_tools_options.manage_codex:
            print_labeled_value(
                console,
                "Codex Context7 method",
                ai_tools_options.codex_context7_method,
            )
        if not os.environ.get("CONTEXT7_API_KEY"):
            print_labeled_value(
                console,
                "Context7 API key",
                "not set (continuing without it)",
            )


def _print_install_plan_summary(
    console: InstallConsole,
    *,
    title: str,
    install_plan: InstallPlan,
    ask_vault_pass: bool,
    ai_tools_options: AiToolsInstallOptions | None,
    command: list[str],
    show_execution_details: bool = False,
) -> None:
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


def _print_ignored_ai_tools_flags_warning(
    console: InstallConsole,
    *,
    json_output: bool,
) -> None:
    if json_output:
        console.warn(f"Warning: {IGNORED_AI_TOOLS_FLAGS_WARNING}")
        return

    print_warning(console, IGNORED_AI_TOOLS_FLAGS_WARNING)


def install(
    tags: list[str],
    *,
    options: InstallOptions,
    console: InstallConsole,
    process_factory: ProcessFactory,
) -> None:
    """Install and configure envmgr through the console/process seam."""
    if options.list_tags:
        if options.dry_run or options.json_output:
            _exit_with_error(
                console,
                "Error: --dry-run and --json cannot be used with --list-tags",
            )
        role_tags, task_tags = _load_available_tags(console)
        print_section_title(console, "Envmgr available tags:")
        print_builtin_scenarios(console)
        print_bullet_list(console, "Role level tags:", role_tags)
        print_bullet_list(console, "Task level tags:", task_tags)
        return
    if options.json_output and not options.dry_run:
        _exit_with_error(
            console,
            "Error: --json is only supported with install --dry-run",
        )

    try:
        selected_tags = normalize_selected_tags(list(tags))
    except CatalogError as error:
        _exit_with_error(console, f"Error: {error}")

    if not selected_tags:
        _exit_with_error(console, "Error: no tags selected for execution")

    role_tags, task_tags = _load_available_tags(console)
    try:
        validate_selected_tags(
            selected_tags,
            role_tags=role_tags,
            task_tags=task_tags,
        )
    except CatalogError as error:
        _exit_with_error(console, f"Error: {error}")

    require_setup_completed("install")

    try:
        install_plan = build_install_plan(
            selected_tags,
            explicit_playbook=options.playbook,
            inventory_reference=options.inventory,
            role_tags=role_tags,
            task_tags=task_tags,
        )
    except (CatalogError, ConfigError) as error:
        _exit_with_error(console, f"Error: {error}")

    ai_tools_flags_provided = any(
        value is not None
        for value in (
            options.manage_claude_code,
            options.manage_codex,
            options.manage_rtk,
            options.enable_context7,
            options.claude_context7_method,
            options.codex_context7_method,
        )
    )
    use_ai_tools_wizard = (
        options.interactive and not ai_tools_flags_provided and not options.dry_run
    )

    process: InstallProcess | None = None
    try:
        ai_tools_options = resolve_ai_tools_choices(
            install_plan.selected_tags,
            execution_playbook_path=install_plan.execution_playbook_path,
            manage_claude_code=options.manage_claude_code,
            manage_codex=options.manage_codex,
            manage_rtk=options.manage_rtk,
            enable_context7=options.enable_context7,
            claude_context7_method=options.claude_context7_method,
            codex_context7_method=options.codex_context7_method,
            interactive=use_ai_tools_wizard,
            console=console,
        )
    except WizardCancelled as error:
        console.print(Text(str(error), style="yellow"))
        cleanup_install_plan(install_plan)
        return
    except CatalogError as error:
        cleanup_install_plan(install_plan)
        _exit_with_error(console, f"Error: {error}")
    except typer.Exit:
        cleanup_install_plan(install_plan)
        raise

    try:
        if not install_plan.ai_tools_defaults.applicable and ai_tools_flags_provided:
            _print_ignored_ai_tools_flags_warning(
                console,
                json_output=options.json_output,
            )

        effective_ask_vault_pass = (
            options.ask_vault_pass or install_plan.default_ask_vault_pass
        )
        command = build_install_command(
            install_plan,
            ask_vault_pass=effective_ask_vault_pass,
            ai_tools_options=ai_tools_options,
        )

        if options.dry_run:
            if options.json_output:
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
                    console,
                    title="Install dry run:",
                    install_plan=install_plan,
                    ask_vault_pass=effective_ask_vault_pass,
                    ai_tools_options=ai_tools_options,
                    command=command,
                    show_execution_details=True,
                )
            return

        _print_install_plan_summary(
            console,
            title="Running Ansible playbook with:",
            install_plan=install_plan,
            ask_vault_pass=effective_ask_vault_pass,
            ai_tools_options=ai_tools_options,
            command=command,
        )

        process = process_factory(
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
            _exit_with_error(
                console,
                "Install failed with exit code "
                f"{return_code}. Next: review the Ansible output above or "
                f"{install_plan.runtime_paths.ansible_log_file}.",
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


__all__ = [
    "AI_TOOLS_CONTEXT7_METHODS",
    "ALL_TAG",
    "BUILTIN_SCENARIOS",
    "DEFAULT_PLAYBOOKS",
    "AiToolsInstallDefaults",
    "AiToolsInstallOptions",
    "InstallConsole",
    "InstallOptions",
    "InstallPlan",
    "InstallProcess",
    "ProcessFactory",
    "WizardCancelled",
    "build_ai_tools_extra_vars",
    "build_ai_tools_install_defaults",
    "build_execution_playbook",
    "build_install_command",
    "build_install_plan",
    "cleanup_install_plan",
    "get_existing_default_playbooks",
    "install",
    "is_all_tag_selection",
    "load_available_tags",
    "normalize_selected_tags",
    "playbook_includes_role",
    "read_playbook_role_name",
    "read_playbook_role_tags",
    "resolve_ai_tools_choices",
    "resolve_default_playbook_path",
    "resolve_install_playbook",
    "resolve_noninteractive_ai_tools_install_options",
    "resolve_playbook_file_reference",
    "resolve_selected_role_metadata",
    "validate_selected_tags",
]
