from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from ..catalog import CatalogError
from ..runtime_config import ConfigError, RuntimePaths
from ..scaffold import ScaffoldError
from ..services.runtime import run_runtime_subprocess
from .shared import exit_with_error

PYTHON_CHECK_PATHS = ["src/envmgr/", "tests/"]
DEV_CHECKOUT_MARKERS = (
    "pyproject.toml",
    "playbooks",
    "roles",
    "src/envmgr/commands",
    "tests",
)
DEV_HELPER_BOUNDARY_MESSAGE = (
    "'{command_name}' is a repo-only development helper. "
    "Run it from an envmgr checkout (for example: `uv run {command_name}`) "
    "or use `envmgr ...` for supported runtime commands."
)


def _find_dev_checkout_root(start_dir: Path | None = None) -> Path | None:
    current_dir = Path.cwd().resolve() if start_dir is None else start_dir.resolve()
    for candidate in (current_dir, *current_dir.parents):
        if all((candidate / marker).exists() for marker in DEV_CHECKOUT_MARKERS):
            return candidate
    return None


def require_repo_dev_context(command_name: str) -> None:
    """Exit when a dev helper runs outside a supported checkout working tree."""
    if _find_dev_checkout_root() is not None:
        return

    exit_with_error(DEV_HELPER_BOUNDARY_MESSAGE.format(command_name=command_name))


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
