from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from scripts.commands.install import (
    WizardCancelled,
    resolve_ai_tools_install_options,
    run_install,
)
from scripts.main import app
from scripts.runtime_config import ensure_runtime_layout
from scripts.services.install import (
    AiToolsInstallDefaults,
    InstallPlan,
    build_install_plan,
)

CLI_RUNNER = CliRunner()


class _FakeRuntimeProcess:
    """Minimal subprocess double for install command tests."""

    def __init__(self, output: str) -> None:
        self.stdout = StringIO(output)

    def wait(self) -> int:
        return 0

    def poll(self) -> int:
        return 0

    def terminate(self) -> None:
        raise AssertionError("terminate should not be called for a successful run")


def check_ai_tools_install_option_resolution() -> None:
    options = resolve_ai_tools_install_options(
        ["ai_tools"],
        execution_playbook_path="playbooks/workstation.yml",
        manage_claude_code=None,
        manage_codex=True,
        manage_rtk=None,
        enable_context7=False,
        claude_context7_method=None,
        codex_context7_method="remote",
        interactive=False,
    )

    if options is None:
        raise AssertionError("expected workstation AI tools playbook to resolve")
    if not options.manage_claude_code:
        raise AssertionError("expected ai_tools tag to keep Claude Code enabled")
    if not options.manage_codex:
        raise AssertionError("expected explicit Codex selection to be honored")
    if not options.manage_rtk:
        raise AssertionError("expected ai_tools tag to keep RTK enabled")
    if options.enable_context7:
        raise AssertionError("expected explicit Context7 disable to be honored")
    if options.codex_context7_method != "remote":
        raise AssertionError("expected Codex Context7 method override to be honored")

    rtk_only_options = resolve_ai_tools_install_options(
        ["rtk"],
        execution_playbook_path="playbooks/workstation.yml",
        manage_claude_code=None,
        manage_codex=None,
        manage_rtk=None,
        enable_context7=None,
        claude_context7_method=None,
        codex_context7_method=None,
        interactive=False,
    )
    if rtk_only_options is None:
        raise AssertionError("expected rtk task tag to resolve AI tools options")
    if not rtk_only_options.manage_rtk:
        raise AssertionError("expected rtk task tag to enable RTK")
    if rtk_only_options.enable_context7:
        raise AssertionError("expected RTK-only installs to skip Context7")

    node_options = resolve_ai_tools_install_options(
        ["all"],
        execution_playbook_path="playbooks/node.yml",
        manage_claude_code=None,
        manage_codex=None,
        manage_rtk=None,
        enable_context7=None,
        claude_context7_method=None,
        codex_context7_method=None,
        interactive=False,
    )
    if node_options is not None:
        raise AssertionError("expected node playbook to skip AI tools resolution")


def check_ai_tools_setup_wizard_uses_rich_prompt_path() -> None:
    with (
        patch("scripts.commands.install.console.print"),
        patch(
            "scripts.commands.install.Confirm.ask",
            side_effect=[True, True, True, True, True],
        ) as mock_confirm,
        patch(
            "scripts.commands.install.Prompt.ask",
            side_effect=["1", "1"],
        ) as mock_prompt,
        patch(
            "builtins.input",
            side_effect=AssertionError(
                "expected AI tools wizard to avoid direct builtins.input prompts"
            ),
        ),
    ):
        options = resolve_ai_tools_install_options(
            ["ai_tools"],
            execution_playbook_path="playbooks/workstation.yml",
            manage_claude_code=None,
            manage_codex=None,
            manage_rtk=None,
            enable_context7=None,
            claude_context7_method=None,
            codex_context7_method=None,
            interactive=True,
        )

    if options is None:
        raise AssertionError("expected AI tools wizard to return install options")
    if mock_confirm.call_count != 5:
        raise AssertionError("expected Rich Confirm prompts for each yes/no question")
    if mock_prompt.call_count != 2:
        raise AssertionError(
            "expected Rich Prompt prompts for each Context7 transport choice"
        )
    if not options.manage_codex:
        raise AssertionError("expected wizard to allow enabling Codex CLI")
    if options.claude_context7_method != "remote":
        raise AssertionError("expected wizard to accept remote transport selections")
    if options.codex_context7_method != "remote":
        raise AssertionError("expected wizard to accept remote transport selections")


