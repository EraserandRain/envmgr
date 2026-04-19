from __future__ import annotations

import unittest

from tests.checks.install import (
    check_ai_tools_install_option_resolution,
    check_install_all_uses_runtime_default_playbook,
    check_install_interrupt_exits_cleanly,
    check_install_rejects_all_plus_other_tags,
    check_install_rejects_unknown_tags_with_exit_code,
)
from tests.support import Check, build_check_suite, build_check_test_case

INSTALL_TEST_CHECKS: tuple[Check, ...] = (
    (
        "AI tools install options resolve correctly",
        check_ai_tools_install_option_resolution,
    ),
    (
        "install all uses the runtime default playbook",
        check_install_all_uses_runtime_default_playbook,
    ),
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
    "Install planning and interrupt-handling unit tests.",
    INSTALL_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(InstallTests, INSTALL_TEST_METHODS)
