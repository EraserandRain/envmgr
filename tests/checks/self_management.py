from __future__ import annotations

import os
import shlex
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import Result
from typer.testing import CliRunner

from envmgr.main import app

CLI_RUNNER = CliRunner()
HELPER_SHIMS = (
    "create",
    "lint",
    "ansible-check",
    "typecheck",
    "validate",
    "smoke-test",
)


def _invoke_envmgr_with_home(envmgr_home: Path, *args: str) -> Result:
    with patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False):
        return CLI_RUNNER.invoke(app, list(args), prog_name="envmgr")


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _write_fake_uv(
    fake_bin_dir: Path,
    *,
    fake_log: Path,
    tool_bin_dir: Path,
    version_output: str = "envmgr 2.0.0",
    helper_to_create: str | None = None,
) -> Path:
    helper_block = ""
    if helper_to_create is not None:
        helper_block = f"""  cat >"$TOOL_BIN_DIR/{helper_to_create}" <<'HELPEREOF'
#!/usr/bin/env bash
exit 0
HELPEREOF
  chmod +x "$TOOL_BIN_DIR/{helper_to_create}"
"""

    fake_uv = fake_bin_dir / "uv"
    _write_executable(
        fake_uv,
        f"""#!/usr/bin/env bash
set -euo pipefail
LOG_FILE={shlex.quote(str(fake_log))}
TOOL_BIN_DIR={shlex.quote(str(tool_bin_dir))}
printf '%s\\n' "$*" >>"$LOG_FILE"
if [[ "${{1:-}}" == "tool" && "${{2:-}}" == "install" ]]; then
  mkdir -p "$TOOL_BIN_DIR"
  cat >"$TOOL_BIN_DIR/envmgr" <<'ENVEOF'
#!/usr/bin/env bash
if [[ "${{1:-}}" == "--version" ]]; then
  printf '%s\\n' "{version_output}"
  exit 0
fi
exit 2
ENVEOF
  chmod +x "$TOOL_BIN_DIR/envmgr"
{helper_block}  exit 0
fi
if [[ "${{1:-}}" == "tool" && "${{2:-}}" == "uninstall" && "${{3:-}}" == "envmgr" ]]; then
  rm -f "$TOOL_BIN_DIR/envmgr"
  exit 0
fi
exit 97
""",
    )
    return fake_uv


def _write_installer_state(
    envmgr_home: Path,
    *,
    uv_path: Path,
    uv_tool_bin_dir: Path,
    version: str = "1.0.0",
    source: str = "github-release",
    manager: str = "install.sh",
) -> Path:
    release_tag = f"v{version}"
    wheel_url = (
        "https://github.com/EraserandRain/envmgr/releases/download/"
        f"{release_tag}/envmgr-{version}-py3-none-any.whl"
    )
    state_file = envmgr_home / "install.toml"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        f"""
[install]
source = "{source}"
manager = "{manager}"
owner = "EraserandRain"
repo = "envmgr"
version = "{version}"
release_tag = "{release_tag}"
wheel_url = "{wheel_url}"
installed_at = "2026-04-25T00:00:00Z"
uv = "{uv_path}"
uv_tool_bin_dir = "{uv_tool_bin_dir}"
""".lstrip(),
        encoding="utf-8",
    )
    return state_file


def _format_failure(description: str, result: Result) -> str:
    return (
        f"{description}\n"
        f"exit code: {result.exit_code}\n"
        f"output:\n{result.output}\n"
        f"exception: {result.exception!r}"
    )


