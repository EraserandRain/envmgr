from __future__ import annotations

import unittest

from tests.checks.cli import (
    check_built_wheel_exposes_only_runtime_console_script,
    check_create_helper_fails_when_role_already_exists,
    check_create_helper_fails_when_scaffold_is_missing,
    check_create_helper_succeeds_with_expected_output,
    check_dev_helper_entrypoints_use_typer_help,
    check_dispatcher_rejects_dev_only_subcommands,
    check_dispatcher_routes_install_subcommand,
    check_dispatcher_routes_ping_subcommand,
    check_dispatcher_routes_setup_subcommand,
    check_plan_a_packaging_keeps_runtime_and_checkout_scripts_split,
    check_public_cli_help_aliases_version_and_completion,
    check_runtime_subcommands_use_typer_help,
)
from tests.support import Check, build_check_suite, build_check_test_case

CLI_CONTRACT_TEST_CHECKS: tuple[Check, ...] = (
    (
        "public CLI exposes help and install subcommands",
        check_dispatcher_routes_install_subcommand,
    ),
    (
        "public CLI supports help aliases, version, and disables completion",
        check_public_cli_help_aliases_version_and_completion,
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
        "create helper fails when the scaffold directory is missing",
        check_create_helper_fails_when_scaffold_is_missing,
    ),
    (
        "create helper fails when the role already exists",
        check_create_helper_fails_when_role_already_exists,
    ),
    (
        "create helper keeps the existing success contract",
        check_create_helper_succeeds_with_expected_output,
    ),
    (
        "Plan A packaging keeps runtime and checkout helper scripts split",
        check_plan_a_packaging_keeps_runtime_and_checkout_scripts_split,
    ),
    (
        "built release wheel exposes only the envmgr console script",
        check_built_wheel_exposes_only_runtime_console_script,
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
