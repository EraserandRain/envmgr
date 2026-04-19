from __future__ import annotations

import unittest

from scripts.smoke_checks.runtime import (
    check_runtime_env_uses_runtime_paths_only,
    check_runtime_subprocess_helpers_use_runtime_paths,
    check_setup_logs_ansible_galaxy_runs,
)

from .support import Check, build_check_suite, build_check_test_case

RUNTIME_SERVICE_TEST_CHECKS: tuple[Check, ...] = (
    (
        "runtime env uses ~/.envmgr paths only",
        check_runtime_env_uses_runtime_paths_only,
    ),
    (
        "runtime subprocess helpers use ~/.envmgr paths",
        check_runtime_subprocess_helpers_use_runtime_paths,
    ),
    ("setup logs ansible-galaxy runtime runs", check_setup_logs_ansible_galaxy_runs),
)

RuntimeServiceTests, RUNTIME_SERVICE_TEST_METHODS = build_check_test_case(
    "RuntimeServiceTests",
    "Runtime subprocess and setup service unit tests.",
    RUNTIME_SERVICE_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(RuntimeServiceTests, RUNTIME_SERVICE_TEST_METHODS)
