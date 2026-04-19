from __future__ import annotations

from unittest.mock import patch

from ..commands.install import resolve_ai_tools_install_options


def check_ai_tools_setup_wizard_flow() -> None:
    with (
        patch("scripts.commands.install.console.print"),
        patch(
            "scripts.commands.install.Confirm.ask",
            side_effect=[True, True, True, True, True],
        ),
        patch(
            "scripts.commands.install.Prompt.ask",
            side_effect=["1", "1"],
        ),
        patch(
            "builtins.input",
            side_effect=AssertionError(
                "expected smoke wizard flow to avoid direct builtins.input prompts"
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
