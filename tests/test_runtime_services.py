from __future__ import annotations

import unittest

from tests.checks.runtime import (
    check_package_root_helper_exports_resolve_to_command_modules,
    check_runtime_env_uses_runtime_paths_only,
    check_runtime_subprocess_helpers_use_runtime_paths,
    check_scripts_main_keeps_only_root_command_exports,
)
from tests.support import Check, build_check_suite, build_check_test_case

RUNTIME_SERVICE_TEST_CHECKS: tuple[Check, ...] = (
    (
        "runtime env uses ~/.envmgr paths only",
        check_runtime_env_uses_runtime_paths_only,
    ),
    (
        "runtime subprocess helpers use ~/.envmgr paths",
        check_runtime_subprocess_helpers_use_runtime_paths,
    ),
    (
        "package-root helper exports resolve to their command modules",
        check_package_root_helper_exports_resolve_to_command_modules,
    ),
    (
        "scripts.main keeps only the retained root-command exports",
        check_scripts_main_keeps_only_root_command_exports,
    ),
)

RuntimeServiceTests, RUNTIME_SERVICE_TEST_METHODS = build_check_test_case(
    "RuntimeServiceTests",
    "Runtime subprocess helper and compatibility boundary unit tests.",
    RUNTIME_SERVICE_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(RuntimeServiceTests, RUNTIME_SERVICE_TEST_METHODS)
