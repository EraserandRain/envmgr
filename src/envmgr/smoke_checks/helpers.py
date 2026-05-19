from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ..runtime_config import (
    RuntimePaths,
    ensure_runtime_layout,
    mark_runtime_setup_complete,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def run_envmgr_cli(
    *args: str,
    env_overrides: dict[str, str] | None = None,
    python_executable: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overrides is not None:
        env.update(env_overrides)
    executable = sys.executable if python_executable is None else str(python_executable)

    return subprocess.run(
        [executable, "-c", "from envmgr.main import main; main()", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def bootstrap_cli_runtime(envmgr_home: Path) -> RuntimePaths:
    runtime_paths = ensure_runtime_layout(envmgr_home)
    (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
    (runtime_paths.galaxy_collections_dir / "community").mkdir()
    mark_runtime_setup_complete(runtime_paths)
    return runtime_paths
