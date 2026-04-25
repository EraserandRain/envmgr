from __future__ import annotations

import unittest

from tests.checks.release_surface import (
    check_isolated_uv_tool_install_exposes_envmgr_only,
)
from tests.support import Check, build_check_suite, build_check_test_case

RELEASE_SURFACE_TEST_CHECKS: tuple[Check, ...] = (
    (
        "isolated uv tool install exposes envmgr and omits create",
        check_isolated_uv_tool_install_exposes_envmgr_only,
    ),
)

ReleaseSurfaceTests, RELEASE_SURFACE_TEST_METHODS = build_check_test_case(
    "ReleaseSurfaceTests",
    "Release package surface tests.",
    RELEASE_SURFACE_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(ReleaseSurfaceTests, RELEASE_SURFACE_TEST_METHODS)
