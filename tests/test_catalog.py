from __future__ import annotations

import unittest

from tests.checks.catalog import check_playbook_resolution
from tests.support import Check, build_check_suite, build_check_test_case

CATALOG_TEST_CHECKS: tuple[Check, ...] = (
    ("playbook resolution", check_playbook_resolution),
)

CatalogTests, CATALOG_TEST_METHODS = build_check_test_case(
    "CatalogTests",
    "Catalog playbook selection unit tests.",
    CATALOG_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(CatalogTests, CATALOG_TEST_METHODS)
