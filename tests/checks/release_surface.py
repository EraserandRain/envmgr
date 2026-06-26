from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _read_release_workflow() -> str:
    return RELEASE_WORKFLOW.read_text(encoding="utf-8")


def _run_command(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _format_process_failure(
    description: str,
    process: subprocess.CompletedProcess[str],
) -> str:
    return (
        f"{description}\n"
        f"command: {' '.join(process.args)}\n"
        f"exit code: {process.returncode}\n"
        f"stdout:\n{process.stdout}\n"
        f"stderr:\n{process.stderr}"
    )


def _command_candidates(bin_dir: Path, command_name: str) -> tuple[Path, ...]:
    return (bin_dir / command_name, bin_dir / f"{command_name}.exe")


def _find_command(bin_dir: Path, command_name: str) -> Path | None:
    for candidate in _command_candidates(bin_dir, command_name):
        if candidate.exists():
            return candidate
    return None


def _assert_workflow_contains(fragments: tuple[str, ...]) -> None:
    workflow = _read_release_workflow()
    missing = [fragment for fragment in fragments if fragment not in workflow]
    if missing:
        raise AssertionError(
            "release workflow is missing required fragments: "
            + ", ".join(repr(fragment) for fragment in missing)
        )


def check_release_workflow_publishes_generated_notes_with_fixed_guidance() -> None:
    workflow = _read_release_workflow()
    placeholder = (
        "Add release-specific highlights, breaking changes, and migration notes "
        "before announcing this release."
    )
    if placeholder in workflow:
        raise AssertionError(
            "release workflow still publishes manual placeholder notes"
        )

    _assert_workflow_contains(
        (
            "## Install",
            "SHA256SUMS",
            "grep ' install.sh$' SHA256SUMS | sha256sum -c -",
            "bash install.sh",
            "envmgr self update --version ${package_version}",
            "envmgr self uninstall --yes",
            "## Clean Reinstall",
            "uv tool uninstall envmgr || true",
            "hash -r",
            "git-cliff",
            "cat changelog.md >> release-notes.md",
            "--notes-file release-notes.md",
        )
    )


def check_isolated_uv_tool_install_exposes_envmgr_only() -> None:
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise AssertionError("expected `uv` to be available for release install checks")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        wheelhouse = temp_path / "wheelhouse"
        tool_dir = temp_path / "uv-tools"
        bin_dir = temp_path / "bin"
        env = os.environ.copy()
        env.update(
            {
                "UV_NO_PROGRESS": "1",
                "UV_PYTHON_DOWNLOADS": "never",
                "UV_TOOL_BIN_DIR": str(bin_dir),
                "UV_TOOL_DIR": str(tool_dir),
            }
        )

        build_result = _run_command(
            [uv_path, "build", "--wheel", "--out-dir", str(wheelhouse)],
            cwd=REPO_ROOT,
            env=env,
        )
        if build_result.returncode != 0:
            raise AssertionError(
                _format_process_failure("expected wheel build to succeed", build_result)
            )

        wheels = sorted(wheelhouse.glob("envmgr-*.whl"))
        if len(wheels) != 1:
            raise AssertionError(
                "expected wheel build to produce exactly one envmgr wheel"
                f"\nwheelhouse: {wheelhouse}"
                f"\nwheels: {[wheel.name for wheel in wheels]}"
            )

        install_result = _run_command(
            [
                uv_path,
                "tool",
                "install",
                "--python",
                sys.executable,
                "--force",
                str(wheels[0]),
            ],
            cwd=temp_path,
            env=env,
        )
        if install_result.returncode != 0:
            raise AssertionError(
                _format_process_failure(
                    "expected isolated uv tool install to succeed",
                    install_result,
                )
            )

        envmgr_command = _find_command(bin_dir, "envmgr")
        if envmgr_command is None:
            raise AssertionError(
                "expected isolated uv tool install to expose the `envmgr` command"
                f"\nbin dir: {bin_dir}"
            )

        version_result = _run_command(
            [str(envmgr_command), "--version"],
            cwd=temp_path,
            env=env,
        )
        if version_result.returncode != 0:
            raise AssertionError(
                _format_process_failure(
                    "expected installed `envmgr --version` to succeed",
                    version_result,
                )
            )
        if not version_result.stdout.strip().startswith("envmgr "):
            raise AssertionError(
                "expected installed `envmgr --version` to print the package version"
                f"\nstdout:\n{version_result.stdout}"
                f"\nstderr:\n{version_result.stderr}"
            )

        checkout_only_helper_shims = (
            "create",
            "lint",
            "ansible-check",
            "typecheck",
            "validate",
            "smoke-test",
        )
        for helper_shim in checkout_only_helper_shims:
            helper_command = _find_command(bin_dir, helper_shim)
            if helper_command is not None:
                raise AssertionError(
                    "expected isolated uv tool install to omit checkout-only "
                    f"`{helper_shim}` shim"
                    f"\nfound: {helper_command}"
                )
