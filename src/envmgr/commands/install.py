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
    )
    install(
        tags,
        options=options,
        console=RichInstallConsole(),
        process_factory=popen_runtime_subprocess,
    )