def check_self_update_requires_supported_installer_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"

        missing_result = _invoke_envmgr_with_home(
            envmgr_home,
            "self",
            "update",
            "--version",
            "2.0.0",
        )
        if missing_result.exit_code != 1:
            raise AssertionError(
                _format_failure(
                    "expected missing installer state to fail", missing_result
                )
            )
        if "install.sh-managed GitHub Release" not in missing_result.output:
            raise AssertionError(
                "expected missing state guidance to mention install.sh"
            )

        state_file = envmgr_home / "install.toml"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("[install\n", encoding="utf-8")
        invalid_result = _invoke_envmgr_with_home(
            envmgr_home,
            "self",
            "update",
            "--version",
            "2.0.0",
        )
        if invalid_result.exit_code != 1:
            raise AssertionError(
                _format_failure(
                    "expected invalid installer state to fail", invalid_result
                )
            )
        if "invalid TOML" not in invalid_result.output:
            raise AssertionError("expected invalid TOML guidance")

        state_file.write_text(
            """
[install]
source = "editable"
manager = "pip"
""".lstrip(),
            encoding="utf-8",
        )
        unsupported_result = _invoke_envmgr_with_home(
            envmgr_home,
            "self",
            "update",
            "--version",
            "2.0.0",
        )
        if unsupported_result.exit_code != 1:
            raise AssertionError(
                _format_failure(
                    "expected unsupported installer state to fail",
                    unsupported_result,
                )
            )
        if "originally installed envmgr" not in unsupported_result.output:
            raise AssertionError("expected unsupported state guidance")


def check_self_update_requires_explicit_version_without_network() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        envmgr_home = temp_path / ".envmgr"
        fake_bin_dir = temp_path / "fake-bin"
        fake_bin_dir.mkdir()
        fake_log = temp_path / "uv.log"
        tool_bin_dir = temp_path / "uv-bin"
        fake_uv = _write_fake_uv(
            fake_bin_dir,
            fake_log=fake_log,
            tool_bin_dir=tool_bin_dir,
        )
        _write_installer_state(
            envmgr_home,
            uv_path=fake_uv,
            uv_tool_bin_dir=tool_bin_dir,
        )

        result = _invoke_envmgr_with_home(envmgr_home, "self", "update")
        if result.exit_code != 1:
            raise AssertionError(
                _format_failure(
                    "expected self update without --version to fail", result
                )
            )
        if "--version" not in result.output or "VERSION to update" not in result.output:
            raise AssertionError("expected no-network latest guidance")
        if fake_log.exists():
            raise AssertionError("expected missing --version to avoid running uv")


def check_self_update_uses_fake_uv_and_rewrites_installer_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        envmgr_home = temp_path / ".envmgr"
        fake_bin_dir = temp_path / "fake-bin"
        fake_bin_dir.mkdir()
        fake_log = temp_path / "uv.log"
        tool_bin_dir = temp_path / "uv-bin"
        fake_uv = _write_fake_uv(
            fake_bin_dir,
            fake_log=fake_log,
            tool_bin_dir=tool_bin_dir,
            version_output="envmgr 2.0.0",
        )
        state_file = _write_installer_state(
            envmgr_home,
            uv_path=fake_uv,
            uv_tool_bin_dir=tool_bin_dir,
        )

        result = _invoke_envmgr_with_home(
            envmgr_home,
            "self",
            "update",
            "--version",
            "2.0.0",
        )
        if result.exit_code != 0:
            raise AssertionError(
                _format_failure("expected fake self update to succeed", result)
            )

        expected_url = (
            "https://github.com/EraserandRain/envmgr/releases/download/"
            "v2.0.0/envmgr-2.0.0-py3-none-any.whl"
        )
        uv_log = fake_log.read_text(encoding="utf-8")
        if f"tool install --force {expected_url}" not in uv_log:
            raise AssertionError("expected self update to call uv tool install")
        if "Verified envmgr: envmgr 2.0.0" not in result.output:
            raise AssertionError("expected self update to verify envmgr")

        state_text = state_file.read_text(encoding="utf-8")
        expected_state_fragments = (
            'source = "github-release"',
            'manager = "install.sh"',
            'version = "2.0.0"',
            'release_tag = "v2.0.0"',
            f'wheel_url = "{expected_url}"',
            'installed_at = "2026-04-25T00:00:00Z"',
            'updated_at = "',
        )
        for fragment in expected_state_fragments:
            if fragment not in state_text:
                raise AssertionError(
                    f"expected updated state to include {fragment!r}"
                    f"\nstate:\n{state_text}"
                )
        for helper in HELPER_SHIMS:
            if (tool_bin_dir / helper).exists():
                raise AssertionError(f"expected helper shim to be absent: {helper}")


