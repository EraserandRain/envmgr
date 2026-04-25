from __future__ import annotations

from typing import Annotated

import typer

from ..services.self_management import (
    SelfManagementError,
    load_installer_state,
    uninstall_installer_managed_envmgr,
    update_installer_managed_envmgr,
)
from .shared import (
    confirm_choice,
    exit_with_error,
    print_command_heading,
    print_status,
    print_summary_line,
)

HELP_CONTEXT_SETTINGS = {"help_option_names": ["--help", "-h"]}
SELF_OPTIONS_HELP_PANEL = "Self-management options"

self_app = typer.Typer(
    help="Manage installer-managed envmgr releases.",
    no_args_is_help=True,
    add_completion=False,
    suggest_commands=True,
    rich_markup_mode="rich",
    context_settings=HELP_CONTEXT_SETTINGS,
)


@self_app.callback()
def _self_callback() -> None:
    """Manage installer-managed envmgr releases."""


@self_app.command("update", context_settings=HELP_CONTEXT_SETTINGS)
def _update_command(
    version: Annotated[
        str | None,
        typer.Option(
            "--version",
            help=(
                "Update to a specific GitHub Release version, for example "
                "0.1.0 or v0.1.0."
            ),
            rich_help_panel=SELF_OPTIONS_HELP_PANEL,
        ),
    ] = None,
) -> None:
    """Update an install.sh-managed GitHub Release install."""
    print_command_heading("Envmgr Self Update")
    try:
        result = update_installer_managed_envmgr(requested_version=version)
    except SelfManagementError as error:
        exit_with_error(f"Error: {error}")

    print_summary_line("Installed release", result.state.release_tag)
    print_summary_line("Wheel URL", result.state.wheel_url)
    print_summary_line("Installer state", result.state.state_file)
    print_status(f"Verified envmgr: {result.version_output}", tone="success")
    print_status("Self update completed successfully.", tone="success")


@self_app.command("uninstall", context_settings=HELP_CONTEXT_SETTINGS)
def _uninstall_command(
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Uninstall without prompting for confirmation.",
            rich_help_panel=SELF_OPTIONS_HELP_PANEL,
        ),
    ] = False,
) -> None:
    """Uninstall envmgr while keeping runtime data under ~/.envmgr."""
    print_command_heading("Envmgr Self Uninstall")
    try:
        state = load_installer_state()
    except SelfManagementError as error:
        exit_with_error(f"Error: {error}")

    if not yes:
        confirmed = confirm_choice(
            "Uninstall envmgr from the uv tool environment and keep runtime data?",
            default=False,
        )
        if not confirmed:
            print_status(
                "Self uninstall cancelled; no files were changed.", tone="warning"
            )
            raise typer.Exit(code=1)

    try:
        result = uninstall_installer_managed_envmgr(state)
    except SelfManagementError as error:
        exit_with_error(f"Error: {error}")

    print_summary_line("Removed installer state", result.state.state_file)
    print_summary_line("Kept runtime data", result.kept_runtime_home)
    print_status("Self uninstall completed successfully.", tone="success")
