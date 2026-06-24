from __future__ import annotations

import unittest

from tests.checks.self_management import (
    check_self_uninstall_prompts_without_yes_and_can_cancel,
    check_self_uninstall_uses_fake_uv_and_preserves_runtime_data,
    check_self_update_handles_empty_tag_name,
    check_self_update_handles_http_error,
    check_self_update_handles_invalid_github_response,
    check_self_update_handles_network_failure,
    check_self_update_rejects_checkout_only_helper_shims,
    check_self_update_requires_supported_installer_state,
    check_self_update_resolves_latest_release_from_github,
    check_self_update_uses_fake_uv_and_rewrites_installer_state,
)
from tests.support import Check, build_check_suite, build_check_test_case

SELF_MANAGEMENT_TEST_CHECKS: tuple[Check, ...] = (
    (
        "self update requires supported installer state",
        check_self_update_requires_supported_installer_state,
    ),
    (
        "self update resolves latest release from GitHub",
        check_self_update_resolves_latest_release_from_github,
    ),
    (
        "self update handles network failure gracefully",
        check_self_update_handles_network_failure,
    ),
    (
        "self update handles HTTP error from GitHub",
        check_self_update_handles_http_error,
    ),
    (
        "self update handles invalid GitHub response",
        check_self_update_handles_invalid_github_response,
    ),
    (
        "self update handles empty tag_name in GitHub response",
        check_self_update_handles_empty_tag_name,
    ),
    (
        "self update uses fake uv and rewrites installer state",
        check_self_update_uses_fake_uv_and_rewrites_installer_state,
    ),
    (
        "self update rejects checkout-only helper shims",
        check_self_update_rejects_checkout_only_helper_shims,
    ),
    (
        "self uninstall uses fake uv and preserves runtime data",
        check_self_uninstall_uses_fake_uv_and_preserves_runtime_data,
    ),
    (
        "self uninstall prompts without --yes and can cancel",
        check_self_uninstall_prompts_without_yes_and_can_cancel,
    ),
)

SelfManagementTests, SELF_MANAGEMENT_TEST_METHODS = build_check_test_case(
    "SelfManagementTests",
    "Installer-managed self update and uninstall contract tests.",
    SELF_MANAGEMENT_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(SelfManagementTests, SELF_MANAGEMENT_TEST_METHODS)
