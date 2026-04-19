from __future__ import annotations

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from ..commands.install import install, resolve_ai_tools_install_options
from ..runtime_config import ensure_runtime_layout
from ..services.install import AiToolsInstallDefaults, InstallPlan


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


def check_ai_tools_setup_wizard_flow() -> None:
    with patch(
        "builtins.input",
        side_effect=["", "y", "", "", "1", "1", ""],
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
        raise AssertionError("expected AI tools wizard to return options")
    if not options.manage_claude_code:
        raise AssertionError("expected wizard to keep Claude Code enabled")
    if not options.manage_codex:
        raise AssertionError("expected wizard to allow enabling Codex CLI")
    if not options.manage_rtk:
        raise AssertionError("expected wizard to keep RTK enabled by default")
    if not options.enable_context7:
        raise AssertionError("expected wizard to keep Context7 enabled")
    if options.claude_context7_method != "remote":
        raise AssertionError("expected wizard to select remote for Claude Code")
    if options.codex_context7_method != "remote":
        raise AssertionError("expected wizard to select remote for Codex CLI")


def check_install_rejects_unknown_tags_with_exit_code() -> None:
    captured_output = io.StringIO()

    with (
        patch("sys.stdout", new=captured_output),
        patch(
            "scripts.commands.install.load_available_tags",
            return_value=(["zsh"], ["codex"]),
        ),
    ):
        try:
            install(["does-not-exist"])
        except SystemExit as error:
            if error.code != 1:
                raise AssertionError(
                    "expected install to exit with code 1 for unknown tags"
                ) from error
        else:
            raise AssertionError("expected install to reject unknown tags")

    output = captured_output.getvalue()
    if "unknown tags: does-not-exist" not in output.lower():
        raise AssertionError("expected install to report the unknown tag")
    if "Use -l or --list-tags to see all available tags" not in output:
        raise AssertionError("expected install to suggest listing available tags")


def check_install_rejects_all_plus_other_tags() -> None:
    captured_output = io.StringIO()

    with patch("sys.stdout", new=captured_output):
        try:
            install(["all", "zsh"])
        except SystemExit as error:
            if error.code != 1:
                raise AssertionError(
                    "expected install to exit with code 1 for mixed all-tag selections"
                ) from error
        else:
            raise AssertionError("expected install to reject mixed all-tag selections")

    if "tag 'all' cannot be combined with other tags" not in captured_output.getvalue():
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
                install(["zsh", "--ask-vault-pass"])
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