def check_install_all_uses_runtime_default_playbook() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = ensure_runtime_layout(envmgr_home)
        runtime_paths.config_file.write_text(
            """
[default]
inventory = "default"
playbook = "node"
ask_vault_pass = false

[inventory]
default = "inventory/default.yaml"
remote = "inventory/remote.yaml"
password = "inventory/password.yaml"
""".lstrip(),
            encoding="utf-8",
        )

        install_plan = build_install_plan(
            ["all"],
            explicit_playbook=None,
            inventory_reference=None,
            role_tags=[],
            task_tags=[],
            envmgr_home=envmgr_home,
        )

        if install_plan.source_playbook_path != "playbooks/node.yml":
            raise AssertionError(
                "expected `install all` to use the runtime default playbook"
            )
        if install_plan.execution_playbook_path != "playbooks/node.yml":
            raise AssertionError(
                "expected `install all` to execute the resolved default playbook"
            )
        if install_plan.uses_temporary_execution_playbook:
            raise AssertionError(
                "expected `install all` to skip temporary execution playbooks"
            )
        if install_plan.inventory_path != runtime_paths.default_inventory_file:
            raise AssertionError(
                "expected `install all` to keep using the default inventory alias"
            )


def check_install_list_tags_uses_rich_console() -> None:
    with (
        patch(
            "scripts.commands.install.load_available_tags",
            return_value=(["init"], ["codex", "rtk"]),
        ),
        patch("scripts.commands.install.console.print") as mock_console_print,
        patch("builtins.print") as mock_print,
    ):
        run_install(
            tags=[],
            list_tags=True,
            playbook=None,
            inventory=None,
            ask_vault_pass=False,
            manage_claude_code=None,
            manage_codex=None,
            manage_rtk=None,
            enable_context7=None,
            claude_context7_method=None,
            codex_context7_method=None,
        )

    if mock_print.called:
        raise AssertionError("expected list-tags flow to avoid plain print calls")

    output = "\n".join(
        "" if not call.args else str(call.args[0])
        for call in mock_console_print.call_args_list
    )
    for expected_fragment in (
        "Envmgr available tags:",
        "Role level tags:",
        "Task level tags:",
        "  - init",
        "  - codex",
        "  - rtk",
    ):
        if expected_fragment not in output:
            raise AssertionError(
                f"expected list-tags Rich output to include {expected_fragment!r}"
            )


def check_install_rejects_unknown_tags_with_exit_code() -> None:
    with (
        patch("scripts.commands.shared.error_console.print") as mock_error_print,
        patch(
            "scripts.commands.install.load_available_tags",
            return_value=(["zsh"], ["codex"]),
        ),
    ):
        try:
            run_install(
                tags=["does-not-exist"],
                list_tags=False,
                playbook=None,
                inventory=None,
                ask_vault_pass=False,
                manage_claude_code=None,
                manage_codex=None,
                manage_rtk=None,
                enable_context7=None,
                claude_context7_method=None,
                codex_context7_method=None,
            )
        except typer.Exit as error:
            if error.exit_code != 1:
                raise AssertionError(
                    "expected install to exit with code 1 for unknown tags"
                ) from error
        else:
            raise AssertionError("expected install to reject unknown tags")

    output = mock_error_print.call_args.args[0]
    if "unknown tags: does-not-exist" not in output.lower():
        raise AssertionError("expected install to report the unknown tag")
    if "Use -l or --list-tags to see all available tags" not in output:
        raise AssertionError("expected install to suggest listing available tags")


