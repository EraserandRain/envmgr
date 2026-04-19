from __future__ import annotations

import io
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.commands.ping import ping
from scripts.runtime_config import (
    RuntimePaths,
    ensure_runtime_layout,
    mark_runtime_setup_complete,
)


def bootstrap_ping_runtime(envmgr_home: Path) -> RuntimePaths:
    runtime_paths = ensure_runtime_layout(envmgr_home)
    (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
    (runtime_paths.galaxy_collections_dir / "community").mkdir()
    mark_runtime_setup_complete(runtime_paths)
    return runtime_paths


def check_ping_uses_selected_inventory_alias() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = bootstrap_ping_runtime(envmgr_home)
        captured_output = io.StringIO()

        with (
            patch("sys.stdout", new=captured_output),
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            patch(
                "scripts.commands.ping.run_runtime_subprocess",
                return_value=subprocess.CompletedProcess(
                    ["ansible", "-m", "ping", "all"],
                    0,
                ),
            ) as mock_run,
        ):
            ping(["-i", "remote"])

        command = mock_run.call_args.args[0]
        if command != [
            "ansible",
            "-i",
            str(runtime_paths.remote_inventory_file),
            "-m",
            "ping",
            "all",
        ]:
            raise AssertionError(
                "expected ping to run ansible against the resolved remote inventory"
            )
        if mock_run.call_args.kwargs.get("check") is not True:
            raise AssertionError("expected ping to run ansible in check mode")

        output = captured_output.getvalue()
        if (
            "Testing connection with inventory: remote -> "
            f"{runtime_paths.remote_inventory_file}" not in output
        ):
            raise AssertionError(
                "expected ping to print the selected inventory alias and path"
            )


def check_ping_surfaces_subprocess_failures() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        bootstrap_ping_runtime(envmgr_home)
        captured_output = io.StringIO()

        with (
            patch("sys.stdout", new=captured_output),
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
            patch(
                "scripts.commands.ping.run_runtime_subprocess",
                side_effect=subprocess.CalledProcessError(
                    7,
                    ["ansible", "-m", "ping", "all"],
                ),
            ),
        ):
            try:
                ping([])
            except SystemExit as error:
                if error.code != 1:
                    raise AssertionError(
                        "expected ping failures to exit with code 1"
                    ) from error
            else:
                raise AssertionError("expected ping to exit when ansible ping fails")

        if "Ping failed with exit code 7" not in captured_output.getvalue():
            raise AssertionError(
                "expected ping to surface the ansible exit code to the user"
            )
