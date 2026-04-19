from __future__ import annotations

import unittest

from scripts.smoke_checks.catalog import (
    check_execution_playbook_generation,
    check_metadata_catalog,
    check_playbook_resolution,
    check_scaffold_generation,
)

from .support import Check, build_check_suite, build_check_test_case

CATALOG_TEST_CHECKS: tuple[Check, ...] = (
    ("metadata catalog", check_metadata_catalog),
    ("role scaffold", check_scaffold_generation),
    ("playbook resolution", check_playbook_resolution),
    ("execution playbook generation", check_execution_playbook_generation),
)

CatalogTests, CATALOG_TEST_METHODS = build_check_test_case(
    "CatalogTests",
    "Catalog and scaffold unit tests.",
    CATALOG_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(CatalogTests, CATALOG_TEST_METHODS)
