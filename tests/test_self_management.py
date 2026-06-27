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
    check_update_cache_read_write_and_freshness,
    check_update_newer_recognises_newer_version,
    check_update_newer_rejects_same_or_older,
    check_update_render_notice_includes_expected_content,
    check_update_run_check_falls_back_to_stale_cache_on_failure,
    check_update_run_check_fetches_when_cache_stale,
    check_update_run_check_handles_network_failure_gracefully,
    check_update_run_check_returns_none_when_current_is_latest,
    check_update_run_check_uses_cached_result_when_fresh,
    check_update_should_notify_skips_during_self_uninstall,
    check_update_should_notify_skips_during_self_update,
    check_update_should_notify_skips_in_ci,
    check_update_should_notify_skips_with_env_var,
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
    (
        "update check newer recognises newer version",
        check_update_newer_recognises_newer_version,
    ),
    (
        "update check newer rejects same or older version",
        check_update_newer_rejects_same_or_older,
    ),
    (
        "update check cache read write and freshness",
        check_update_cache_read_write_and_freshness,
    ),
    (
        "update check uses cached result when fresh",
        check_update_run_check_uses_cached_result_when_fresh,
    ),
    (
        "update check returns none when current is latest",
        check_update_run_check_returns_none_when_current_is_latest,
    ),
    (
        "update check fetches when cache stale",
        check_update_run_check_fetches_when_cache_stale,
    ),
    (
        "update check handles network failure gracefully",
        check_update_run_check_handles_network_failure_gracefully,
    ),
    (
        "update check falls back to stale cache on network failure",
        check_update_run_check_falls_back_to_stale_cache_on_failure,
    ),
    (
        "update check skips notification in CI",
        check_update_should_notify_skips_in_ci,
    ),
    (
        "update check skips notification during self update",
        check_update_should_notify_skips_during_self_update,
    ),
    (
        "update check skips notification during self uninstall",
        check_update_should_notify_skips_during_self_uninstall,
    ),
    (
        "update check skips notification with NO_UPDATE_NOTIFIER",
        check_update_should_notify_skips_with_env_var,
    ),
    (
        "update check render notice includes expected content",
        check_update_render_notice_includes_expected_content,
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
