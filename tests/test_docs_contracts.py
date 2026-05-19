from __future__ import annotations

import unittest

from tests.checks.docs_contracts import (
    check_doctor_dependency_docs_contract,
    check_install_dry_run_docs_contract,
    check_public_cli_surface_docs_contract,
    check_release_notes_docs_contract,
    check_runtime_playbook_scenario_docs_contract,
)
from tests.support import Check, build_check_suite, build_check_test_case

DOCS_CONTRACT_TEST_CHECKS: tuple[Check, ...] = (
    (
        "public CLI commands and options are documented",
        check_public_cli_surface_docs_contract,
    ),
    (
        "runtime playbook scenario docs stay synchronized",
        check_runtime_playbook_scenario_docs_contract,
    ),
    (
        "install dry-run docs stay synchronized",
        check_install_dry_run_docs_contract,
    ),
    (
        "doctor dependency docs stay synchronized",
        check_doctor_dependency_docs_contract,
    ),
    (
        "release notes docs stay synchronized",
        check_release_notes_docs_contract,
    ),
)

DocsContractTests, DOCS_CONTRACT_TEST_METHODS = build_check_test_case(
    "DocsContractTests",
    "Documentation contract tests.",
    DOCS_CONTRACT_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(DocsContractTests, DOCS_CONTRACT_TEST_METHODS)
