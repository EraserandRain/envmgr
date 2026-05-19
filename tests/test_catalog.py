from __future__ import annotations

import unittest

from tests.checks.catalog import (
    check_builtin_playbooks_match_enabled_role_metadata,
    check_catalog_defaults_resolve_outside_repo_cwd,
    check_github_cli_task_tag_catalog_and_execution_playbook,
    check_playbook_resolution,
)
from tests.support import Check, build_check_suite, build_check_test_case

CATALOG_TEST_CHECKS: tuple[Check, ...] = (
    ("playbook resolution", check_playbook_resolution),
    (
        "catalog defaults resolve outside the repo cwd",
        check_catalog_defaults_resolve_outside_repo_cwd,
    ),
    (
        "github_cli task tag catalog and execution playbook",
        check_github_cli_task_tag_catalog_and_execution_playbook,
    ),
    (
        "built-in playbooks match enabled role metadata",
        check_builtin_playbooks_match_enabled_role_metadata,
    ),
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
