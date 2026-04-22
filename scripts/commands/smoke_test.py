from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..command_text import CLI_ROOT_COMMAND
from ..runtime_config import ensure_runtime_layout
from ..smoke_checks import iter_smoke_tests
from .dev_shared import require_repo_dev_context, run_assertion_step, run_command_step
from .shared import require_setup_completed, resolve_inventory_option

COMMAND_NAME = "smoke-test"
app = typer.Typer(add_completion=False, rich_markup_mode="rich")


def run_smoke_test(*, inventory: str | None, playbooks: list[str] | None) -> None:
    """Run lightweight integration checks without installing software."""
    require_repo_dev_context(COMMAND_NAME)
    require_setup_completed(COMMAND_NAME)

    selected_playbooks = playbooks or [
        playbook
        for playbook in ["playbooks/workstation.yml", "playbooks/node.yml"]
        if Path(playbook).exists()
    ]
    inventory_path, _inventory_label = resolve_inventory_option(inventory)
    runtime_paths = ensure_runtime_layout()

    print("Running smoke tests...")

    results = [
        run_assertion_step(step_name, test.debug)
        for step_name, test in iter_smoke_tests()
    ]

    if not selected_playbooks:
        print("No playbooks selected for smoke checks.")

    for playbook in selected_playbooks:
        if not Path(playbook).exists():
            print(f"✗ list-tags failed because playbook was not found: {playbook}")
            results.append(False)
            continue
        results.append(
            run_command_step(
                f"list-tags {playbook}",
                [
                    "ansible-playbook",
                    "-i",
                    str(inventory_path),
                    playbook,
                    "--list-tags",
                ],
                runtime_paths=runtime_paths,
            )
        )

    if all(results):
        print("\n✓ Smoke tests passed")
        return

    print("\n✗ Smoke tests failed")
    raise SystemExit(1)


@app.command()
def _smoke_test_command(
    inventory: Annotated[
        str | None,
        typer.Option(
            "--inventory",
            "-i",
            help="Specify an inventory alias from ~/.envmgr/config.toml",
        ),
    ] = None,
    playbook: Annotated[
        list[str] | None,
        typer.Option(
            "--playbook",
            help="Specify a playbook file to smoke-check (can be used multiple times)",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Run lightweight smoke tests for metadata, scaffolds, and playbooks."""
    run_smoke_test(
        inventory=inventory,
        playbooks=None if playbook is None else list(playbook),
    )


def smoke_test(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run lightweight integration checks without installing software."""
    app(
        args=[] if argv is None else argv,
        prog_name=prog_name or f"{CLI_ROOT_COMMAND} {COMMAND_NAME}",
    )


def main() -> None:
    """Run the smoke helper from its dedicated development command."""
    app(prog_name=COMMAND_NAME)
