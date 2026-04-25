from __future__ import annotations

import unittest

from tests.checks.installer import (
    check_installer_help_and_dry_run_are_auditable_without_uv,
    check_installer_missing_uv_fails_with_clear_guidance,
    check_installer_rejects_checkout_only_helper_shims,
    check_installer_uses_fake_uv_and_records_release_state,
)
from tests.support import Check, build_check_suite, build_check_test_case

INSTALLER_TEST_CHECKS: tuple[Check, ...] = (
    (
        "installer help and dry-run are auditable without uv",
        check_installer_help_and_dry_run_are_auditable_without_uv,
    ),
    (
        "installer missing uv fails with clear guidance",
        check_installer_missing_uv_fails_with_clear_guidance,
    ),
    (
        "installer uses fake uv and records release state",
        check_installer_uses_fake_uv_and_records_release_state,
    ),
    (
        "installer rejects checkout-only helper shims",
        check_installer_rejects_checkout_only_helper_shims,
    ),
)

InstallerTests, INSTALLER_TEST_METHODS = build_check_test_case(
    "InstallerTests",
    "GitHub Release installer contract tests.",
    INSTALLER_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(InstallerTests, INSTALLER_TEST_METHODS)
