from __future__ import annotations

CLI_ROOT_COMMAND = "envmgr"
CLI_COMMAND_PREFIX = CLI_ROOT_COMMAND
CLI_APP_HELP = "Direct runtime commands for envmgr."


def render_cli_command(*parts: str) -> str:
    """Build a user-facing command string from the current CLI prefix."""
    command_parts = [CLI_COMMAND_PREFIX]
    command_parts.extend(part.strip() for part in parts if part.strip())
    return " ".join(command_parts)


SETUP_COMMAND = render_cli_command("setup")
SETUP_HINT = f"run `{SETUP_COMMAND}` first"
