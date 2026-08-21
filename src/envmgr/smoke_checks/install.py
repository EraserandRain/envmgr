from __future__ import annotations

from unittest.mock import patch

from ..commands.shared import RichInstallConsole
from ..runtime_config import AiToolsConfig
from ..services.install_ai_tools import resolve_ai_tools_choices


def check_ai_tools_setup_wizard_flow() -> None:
    with (
        patch("envmgr.commands.shared.console.print"),
        patch(
            "envmgr.commands.shared.confirm_backend",
            side_effect=[True, True, True, True, True],
        ),
        patch(
            "envmgr.commands.shared.prompt_backend",
            side_effect=["1", "1"],
        ),
        patch(
            "builtins.input",
            side_effect=AssertionError(
                "expected smoke wizard flow to avoid direct builtins.input prompts"
            ),
        ),
    ):
        resolution = resolve_ai_tools_choices(
            ["ai_tools"],
            execution_playbook_path="workstation",
            ai_tools_config=AiToolsConfig.unconfigured_defaults(),
            interactive=True,
            console=RichInstallConsole(),
        )

    options = resolution.options
    if options is None:
        raise AssertionError("expected AI tools wizard to return options")
    if not resolution.persist:
        raise AssertionError("expected first-run wizard to request persistence")
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
