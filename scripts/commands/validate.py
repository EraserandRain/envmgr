from __future__ import annotations

import sys
from pathlib import Path

from ..runtime_config import ensure_runtime_layout
from .dev_shared import PYTHON_CHECK_PATHS, UNIT_TEST_MODULES, run_command_step
from .shared import (
    build_command_parser,
    parse_command_args,
    require_setup_completed,
    resolve_inventory_option,
)


def validate(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run the project validation suite in one command."""
    parser = build_command_parser(
        "validate",
        description="Run lint, typecheck, ansible lint, and playbook syntax checks",
        prog_name=prog_name,
    )
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        help="Specify a playbook file to syntax-check (can be used multiple times)",
    )

    args = parse_command_args(parser, argv)

    require_setup_completed("validate")

    playbooks = args.playbook or [
        playbook
        for playbook in ["playbooks/workstation.yml", "playbooks/node.yml"]
        if Path(playbook).exists()
    ]
    inventory_path, _inventory_label = resolve_inventory_option(args.inventory)
    runtime_paths = ensure_runtime_layout()

    print("Running project validation...")

    results = [
        run_command_step("ruff check", ["ruff", "check", *PYTHON_CHECK_PATHS]),
        run_command_step(
            "ruff format",
            ["ruff", "format", "--check", *PYTHON_CHECK_PATHS],
        ),
        run_command_step(
            "unittest",
            [sys.executable, "-m", "unittest", *UNIT_TEST_MODULES],
        ),
        run_command_step("mypy", ["mypy", *PYTHON_CHECK_PATHS]),
        run_command_step(
            "ansible-lint",
            ["ansible-lint", "./roles"],
            runtime_paths=runtime_paths,
        ),
    ]

    if not playbooks:
        print("No playbooks selected for syntax checks.")

    for playbook in playbooks:
        if not Path(playbook).exists():
            print(f"✗ syntax-check failed because playbook was not found: {playbook}")
            results.append(False)
            continue
        results.append(
            run_command_step(
                f"syntax-check {playbook}",
                [
                    "ansible-playbook",
                    "-i",
                    str(inventory_path),
                    playbook,
                    "--syntax-check",
                ],
                runtime_paths=runtime_paths,
            )
        )

    if all(results):
        print("\n✓ Validation passed")
        return

    print("\n✗ Validation failed")
    raise SystemExit(1)
