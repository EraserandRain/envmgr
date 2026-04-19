from __future__ import annotations

import unittest

from tests.checks.ping import (
    check_ping_surfaces_subprocess_failures,
    check_ping_uses_selected_inventory_alias,
)
from tests.support import Check, build_check_suite, build_check_test_case

PING_TEST_CHECKS: tuple[Check, ...] = (
    (
        "ping uses the selected inventory alias",
        check_ping_uses_selected_inventory_alias,
    ),
    ("ping surfaces subprocess failures", check_ping_surfaces_subprocess_failures),
)

PingTests, PING_TEST_METHODS = build_check_test_case(
    "PingTests",
    "Ping command unit tests.",
    PING_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(PingTests, PING_TEST_METHODS)
