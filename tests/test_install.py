from __future__ import annotations

import unittest

from tests.checks.install import (
    check_ai_tools_install_option_resolution,
    check_ai_tools_setup_wizard_uses_rich_prompt_path,
    check_install_all_uses_runtime_default_playbook,
    check_install_interrupt_exits_cleanly,
    check_install_list_tags_uses_rich_console,
    check_install_rejects_all_plus_other_tags,
    check_install_rejects_unknown_tags_with_exit_code,
    check_install_scoped_runs_use_runtime_scratch_outside_repo_cwd,
    check_install_summary_uses_rich_console_and_keeps_raw_subprocess_output,
    check_install_typer_flags_preserve_tri_state_bools,
    check_install_wizard_cancellation_reports_via_rich_console,
)
from tests.support import Check, build_check_suite, build_check_test_case

INSTALL_TEST_CHECKS: tuple[Check, ...] = (
    (
        "AI tools install options resolve correctly",
        check_ai_tools_install_option_resolution,
    ),
    (
        "AI tools wizard uses Rich prompt helpers",
        check_ai_tools_setup_wizard_uses_rich_prompt_path,
    ),
    (
        "install all uses the runtime default playbook",
        check_install_all_uses_runtime_default_playbook,
    ),
    (
        "scoped installs use the runtime scratch directory outside the repo cwd",
        check_install_scoped_runs_use_runtime_scratch_outside_repo_cwd,
    ),
    (
        "install list-tags uses Rich console output",
        check_install_list_tags_uses_rich_console,
    ),
    (
        "install rejects unknown tags with exit code 1",
        check_install_rejects_unknown_tags_with_exit_code,
    ),
    (
        "install summary uses Rich output while subprocess passthrough stays raw",
        check_install_summary_uses_rich_console_and_keeps_raw_subprocess_output,
    ),
    (
        "install rejects mixed all-tag selections",
        check_install_rejects_all_plus_other_tags,
    ),
    (
        "install Typer flags preserve tri-state bool semantics",
        check_install_typer_flags_preserve_tri_state_bools,
    ),
    (
        "install wizard cancellation reports through Rich console",
        check_install_wizard_cancellation_reports_via_rich_console,
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
