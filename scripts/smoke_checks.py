from __future__ import annotations

from collections.abc import Callable

from tests.test_smoke import SMOKE_TEST_CHECKS, build_smoke_test_suite, iter_smoke_tests

SmokeCheck = tuple[str, Callable[[], None]]

__all__ = [
    "SmokeCheck",
    "SMOKE_TEST_CHECKS",
    "build_smoke_test_suite",
    "iter_smoke_tests",
]
