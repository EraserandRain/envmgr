from __future__ import annotations

import unittest

from envmgr.smoke_checks import (
    SMOKE_TEST_CHECKS,
    SmokeCheck,
    build_smoke_test_suite,
    iter_smoke_tests,
)

__all__ = [
    "SMOKE_TEST_CHECKS",
    "SmokeCheck",
    "build_smoke_test_suite",
    "iter_smoke_tests",
    "load_tests",
]


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_smoke_test_suite()
