from __future__ import annotations

import unittest

from tests.checks.doctor_history import (
    check_doctor_ignores_non_default_inventory_aliases,
    check_doctor_json_output,
    check_doctor_report_detects_unbootstrapped_runtime,
    check_doctor_report_passes_bootstrapped_runtime,
    check_doctor_resolves_default_playbook_outside_repo_cwd,
    check_doctor_text_output,
    check_history_json_output,
    check_history_text_output,
    check_history_text_output_preserves_markup_like_values,
)
from tests.support import Check, build_check_suite, build_check_test_case

DOCTOR_HISTORY_TEST_CHECKS: tuple[Check, ...] = (
    ("history renders readable text output", check_history_text_output),
    (
        "history preserves markup-like status and command text",
        check_history_text_output_preserves_markup_like_values,
    ),
    ("history emits json output", check_history_json_output),
    (
        "doctor detects an unbootstrapped runtime",
        check_doctor_report_detects_unbootstrapped_runtime,
    ),
    (
        "doctor passes a bootstrapped runtime",
        check_doctor_report_passes_bootstrapped_runtime,
    ),
    (
        "doctor ignores non-default inventory aliases",
        check_doctor_ignores_non_default_inventory_aliases,
    ),
    (
        "doctor resolves the default playbook outside the repo cwd",
        check_doctor_resolves_default_playbook_outside_repo_cwd,
    ),
    ("doctor renders readable text output", check_doctor_text_output),
    ("doctor emits json output", check_doctor_json_output),
)

DoctorHistoryTests, DOCTOR_HISTORY_TEST_METHODS = build_check_test_case(
    "DoctorHistoryTests",
    "Doctor and history reporting unit tests.",
    DOCTOR_HISTORY_TEST_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(DoctorHistoryTests, DOCTOR_HISTORY_TEST_METHODS)
