from __future__ import annotations

import unittest

from scripts.smoke_checks.install import (
    check_ai_tools_install_option_resolution,
    check_ai_tools_setup_wizard_flow,
    check_install_interrupt_exits_cleanly,
    check_install_rejects_all_plus_other_tags,
    check_install_rejects_unknown_tags_with_exit_code,
)

from .support import Check, build_check_suite, build_check_test_case

INSTALL_TEST_CHECKS: tuple[Check, ...] = (
    (
        "AI tools install options resolve correctly",
        check_ai_tools_install_option_resolution,
    ),
    ("AI tools setup wizard flow", check_ai_tools_setup_wizard_flow),
    (
        "install rejects unknown tags with exit code 1",
        check_install_rejects_unknown_tags_with_exit_code,
    ),
    (
        "install rejects mixed all-tag selections",
        check_install_rejects_all_plus_other_tags,
    ),
    ("install exits cleanly on Ctrl+C", check_install_interrupt_exits_cleanly),
)

InstallTests, INSTALL_TEST_METHODS = build_check_test_case(
    "InstallTests",
    "Install planning and CLI unit tests.",
    INSTALL_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(InstallTests, INSTALL_TEST_METHODS)