def check_install_summary_uses_rich_console_and_keeps_raw_subprocess_output() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
        execution_playbook_path = Path(temp_dir) / "execution.yml"
        execution_playbook_path.write_text("---\n", encoding="utf-8")
        install_plan = InstallPlan(
            selected_tags=["zsh"],
            role_tags=["zsh"],
            task_tags=[],
            source_playbook_path="playbooks/workstation.yml",
            execution_playbook_path=str(execution_playbook_path),
            uses_temporary_execution_playbook=True,
            inventory_path=runtime_paths.default_inventory_file,
            inventory_label="default",
            runtime_paths=runtime_paths,
            default_ask_vault_pass=False,
            ai_tools_defaults=AiToolsInstallDefaults(
                applicable=False,
                manage_claude_code=False,
                manage_codex=False,
                manage_rtk=False,
            ),
        )
        process = _FakeRuntimeProcess("PLAY [all]\nok: [localhost]\n")

        with (
            patch(
                "scripts.commands.install.load_available_tags",
                return_value=(["zsh"], []),
            ),
            patch("scripts.commands.install.require_setup_completed"),
            patch(
                "scripts.commands.install.build_install_plan",
                return_value=install_plan,
            ),
            patch(
                "scripts.commands.install.resolve_ai_tools_install_options",
                return_value=None,
            ),
            patch(
                "scripts.commands.install.build_install_command",
                return_value=["ansible-playbook", "playbooks/workstation.yml"],
            ),
            patch(
                "scripts.commands.install.popen_runtime_subprocess",
                return_value=process,
            ),
            patch("scripts.commands.install.console.print") as mock_console_print,
            patch("builtins.print") as mock_print,
        ):
            run_install(
                tags=["zsh"],
                list_tags=False,
                playbook=None,
                inventory=None,
                ask_vault_pass=False,
                manage_claude_code=None,
                manage_codex=True,
                manage_rtk=None,
                enable_context7=None,
                claude_context7_method=None,
                codex_context7_method=None,
            )

        output = "\n".join(
            "" if not call.args else str(call.args[0])
            for call in mock_console_print.call_args_list
        )
        for expected_fragment in (
            "Warning: AI-tools flags were ignored because this run does not include the ai_tools role",
            "Running Ansible playbook with:",
            "  Playbook: playbooks/workstation.yml",
            "  Inventory: default ->",
            "  Tags: [Role: zsh]",
        ):
            if expected_fragment not in output:
                raise AssertionError(
                    f"expected Rich install summary to include {expected_fragment!r}"
                )
        if "PLAY [all]" in output or "ok: [localhost]" in output:
            raise AssertionError(
                "expected live subprocess output to stay out of Rich summary rendering"
            )

        raw_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
        if raw_lines != ["PLAY [all]\n", "ok: [localhost]\n"]:
            raise AssertionError(
                "expected subprocess output to keep streaming through raw print passthrough"
            )
        for call in mock_print.call_args_list:
            if call.kwargs.get("end") != "":
                raise AssertionError(
                    "expected subprocess passthrough to preserve print(..., end='')"
                )


def check_install_wizard_cancellation_reports_via_rich_console() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
        execution_playbook_path = Path(temp_dir) / "execution.yml"
        execution_playbook_path.write_text("---\n", encoding="utf-8")
        install_plan = InstallPlan(
            selected_tags=["ai_tools"],
            role_tags=["ai_tools"],
            task_tags=[],
            source_playbook_path="playbooks/workstation.yml",
            execution_playbook_path=str(execution_playbook_path),
            uses_temporary_execution_playbook=True,
            inventory_path=runtime_paths.default_inventory_file,
            inventory_label="default",
            runtime_paths=runtime_paths,
            default_ask_vault_pass=False,
            ai_tools_defaults=AiToolsInstallDefaults(
                applicable=True,
                manage_claude_code=True,
                manage_codex=False,
                manage_rtk=True,
            ),
        )

        with (
            patch(
                "scripts.commands.install.load_available_tags",
                return_value=(["ai_tools"], []),
            ),
            patch("scripts.commands.install.require_setup_completed"),
            patch(
                "scripts.commands.install.build_install_plan",
                return_value=install_plan,
            ),
            patch(
                "scripts.commands.install.resolve_ai_tools_install_options",
                side_effect=WizardCancelled(
                    "AI Tools Setup cancelled before installation."
                ),
            ),
            patch("scripts.commands.install.cleanup_install_plan") as mock_cleanup,
            patch("scripts.commands.install.console.print") as mock_console_print,
            patch("builtins.print") as mock_print,
        ):
            try:
                run_install(
                    tags=["ai_tools"],
                    list_tags=False,
                    playbook=None,
                    inventory=None,
                    ask_vault_pass=False,
                    manage_claude_code=None,
                    manage_codex=None,
                    manage_rtk=None,
                    enable_context7=None,
                    claude_context7_method=None,
                    codex_context7_method=None,
                )
            except WizardCancelled as error:
                raise AssertionError(
                    "expected wizard cancellation to be handled without bubbling"
                ) from error

        if mock_print.called:
            raise AssertionError(
                "expected wizard cancellation messaging to avoid plain print calls"
            )
        mock_cleanup.assert_called_once_with(install_plan)
        output = "\n".join(
            "" if not call.args else str(call.args[0])
            for call in mock_console_print.call_args_list
        )
        if "AI Tools Setup cancelled before installation." not in output:
            raise AssertionError(
                "expected wizard cancellation messaging to stay user-friendly"
            )


