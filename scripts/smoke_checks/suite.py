from __future__ import annotations

import re
import unittest
from collections.abc import Callable

from .catalog import (
    check_execution_playbook_generation,
    check_metadata_catalog,
    check_scaffold_generation,
)
from .cli import (
    check_doctor_json_cli_contract,
    check_envmgr_help_contract,
    check_envmgr_invalid_command_contract,
    check_history_json_cli_contract,
    check_install_list_tags_cli_contract,
)
from .install import check_ai_tools_setup_wizard_flow
from .runtime import (
    check_multi_node_inventory_topology,
    check_setup_logs_ansible_galaxy_runs,
)

SmokeCheck = tuple[str, Callable[[], None]]

SMOKE_TEST_CHECKS: tuple[SmokeCheck, ...] = (
    ("metadata catalog", check_metadata_catalog),
    ("role scaffold", check_scaffold_generation),
    ("execution playbook generation", check_execution_playbook_generation),
    ("AI tools setup wizard flow", check_ai_tools_setup_wizard_flow),
    ("envmgr help contract", check_envmgr_help_contract),
    ("envmgr invalid subcommand contract", check_envmgr_invalid_command_contract),
    ("doctor json CLI contract", check_doctor_json_cli_contract),
    ("history json CLI contract", check_history_json_cli_contract),
    ("install list-tags CLI contract", check_install_list_tags_cli_contract),
    ("setup logs ansible-galaxy runtime runs", check_setup_logs_ansible_galaxy_runs),
    ("multi-node inventory topology", check_multi_node_inventory_topology),
)


def _slugify_smoke_test_name(step_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", step_name.lower()).strip("_")
    return slug or "smoke_test"


class SmokeTests(unittest.TestCase):
    """Repository smoke tests runnable via `python -m unittest tests.test_smoke`."""

    maxDiff = None


SMOKE_TEST_METHODS: tuple[tuple[str, str], ...] = tuple(
    (
        step_name,
        f"test_{index:02d}_{_slugify_smoke_test_name(step_name)}",
    )
    for index, (step_name, _check) in enumerate(SMOKE_TEST_CHECKS, start=1)
)


for (step_name, check), (_registered_name, method_name) in zip(
    SMOKE_TEST_CHECKS,
    SMOKE_TEST_METHODS,
    strict=True,
):

    def _make_test(
        current_check: Callable[[], None],
        current_step_name: str,
        current_method_name: str,
    ) -> Callable[[SmokeTests], None]:
        def test(self: SmokeTests) -> None:
            current_check()

        test.__name__ = current_method_name
        test.__doc__ = current_step_name
        return test

    setattr(SmokeTests, method_name, _make_test(check, step_name, method_name))


def build_smoke_test_suite() -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for _step_name, method_name in SMOKE_TEST_METHODS:
        suite.addTest(SmokeTests(method_name))
    return suite


def iter_smoke_tests() -> tuple[tuple[str, unittest.TestCase], ...]:
    return tuple(
        (step_name, SmokeTests(method_name))
        for step_name, method_name in SMOKE_TEST_METHODS
    )


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_smoke_test_suite()
