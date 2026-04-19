from __future__ import annotations

import unittest

from tests.checks.cli import (
    check_dispatcher_rejects_dev_only_subcommands,
    check_dispatcher_routes_install_subcommand,
)
from tests.support import Check, build_check_suite, build_check_test_case

CLI_CONTRACT_TEST_CHECKS: tuple[Check, ...] = (
    (
        "dispatcher routes install subcommands",
        check_dispatcher_routes_install_subcommand,
    ),
    (
        "dispatcher rejects dev-only subcommands",
        check_dispatcher_rejects_dev_only_subcommands,
    ),
)

CliContractTests, CLI_CONTRACT_TEST_METHODS = build_check_test_case(
    "CliContractTests",
    "CLI dispatcher unit tests.",
    CLI_CONTRACT_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(CliContractTests, CLI_CONTRACT_TEST_METHODS)