def check_install_rejects_all_plus_other_tags() -> None:
    with patch("scripts.commands.shared.error_console.print") as mock_error_print:
        try:
            run_install(
                tags=["all", "zsh"],
                list_tags=False,
                playbook=None,
                inventory=None,
                ask_vault_pass=False,
                manage_claude_code=None,
                manage_codex=None,
                manage_rtk=None,
                enable_context7=None,
                claude_context7_method=None,
                codex_context7_method=None,
            )
        except typer.Exit as error:
            if error.exit_code != 1:
                raise AssertionError(
                    "expected install to exit with code 1 for mixed all-tag selections"
                ) from error
        else:
            raise AssertionError("expected install to reject mixed all-tag selections")

    message = mock_error_print.call_args.args[0]
    if "tag 'all' cannot be combined with other tags" not in message:
        raise AssertionError(
            "expected install to explain that `all` cannot be mixed with other tags"
        )


def check_install_interrupt_exits_cleanly() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
        execution_playbook_path = Path(temp_dir) / "execution.yml"
        execution_playbook_path.write_text("---\n", encoding="utf-8")
        install_plan = InstallPlan(
            selected_tags=["zsh"],
            role_tags=["zsh"],
            task_tags=[],
            source_playbook_path="playbooks/workstation.yml",
            execution_playbook_path=str(execution_playbook_path),
            uses_temporary_execution_playbook=True,
            inventory_path=runtime_paths.default_inventory_file,
            inventory_label="default",
            runtime_paths=runtime_paths,
            default_ask_vault_pass=False,
            ai_tools_defaults=AiToolsInstallDefaults(
                applicable=False,
                manage_claude_code=False,
                manage_codex=False,
                manage_rtk=False,
            ),
        )

        with (
            patch("scripts.commands.install.require_setup_completed"),
            patch(
                "scripts.commands.install.build_install_plan", return_value=install_plan
            ),
            patch(
                "scripts.commands.install.resolve_ai_tools_install_options",
                return_value=None,
            ),
            patch(
                "scripts.commands.install.popen_runtime_subprocess",
                side_effect=KeyboardInterrupt,
            ),
        ):
            try:
                run_install(
                    tags=["zsh"],
                    list_tags=False,
                    playbook=None,
                    inventory=None,
                    ask_vault_pass=True,
                    manage_claude_code=None,
                    manage_codex=None,
                    manage_rtk=None,
                    enable_context7=None,
                    claude_context7_method=None,
                    codex_context7_method=None,
                )
            except SystemExit as error:
                if error.code != 130:
                    raise AssertionError(
                        "expected install to exit with code 130 on Ctrl+C"
                    ) from error
            else:
                raise AssertionError("expected install to exit on Ctrl+C")

        if execution_playbook_path.exists():
            raise AssertionError(
                "expected install to clean up temporary execution playbooks on Ctrl+C"
            )


def check_install_typer_flags_preserve_tri_state_bools() -> None:
    captured_calls: list[dict[str, object]] = []

    def _capture_run_install(**kwargs: object) -> None:
        captured_calls.append(kwargs)

    with patch("scripts.main.run_install", side_effect=_capture_run_install):
        default_result = CLI_RUNNER.invoke(
            app,
            ["install", "ai_tools"],
            prog_name="envmgr",
        )
        flagged_result = CLI_RUNNER.invoke(
            app,
            [
                "install",
                "ai_tools",
                "--no-claude-code",
                "--codex",
                "--no-rtk",
                "--context7",
                "--claude-context7-method",
                "local",
                "--codex-context7-method",
                "remote",
            ],
            prog_name="envmgr",
        )

    if default_result.exit_code != 0:
        raise AssertionError(
            "expected bare `envmgr install ai_tools` invocation to parse successfully"
            f"\noutput:\n{default_result.output}"
        )
    if flagged_result.exit_code != 0:
        raise AssertionError(
            "expected paired install flags to parse successfully"
            f"\noutput:\n{flagged_result.output}"
        )
    if len(captured_calls) != 2:
        raise AssertionError("expected Typer install wrapper to delegate twice")

    default_call, flagged_call = captured_calls
    for option_name in (
        "manage_claude_code",
        "manage_codex",
        "manage_rtk",
        "enable_context7",
        "claude_context7_method",
        "codex_context7_method",
    ):
        if default_call[option_name] is not None:
            raise AssertionError(
                f"expected {option_name} to stay unset when no install flags are provided"
            )

    expected_flag_values = {
        "manage_claude_code": False,
        "manage_codex": True,
        "manage_rtk": False,
        "enable_context7": True,
        "claude_context7_method": "local",
        "codex_context7_method": "remote",
    }
    for option_name, expected_value in expected_flag_values.items():
        if flagged_call[option_name] != expected_value:
            raise AssertionError(
                f"expected {option_name} to resolve to {expected_value!r}"
            )
