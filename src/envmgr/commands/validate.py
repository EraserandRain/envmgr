from __future__ import annotations

import sys
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import typer

from ..command_text import CLI_ROOT_COMMAND
from ..runtime_config import ensure_runtime_layout
from .dev_shared import PYTHON_CHECK_PATHS, require_repo_dev_context, run_command_step
from .shared import require_setup_completed, resolve_inventory_option

COMMAND_NAME = "validate"
REPO_ROOT = Path(__file__).resolve().parents[3]
TESTS_DIR = REPO_ROOT / "tests"
UNIT_TEST_PATTERN = "test_*.py"
SMOKE_TEST_CLASS_MODULE_PREFIX = "envmgr.smoke_checks."
app = typer.Typer(add_completion=False, rich_markup_mode="rich")


def _iter_test_cases(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _iter_test_cases(test)
            continue
        yield test


def build_unit_test_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    discovered_suite = loader.discover(
        start_dir=str(TESTS_DIR),
        pattern=UNIT_TEST_PATTERN,
        top_level_dir=str(REPO_ROOT),
    )

    unit_suite = unittest.TestSuite()
    for test in _iter_test_cases(discovered_suite):
        if test.__class__.__module__.startswith(SMOKE_TEST_CLASS_MODULE_PREFIX):
            continue
        unit_suite.addTest(test)
    return unit_suite


def run_unit_test_step() -> bool:
    print(
        "\n[unittest] "
        f"discover {TESTS_DIR.name} -p '{UNIT_TEST_PATTERN}' "
        "(excluding tests.test_smoke)"
    )
    suite = build_unit_test_suite()
    test_count = suite.countTestCases()
    if test_count == 0:
        print("✗ unittest failed because no unit tests were discovered")
        return False

    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    if result.wasSuccessful():
        print(f"✓ unittest passed ({test_count} tests)")
        return True

    print("✗ unittest failed")
    return False


def run_validate(*, inventory: str | None, playbooks: list[str] | None) -> None:
    """Run the project validation suite in one command."""
    require_repo_dev_context(COMMAND_NAME)
    require_setup_completed(COMMAND_NAME)

    selected_playbooks = playbooks or [
        playbook
        for playbook in ["playbooks/workstation.yml", "playbooks/node.yml"]
        if Path(playbook).exists()
    ]
    inventory_path, _inventory_label = resolve_inventory_option(inventory)
    runtime_paths = ensure_runtime_layout()

    print("Running project validation...")

    results = [
        run_command_step("ruff check", ["ruff", "check", *PYTHON_CHECK_PATHS]),
        run_command_step(
            "ruff format",
            ["ruff", "format", "--check", *PYTHON_CHECK_PATHS],
        ),
        run_unit_test_step(),
        run_command_step("mypy", ["mypy", *PYTHON_CHECK_PATHS]),
        run_command_step(
            "ansible-lint",
            ["ansible-lint", "./roles"],
            runtime_paths=runtime_paths,
        ),
    ]

    if not selected_playbooks:
        print("No playbooks selected for syntax checks.")

    for playbook in selected_playbooks:
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


@app.command()
def _validate_command(
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
            help="Specify a playbook file to syntax-check (can be used multiple times)",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Run lint, typecheck, ansible lint, and playbook syntax checks."""
    run_validate(
        inventory=inventory,
        playbooks=None if playbook is None else list(playbook),
    )


def validate(
    argv: list[str] | None = None,
    *,
    prog_name: str | None = None,
) -> None:
    """Run the project validation suite in one command."""
    app(
        args=[] if argv is None else argv,
        prog_name=prog_name or f"{CLI_ROOT_COMMAND} {COMMAND_NAME}",
    )


def main() -> None:
    """Run the full validation helper from its dedicated development command."""
    app(prog_name=COMMAND_NAME)
