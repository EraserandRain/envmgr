from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "install.sh"
HELPER_SHIMS = (
    "create",
    "lint",
    "ansible-check",
    "typecheck",
    "validate",
    "smoke-test",
)
SHELL_PROFILE_FILES = (".bashrc", ".bash_profile", ".profile", ".zshrc")


def _bash_path() -> str:
    bash_path = shutil.which("bash")
    if bash_path is None:
        raise AssertionError("expected bash to be available for installer checks")
    return bash_path


def _run_installer(
    args: list[str],
    *,
    env: dict[str, str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_bash_path(), str(INSTALLER), *args],
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


def _base_env(temp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ENVMGR_HOME": str(temp_path / ".envmgr"),
            "HOME": str(temp_path / "home"),
            "UV_TOOL_BIN_DIR": str(temp_path / "uv-bin"),
        }
    )
    return env


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_fake_uv(
    fake_bin_dir: Path,
    *,
    fake_log: Path,
    helper_to_create: str | None = None,
) -> Path:
    helper_block = ""
    if helper_to_create is not None:
        helper_block = f'printf "#!/usr/bin/env bash\\n" >"${{UV_TOOL_BIN_DIR}}/{helper_to_create}"\n'
        helper_block += f'chmod +x "${{UV_TOOL_BIN_DIR}}/{helper_to_create}"\n'

    fake_uv = fake_bin_dir / "uv"
    _write_executable(
        fake_uv,
        f"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >>"{fake_log}"
if [[ "$1" == "tool" && "$2" == "dir" && "$3" == "--bin" ]]; then
  printf '%s\\n' "${{UV_TOOL_BIN_DIR}}"
  exit 0
fi
if [[ "$1" == "tool" && "$2" == "install" ]]; then
  mkdir -p "${{UV_TOOL_BIN_DIR}}"
  cat >"${{UV_TOOL_BIN_DIR}}/envmgr" <<'ENVEOF'
#!/usr/bin/env bash
if [[ "${{1:-}}" == "--version" ]]; then
  printf '%s\\n' "envmgr 9.8.7"
  exit 0
fi
exit 2
ENVEOF
  chmod +x "${{UV_TOOL_BIN_DIR}}/envmgr"
{helper_block}  exit 0
fi
exit 97
""",
    )
    return fake_uv


def check_installer_help_and_dry_run_are_auditable_without_uv() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        env = _base_env(temp_path)
        env["PATH"] = str(temp_path / "empty-path")

        help_result = _run_installer(["--help"], env=env, cwd=temp_path)
        if help_result.returncode != 0:
            raise AssertionError(
                _format_process_failure(
                    "expected installer help to succeed", help_result
                )
            )
        if (
            "uv tool install --force <github-release-wheel-url>"
            not in help_result.stdout
        ):
            raise AssertionError("expected help to document uv tool install")
        if "--no-modify-path" not in help_result.stdout:
            raise AssertionError("expected help to document --no-modify-path")

        dry_run_result = _run_installer(
            ["--version", "1.2.3", "--dry-run", "--no-modify-path"],
            env=env,
            cwd=temp_path,
        )
        if dry_run_result.returncode != 0:
            raise AssertionError(
                _format_process_failure(
                    "expected installer dry-run to succeed", dry_run_result
                )
            )

        expected_url = (
            "https://github.com/EraserandRain/envmgr/releases/download/"
            "v1.2.3/envmgr-1.2.3-py3-none-any.whl"
        )
        if expected_url not in dry_run_result.stdout:
            raise AssertionError(
                "expected dry-run output to print the release wheel URL"
            )
        if "uv tool install --force" not in dry_run_result.stdout:
            raise AssertionError(
                "expected dry-run output to print the planned uv command"
            )
        if (
            "no shell profiles or hidden PATH files will be modified"
            not in dry_run_result.stdout
        ):
            raise AssertionError(
                "expected dry-run output to document PATH non-modification"
            )
        if (temp_path / ".envmgr" / "install.toml").exists():
            raise AssertionError("expected dry-run to avoid writing installer state")


def check_installer_missing_uv_fails_with_clear_guidance() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        env = _base_env(temp_path)
        env["PATH"] = str(temp_path / "empty-path")

        result = _run_installer(["--version", "1.2.3"], env=env, cwd=temp_path)
        if result.returncode == 0:
            raise AssertionError("expected installer to fail when uv is missing")
        if "uv was not found in PATH" not in result.stderr:
            raise AssertionError("expected missing-uv output to explain the problem")
        if "does not bootstrap uv yet" not in result.stderr:
            raise AssertionError(
                "expected missing-uv output to avoid implicit bootstrapping"
            )
        if (temp_path / ".envmgr" / "install.toml").exists():
            raise AssertionError(
                "expected missing-uv failure to avoid writing installer state"
            )


def check_installer_uses_fake_uv_and_records_release_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        fake_bin_dir = temp_path / "fake-bin"
        fake_bin_dir.mkdir()
        fake_log = temp_path / "uv.log"
        _write_fake_uv(fake_bin_dir, fake_log=fake_log)

        env = _base_env(temp_path)
        env["PATH"] = f"{fake_bin_dir}{os.pathsep}{env.get('PATH', '')}"

        result = _run_installer(["--version", "9.8.7"], env=env, cwd=temp_path)
        if result.returncode != 0:
            raise AssertionError(
                _format_process_failure(
                    "expected fake uv installer run to succeed", result
                )
            )

        expected_url = (
            "https://github.com/EraserandRain/envmgr/releases/download/"
            "v9.8.7/envmgr-9.8.7-py3-none-any.whl"
        )
        uv_log = fake_log.read_text(encoding="utf-8")
        if f"tool install --force {expected_url}" not in uv_log:
            raise AssertionError(
                "expected installer to call uv tool install --force with the wheel URL"
            )
        if "Verified envmgr: envmgr 9.8.7" not in result.stdout:
            raise AssertionError(
                "expected installer to verify envmgr from the uv tool bin directory"
            )

        home_path = Path(env["HOME"])
        for profile_name in SHELL_PROFILE_FILES:
            if (home_path / profile_name).exists():
                raise AssertionError(
                    f"expected installer to avoid writing shell profile: {profile_name}"
                )

        uv_bin = Path(env["UV_TOOL_BIN_DIR"])
        for helper in HELPER_SHIMS:
            if (uv_bin / helper).exists():
                raise AssertionError(
                    f"expected fake install to avoid helper shim: {helper}"
                )

        state_file = Path(env["ENVMGR_HOME"]) / "install.toml"
        if not state_file.exists():
            raise AssertionError(
                "expected installer to write install.toml after verification"
            )
        state_text = state_file.read_text(encoding="utf-8")
        expected_state_fragments = (
            'source = "github-release"',
            'manager = "install.sh"',
            'owner = "EraserandRain"',
            'repo = "envmgr"',
            'version = "9.8.7"',
            'release_tag = "v9.8.7"',
            f'wheel_url = "{expected_url}"',
            f'uv_tool_bin_dir = "{env["UV_TOOL_BIN_DIR"]}"',
        )
        missing_fragments = [
            fragment
            for fragment in expected_state_fragments
            if fragment not in state_text
        ]
        if missing_fragments:
            raise AssertionError(
                "expected install.toml to record release install metadata"
                f"\nmissing: {missing_fragments}"
                f"\nstate:\n{state_text}"
            )


def check_installer_rejects_checkout_only_helper_shims() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        fake_bin_dir = temp_path / "fake-bin"
        fake_bin_dir.mkdir()
        fake_log = temp_path / "uv.log"
        _write_fake_uv(fake_bin_dir, fake_log=fake_log, helper_to_create="create")

        env = _base_env(temp_path)
        env["PATH"] = f"{fake_bin_dir}{os.pathsep}{env.get('PATH', '')}"

        result = _run_installer(["--version", "9.8.7"], env=env, cwd=temp_path)
        if result.returncode == 0:
            raise AssertionError(
                "expected installer to reject checkout-only helper shims"
            )
        if (
            "unexpected checkout-only helper shim found after install"
            not in result.stderr
        ):
            raise AssertionError("expected helper-shim failure to be actionable")
        if (Path(env["ENVMGR_HOME"]) / "install.toml").exists():
            raise AssertionError(
                "expected helper-shim failure to avoid writing installer state"
            )
