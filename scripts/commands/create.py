from __future__ import annotations

from typing import Annotated

import typer

from ..command_text import CLI_ROOT_COMMAND
from ..scaffold import ScaffoldError, generate_role
from .dev_shared import require_repo_dev_context

COMMAND_NAME = "create"
app = typer.Typer(add_completion=False, rich_markup_mode="rich")


@app.command()
def _create_command(
    ctx: typer.Context,
    role: Annotated[
        str | None,
        typer.Argument(help="The name of the role to create"),
    ] = None,
) -> None:
    """Create a new Ansible role by generating the role directory."""
    require_repo_dev_context(COMMAND_NAME)

    if role is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    try:
        generate_role(role)
        typer.echo(f"Role '{role}' generated successfully.")
        typer.echo(
            f"Update roles/{role}/meta/envmgr.yml and add the role to the appropriate playbook."
        )
    except FileExistsError:
        typer.echo(f"Role '{role}' already exists.")
    except (FileNotFoundError, ScaffoldError) as error:
        typer.echo(str(error))


def create(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Create a new Ansible role using Typer-based argument parsing."""
    app(
        args=[] if argv is None else argv,
        prog_name=prog_name or f"{CLI_ROOT_COMMAND} {COMMAND_NAME}",
    )


def main() -> None:
    """Run the role scaffolding helper from its dedicated development command."""
    app(prog_name=COMMAND_NAME)
