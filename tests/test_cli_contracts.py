from __future__ import annotations

import unittest

from scripts.smoke_checks.cli import (
    check_dispatcher_rejects_dev_only_subcommands,
    check_dispatcher_routes_install_subcommand,
    check_doctor_json_cli_contract,
    check_envmgr_help_contract,
    check_envmgr_invalid_command_contract,
    check_history_json_cli_contract,
    check_install_list_tags_cli_contract,
)

from .support import Check, build_check_suite, build_check_test_case

CLI_CONTRACT_TEST_CHECKS: tuple[Check, ...] = (
    (
        "dispatcher routes install subcommands",
        check_dispatcher_routes_install_subcommand,
    ),
    (
        "dispatcher rejects dev-only subcommands",
        check_dispatcher_rejects_dev_only_subcommands,
    ),
    ("envmgr help contract", check_envmgr_help_contract),
    ("envmgr invalid subcommand contract", check_envmgr_invalid_command_contract),
    ("doctor json CLI contract", check_doctor_json_cli_contract),
    ("history json CLI contract", check_history_json_cli_contract),
    ("install list-tags CLI contract", check_install_list_tags_cli_contract),
)

CliContractTests, CLI_CONTRACT_TEST_METHODS = build_check_test_case(
    "CliContractTests",
    "User-facing envmgr CLI contract tests.",
    CLI_CONTRACT_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(CliContractTests, CLI_CONTRACT_TEST_METHODS)
