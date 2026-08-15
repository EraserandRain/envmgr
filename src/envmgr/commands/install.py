from __future__ import annotations

import sys

from ..services.install import InstallOptions, install
from ..services.runtime import popen_runtime_subprocess
from .shared import RichInstallConsole


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
    """Run `envmgr install` by assembling InstallOptions at the CLI boundary."""
    options = InstallOptions(
        list_tags=list_tags,
        dry_run=dry_run,
        json_output=json_output,
        playbook=playbook,
        inventory=inventory,
        ask_vault_pass=ask_vault_pass,
        interactive=sys.stdin.isatty() and sys.stdout.isatty(),
        manage_claude_code=manage_claude_code,
        manage_codex=manage_codex,
        manage_rtk=manage_rtk,
        enable_context7=enable_context7,
        claude_context7_method=claude_context7_method,
        codex_context7_method=codex_context7_method,
    )
    install(
        tags,
        options=options,
        console=RichInstallConsole(),
        process_factory=popen_runtime_subprocess,
    )
