from __future__ import annotations

import re
import unittest
from collections.abc import Callable

Check = tuple[str, Callable[[], None]]
CheckMethod = tuple[str, str]


def slugify_test_name(step_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", step_name.lower()).strip("_")
    return slug or "check"


def build_check_test_case(
    class_name: str,
    class_doc: str,
    checks: tuple[Check, ...],
) -> tuple[type[unittest.TestCase], tuple[CheckMethod, ...]]:
    class CheckTests(unittest.TestCase):
        maxDiff = None

    CheckTests.__name__ = class_name
    CheckTests.__qualname__ = class_name
    CheckTests.__doc__ = class_doc

    method_specs = tuple(
        (
            step_name,
            f"test_{index:02d}_{slugify_test_name(step_name)}",
        )
        for index, (step_name, _check) in enumerate(checks, start=1)
    )

    for (step_name, check), (_registered_name, method_name) in zip(
        checks,
        method_specs,
        strict=True,
    ):

        def _make_test(
            current_check: Callable[[], None],
            current_step_name: str,
            current_method_name: str,
        ) -> Callable[[unittest.TestCase], None]:
            def test(self: unittest.TestCase) -> None:
                current_check()

            test.__name__ = current_method_name
            test.__doc__ = current_step_name
            return test

        setattr(CheckTests, method_name, _make_test(check, step_name, method_name))

    return CheckTests, method_specs


def build_check_suite(
    test_case: type[unittest.TestCase],
    method_specs: tuple[CheckMethod, ...],
) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for _step_name, method_name in method_specs:
        suite.addTest(test_case(method_name))
    return suite
