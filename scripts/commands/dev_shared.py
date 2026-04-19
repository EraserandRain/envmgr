from __future__ import annotations

import subprocess
from collections.abc import Callable

from ..catalog import CatalogError
from ..runtime_config import ConfigError, RuntimePaths
from ..scaffold import ScaffoldError
from ..services.runtime import run_runtime_subprocess

PYTHON_CHECK_PATHS = ["scripts/", "tests/"]


def run_command_step(
    step_name: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    runtime_paths: RuntimePaths | None = None,
) -> bool:
    """Run one validation step and report its outcome."""
    print(f"\n[{step_name}] {' '.join(command)}")
    try:
        if runtime_paths is not None:
            run_runtime_subprocess(
                command,
                check=True,
                runtime_paths=runtime_paths,
                extra_env=env,
            )
        else:
            subprocess.run(command, check=True, env=env)
        print(f"✓ {step_name} passed")
        return True
    except subprocess.CalledProcessError as error:
        print(f"✗ {step_name} failed with exit code {error.returncode}")
        return False
    except FileNotFoundError:
        print(f"✗ {step_name} failed because '{command[0]}' was not found in PATH")
        return False


def run_assertion_step(step_name: str, check: Callable[[], None]) -> bool:
    """Run one Python-level smoke-test assertion and report its outcome."""
    print(f"\n[{step_name}]")
    try:
        check()
        print(f"✓ {step_name} passed")
        return True
    except (
        AssertionError,
        CatalogError,
        ConfigError,
        FileNotFoundError,
        ScaffoldError,
    ) as error:
        print(f"✗ {step_name} failed: {error}")
        return False
