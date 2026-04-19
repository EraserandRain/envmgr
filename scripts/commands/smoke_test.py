from __future__ import annotations

from pathlib import Path

from ..runtime_config import ensure_runtime_layout
from ..smoke_checks import iter_smoke_tests
from .dev_shared import run_assertion_step, run_command_step
from .legacy_argparse import build_command_parser, parse_command_args
from .shared import (
    require_setup_completed,
    resolve_inventory_option,
)


def smoke_test(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run lightweight integration checks without installing software."""
    parser = build_command_parser(
        "smoke-test",
        description="Run lightweight smoke tests for metadata, scaffolds, and playbooks",
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
        help="Specify a playbook file to smoke-check (can be used multiple times)",
    )

    args = parse_command_args(parser, argv)

    require_setup_completed("smoke-test")

    playbooks = args.playbook or [
        playbook
        for playbook in ["playbooks/workstation.yml", "playbooks/node.yml"]
        if Path(playbook).exists()
    ]
    inventory_path, _inventory_label = resolve_inventory_option(args.inventory)
    runtime_paths = ensure_runtime_layout()

    print("Running smoke tests...")

    results = [
        run_assertion_step(step_name, test.debug)
        for step_name, test in iter_smoke_tests()
    ]

    if not playbooks:
        print("No playbooks selected for smoke checks.")

    for playbook in playbooks:
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