def check_self_update_rejects_checkout_only_helper_shims() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        envmgr_home = temp_path / ".envmgr"
        fake_bin_dir = temp_path / "fake-bin"
        fake_bin_dir.mkdir()
        fake_log = temp_path / "uv.log"
        tool_bin_dir = temp_path / "uv-bin"
        fake_uv = _write_fake_uv(
            fake_bin_dir,
            fake_log=fake_log,
            tool_bin_dir=tool_bin_dir,
            helper_to_create="create",
        )
        state_file = _write_installer_state(
            envmgr_home,
            uv_path=fake_uv,
            uv_tool_bin_dir=tool_bin_dir,
        )

        result = _invoke_envmgr_with_home(
            envmgr_home,
            "self",
            "update",
            "--version",
            "2.0.0",
        )
        if result.exit_code != 1:
            raise AssertionError(
                _format_failure("expected self update to reject helper shims", result)
            )
        if "Unexpected checkout-only helper shim" not in result.output:
            raise AssertionError("expected helper shim guidance")
        if 'version = "1.0.0"' not in state_file.read_text(encoding="utf-8"):
            raise AssertionError("expected failed update to preserve prior state")


def check_self_uninstall_uses_fake_uv_and_preserves_runtime_data() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        envmgr_home = temp_path / ".envmgr"
        fake_bin_dir = temp_path / "fake-bin"
        fake_bin_dir.mkdir()
        fake_log = temp_path / "uv.log"
        tool_bin_dir = temp_path / "uv-bin"
        fake_uv = _write_fake_uv(
            fake_bin_dir,
            fake_log=fake_log,
            tool_bin_dir=tool_bin_dir,
        )
        state_file = _write_installer_state(
            envmgr_home,
            uv_path=fake_uv,
            uv_tool_bin_dir=tool_bin_dir,
        )
        runtime_config = envmgr_home / "config.toml"
        runtime_config.write_text("[default]\n", encoding="utf-8")

        result = _invoke_envmgr_with_home(envmgr_home, "self", "uninstall", "--yes")
        if result.exit_code != 0:
            raise AssertionError(
                _format_failure("expected fake self uninstall to succeed", result)
            )

        uv_log = fake_log.read_text(encoding="utf-8")
        if "tool uninstall envmgr" not in uv_log:
            raise AssertionError("expected self uninstall to call uv tool uninstall")
        if state_file.exists():
            raise AssertionError("expected self uninstall to remove install.toml")
        if not runtime_config.exists():
            raise AssertionError("expected self uninstall to keep runtime data")
        if "Kept runtime data" not in result.output:
            raise AssertionError("expected output to mention preserved runtime data")


def check_self_uninstall_prompts_without_yes_and_can_cancel() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        envmgr_home = temp_path / ".envmgr"
        fake_bin_dir = temp_path / "fake-bin"
        fake_bin_dir.mkdir()
        fake_log = temp_path / "uv.log"
        tool_bin_dir = temp_path / "uv-bin"
        fake_uv = _write_fake_uv(
            fake_bin_dir,
            fake_log=fake_log,
            tool_bin_dir=tool_bin_dir,
        )
        state_file = _write_installer_state(
            envmgr_home,
            uv_path=fake_uv,
            uv_tool_bin_dir=tool_bin_dir,
        )

        with patch("envmgr.commands.shared.confirm_backend", return_value=False):
            result = _invoke_envmgr_with_home(envmgr_home, "self", "uninstall")

        if result.exit_code != 1:
            raise AssertionError(
                _format_failure(
                    "expected cancelled self uninstall to exit non-zero", result
                )
            )
        if "cancelled" not in result.output:
            raise AssertionError("expected cancellation output")
        if not state_file.exists():
            raise AssertionError("expected cancellation to keep install.toml")
        if fake_log.exists():
            raise AssertionError("expected cancellation to avoid running uv")
