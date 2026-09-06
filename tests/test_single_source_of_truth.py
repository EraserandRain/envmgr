from __future__ import annotations

import unittest

from tests.checks.single_source_of_truth import check_single_source_of_truth
from tests.support import Check, build_check_suite, build_check_test_case

SINGLE_SOURCE_OF_TRUTH_CHECKS: tuple[Check, ...] = (
    (
        "src markers stay inside their owning module",
        check_single_source_of_truth,
    ),
)

SingleSourceOfTruthTests, SINGLE_SOURCE_OF_TRUTH_METHODS = build_check_test_case(
    "SingleSourceOfTruthTests",
    "Single-source-of-truth registry contract checks.",
    SINGLE_SOURCE_OF_TRUTH_CHECKS,
)


def load_tests(
    _loader: unittest.TestLoader,
    _tests: unittest.TestSuite,
    _pattern: str | None,
) -> unittest.TestSuite:
    return build_check_suite(SingleSourceOfTruthTests, SINGLE_SOURCE_OF_TRUTH_METHODS)
