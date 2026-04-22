from __future__ import annotations

import unittest

from tests.checks.cli import (
    check_dev_helper_entrypoints_use_typer_help,
    check_dev_helpers_reject_unsupported_non_repo_cwds,
    check_dispatcher_rejects_dev_only_subcommands,
    check_dispatcher_routes_install_subcommand,
    check_dispatcher_routes_ping_subcommand,
    check_dispatcher_routes_setup_subcommand,
    check_runtime_subcommands_use_typer_help,
)
from tests.support import Check, build_check_suite, build_check_test_case

CLI_CONTRACT_TEST_CHECKS: tuple[Check, ...] = (
    (
        "public CLI exposes help and install subcommands",
        check_dispatcher_routes_install_subcommand,
    ),
    (
        "public runtime subcommands keep Typer Rich help output",
        check_runtime_subcommands_use_typer_help,
    ),
    (
        "dedicated dev-helper entrypoints keep Typer Rich help output",
        check_dev_helper_entrypoints_use_typer_help,
    ),
    (
        "dedicated dev helpers reject unsupported non-repo cwds",
        check_dev_helpers_reject_unsupported_non_repo_cwds,
    ),
    (
        "public CLI routes setup to the shared Rich runtime summary",
        check_dispatcher_routes_setup_subcommand,
    ),
    (
        "public CLI routes ping to the shared Rich runtime summary",
        check_dispatcher_routes_ping_subcommand,
    ),
    (
        "public CLI rejects dev-only subcommands",
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
