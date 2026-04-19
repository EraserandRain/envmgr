from __future__ import annotations

import unittest

from tests.checks.runtime import (
    check_invalid_toml_surfaces_config_error,
    check_inventory_aliases_stay_under_runtime_inventory_dir,
    check_missing_runtime_inventory_file_is_recreated,
    check_outdated_setup_stamp_requires_setup,
    check_runtime_config_bootstrap,
    check_setup_marker_is_written_after_setup,
    check_unbootstrapped_runtime_surfaces_setup_guidance,
    check_unknown_inventory_alias_is_rejected,
)
from tests.support import Check, build_check_suite, build_check_test_case

RUNTIME_CONFIG_TEST_CHECKS: tuple[Check, ...] = (
    ("runtime config bootstrap", check_runtime_config_bootstrap),
    ("setup marker is written after setup", check_setup_marker_is_written_after_setup),
    (
        "unbootstrapped runtime surfaces setup guidance",
        check_unbootstrapped_runtime_surfaces_setup_guidance,
    ),
    ("outdated setup stamp requires setup", check_outdated_setup_stamp_requires_setup),
    (
        "unknown inventory aliases are rejected",
        check_unknown_inventory_alias_is_rejected,
    ),
    (
        "inventory aliases stay under ~/.envmgr/inventory",
        check_inventory_aliases_stay_under_runtime_inventory_dir,
    ),
    ("invalid TOML surfaces config error", check_invalid_toml_surfaces_config_error),
    (
        "missing runtime inventory file is recreated",
        check_missing_runtime_inventory_file_is_recreated,
    ),
)

RuntimeConfigTests, RUNTIME_CONFIG_TEST_METHODS = build_check_test_case(
    "RuntimeConfigTests",
    "Runtime configuration and inventory unit tests.",
    RUNTIME_CONFIG_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(RuntimeConfigTests, RUNTIME_CONFIG_TEST_METHODS)
