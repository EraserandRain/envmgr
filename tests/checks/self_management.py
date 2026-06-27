from __future__ import annotations

import json
import os
import shlex
import stat
import sys
import tempfile
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message
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


def _mock_github_latest_response(fake_response: str) -> object:
    """Return a context manager that mocks urlopen to return *fake_response*."""

    class _FakeResponse:
        def __init__(self, body: str) -> None:
            self._body = body

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: object,
        ) -> None:
            pass

        def read(self) -> bytes:
            return self._body.encode("utf-8")

    return _FakeResponse(fake_response)


def check_self_update_resolves_latest_release_from_github() -> None:
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

        with patch(
            "urllib.request.urlopen",
            return_value=_mock_github_latest_response('{"tag_name": "v2.0.0"}'),
        ):
            result = _invoke_envmgr_with_home(envmgr_home, "self", "update")

        if result.exit_code != 0:
            raise AssertionError(
                _format_failure(
                    "expected self update without --version to succeed with mocked latest",
                    result,
                )
            )

        expected_url = (
            "https://github.com/EraserandRain/envmgr/releases/download/"
            "v2.0.0/envmgr-2.0.0-py3-none-any.whl"
        )
        uv_log = fake_log.read_text(encoding="utf-8")
        if f"tool install --force {expected_url}" not in uv_log:
            raise AssertionError("expected latest self update to call uv tool install")
        if "Verified envmgr: envmgr 2.0.0" not in result.output:
            raise AssertionError("expected latest self update to verify envmgr")

        state_text = state_file.read_text(encoding="utf-8")
        expected_state_fragments = (
            'source = "github-release"',
            'manager = "install.sh"',
            'version = "2.0.0"',
            'release_tag = "v2.0.0"',
            f'wheel_url = "{expected_url}"',
            'updated_at = "',
        )
        for fragment in expected_state_fragments:
            if fragment not in state_text:
                raise AssertionError(
                    f"expected updated state to include {fragment!r}"
                    f"\nstate:\n{state_text}"
                )


def check_self_update_handles_network_failure() -> None:
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

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            result = _invoke_envmgr_with_home(envmgr_home, "self", "update")

        if result.exit_code != 1:
            raise AssertionError(
                _format_failure(
                    "expected network failure during latest resolution to fail", result
                )
            )
        if "network" not in result.output.lower():
            raise AssertionError("expected network failure guidance")
        if "--version" not in result.output:
            raise AssertionError(
                "expected network failure to suggest --version fallback"
            )
        if fake_log.exists():
            raise AssertionError("expected network failure to avoid running uv")


def check_self_update_handles_http_error() -> None:
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

        http_error = urllib.error.HTTPError(
            url="https://api.github.com/repos/EraserandRain/envmgr/releases/latest",
            code=403,
            msg="rate limit exceeded",
            hdrs=Message(),
            fp=None,
        )
        with patch(
            "urllib.request.urlopen",
            side_effect=http_error,
        ):
            result = _invoke_envmgr_with_home(envmgr_home, "self", "update")

        if result.exit_code != 1:
            raise AssertionError(
                _format_failure(
                    "expected HTTP error during latest resolution to fail", result
                )
            )
        if "HTTP 403" not in result.output:
            raise AssertionError("expected HTTP error code in output")
        if "--version" not in result.output:
            raise AssertionError("expected HTTP error to suggest --version fallback")
        if fake_log.exists():
            raise AssertionError("expected HTTP error to avoid running uv")


def check_self_update_handles_invalid_github_response() -> None:
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

        with patch(
            "urllib.request.urlopen",
            return_value=_mock_github_latest_response("not json"),
        ):
            result = _invoke_envmgr_with_home(envmgr_home, "self", "update")

        if result.exit_code != 1:
            raise AssertionError(
                _format_failure("expected invalid JSON response to fail", result)
            )
        if "--version" not in result.output or "VERSION to update" not in result.output:
            raise AssertionError("expected invalid response to suggest --version")
        if fake_log.exists():
            raise AssertionError("expected invalid response to avoid running uv")


def check_self_update_handles_empty_tag_name() -> None:
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

        with patch(
            "urllib.request.urlopen",
            return_value=_mock_github_latest_response('{"tag_name": ""}'),
        ):
            result = _invoke_envmgr_with_home(envmgr_home, "self", "update")

        if result.exit_code != 1:
            raise AssertionError(
                _format_failure("expected empty tag_name to fail", result)
            )
        if "--version" not in result.output or "VERSION to update" not in result.output:
            raise AssertionError("expected empty tag_name to suggest --version")
        if fake_log.exists():
            raise AssertionError("expected empty tag_name to avoid running uv")


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


# ---------------------------------------------------------------------------
# update-check helpers
# ---------------------------------------------------------------------------


def _make_empty_cache(cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)


def _make_fresh_cache(cache_path: Path, version: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_check": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latest_version": version,
    }
    cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _make_stale_cache(cache_path: Path, version: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    stale_time = datetime.now(timezone.utc) - timedelta(hours=25)
    payload = {
        "last_check": stale_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latest_version": version,
    }
    cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# update check contract tests
# ---------------------------------------------------------------------------


def check_update_newer_recognises_newer_version() -> None:
    from envmgr.services.update_check import _newer

    if not _newer("v0.2.0", "0.1.0"):
        raise AssertionError("expected v0.2.0 > 0.1.0")
    if not _newer("v1.0.0", "0.9.9"):
        raise AssertionError("expected v1.0.0 > 0.9.9")
    if not _newer("v0.1.1", "0.1.0"):
        raise AssertionError("expected v0.1.1 > 0.1.0")


def check_update_newer_rejects_same_or_older() -> None:
    from envmgr.services.update_check import _newer

    if _newer("v0.1.0", "0.1.0"):
        raise AssertionError("expected v0.1.0 == 0.1.0")
    if _newer("v0.0.9", "0.1.0"):
        raise AssertionError("expected v0.0.9 < 0.1.0")
    if _newer("", "0.1.0"):
        raise AssertionError("expected empty string to not be newer")
    if _newer("not-a-version", "0.1.0"):
        raise AssertionError("expected non-version to not be newer")


def check_update_cache_read_write_and_freshness() -> None:
    from envmgr.services.update_check import (
        _cache_fresh,
        _cache_path,
        _read_cache,
        _write_cache,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        home = Path(temp_dir) / ".envmgr"
        cache_path = _cache_path(home)

        # Missing cache is not fresh
        if _cache_fresh(cache_path):
            raise AssertionError("expected missing cache to not be fresh")

        # Write and read back
        _write_cache(cache_path, "v0.2.0")
        version, last_check = _read_cache(cache_path)
        if version != "v0.2.0":
            raise AssertionError(f"expected v0.2.0, got {version}")
        if last_check is None:
            raise AssertionError("expected a timestamp")

        # Freshly written cache should be fresh
        if not _cache_fresh(cache_path):
            raise AssertionError("expected just-written cache to be fresh")

        # Stale cache should not be fresh
        _make_stale_cache(cache_path, "v0.1.0")
        if _cache_fresh(cache_path):
            raise AssertionError("expected stale cache to not be fresh")


def check_update_run_check_uses_cached_result_when_fresh() -> None:
    from envmgr.services.update_check import _run_check

    with tempfile.TemporaryDirectory() as temp_dir:
        home = Path(temp_dir) / ".envmgr"
        cache_path = home / "update-check.json"

        # Plant a fresh cache claiming v99.0.0 is the latest
        _make_fresh_cache(cache_path, "v99.0.0")

        # _run_check should trust the cache without touching the network
        latest_tag, _current = _run_check(home)
        if latest_tag is None:
            raise AssertionError(
                "expected notification because cached v99.0.0 > current version"
            )
        if "v99.0.0" not in latest_tag:
            raise AssertionError(f"expected tag to be v99.0.0, got: {latest_tag}")


def check_update_run_check_returns_none_when_current_is_latest() -> None:
    from envmgr.services.update_check import _current_version, _run_check

    with tempfile.TemporaryDirectory() as temp_dir:
        home = Path(temp_dir) / ".envmgr"
        cache_path = home / "update-check.json"

        # Plant a fresh cache claiming the *current* version is latest
        current = _current_version()
        _make_fresh_cache(cache_path, f"v{current}")

        latest_tag, _current_out = _run_check(home)
        if latest_tag is not None:
            raise AssertionError(
                f"expected no notification when current is latest, got: {latest_tag}"
            )


def check_update_run_check_fetches_when_cache_stale() -> None:
    from envmgr.services.update_check import _run_check

    with tempfile.TemporaryDirectory() as temp_dir:
        home = Path(temp_dir) / ".envmgr"
        cache_path = home / "update-check.json"

        # Plant a stale cache with a low version
        _make_stale_cache(cache_path, "v0.0.1")

        with patch(
            "envmgr.services.update_check._fetch_latest_tag",
            return_value="v99.0.0",
        ):
            latest_tag, _current = _run_check(home)

        if latest_tag is None:
            raise AssertionError("expected notification after network fetch")
        if "v99.0.0" not in latest_tag:
            raise AssertionError(f"expected tag to be v99.0.0, got: {latest_tag}")

        # Cache should have been refreshed
        version, _ = __import__(
            "envmgr.services.update_check", fromlist=["_read_cache"]
        )._read_cache(cache_path)
        if version != "v99.0.0":
            raise AssertionError(
                f"expected cache to be updated to v99.0.0, got {version}"
            )


def check_update_run_check_handles_network_failure_gracefully() -> None:
    from envmgr.services.update_check import _run_check

    with tempfile.TemporaryDirectory() as temp_dir:
        home = Path(temp_dir) / ".envmgr"
        cache_path = home / "update-check.json"

        # No cache at all + network failure → no notification, no crash
        _make_empty_cache(cache_path)
        with patch(
            "envmgr.services.update_check._fetch_latest_tag",
            return_value=None,
        ):
            latest_tag, _current = _run_check(home)

        if latest_tag is not None:
            raise AssertionError(
                f"expected no notification on network failure, got: {latest_tag}"
            )


def check_update_run_check_falls_back_to_stale_cache_on_failure() -> None:
    from envmgr.services.update_check import _run_check

    with tempfile.TemporaryDirectory() as temp_dir:
        home = Path(temp_dir) / ".envmgr"
        cache_path = home / "update-check.json"

        # Stale cache with a newer version + network failure
        _make_stale_cache(cache_path, "v99.0.0")
        with patch(
            "envmgr.services.update_check._fetch_latest_tag",
            return_value=None,
        ):
            latest_tag, _current = _run_check(home)

        if latest_tag is None:
            raise AssertionError(
                "expected notification from stale cache despite network failure"
            )
        if "v99.0.0" not in latest_tag:
            raise AssertionError(
                f"expected tag to mention cached v99.0.0, got: {latest_tag}"
            )


def check_update_should_notify_skips_in_ci() -> None:
    from envmgr.services.update_check import _should_notify

    with patch.dict(os.environ, {"CI": "true"}, clear=False):
        if _should_notify():
            raise AssertionError("expected _should_notify to return False in CI")


def check_update_should_notify_skips_with_env_var() -> None:
    from envmgr.services.update_check import _should_notify

    with patch.dict(os.environ, {"NO_UPDATE_NOTIFIER": "1"}, clear=False):
        if _should_notify():
            raise AssertionError(
                "expected _should_notify to return False with NO_UPDATE_NOTIFIER"
            )


def check_update_should_notify_skips_during_self_update() -> None:
    from envmgr.services.update_check import _should_notify

    with (
        patch.object(sys, "argv", ["envmgr", "self", "update"]),
        patch.object(sys.stderr, "isatty", return_value=True),
    ):
        if _should_notify():
            raise AssertionError(
                "expected _should_notify to return False during self update"
            )


def check_update_should_notify_skips_during_self_uninstall() -> None:
    from envmgr.services.update_check import _should_notify

    with (
        patch.object(sys, "argv", ["envmgr", "self", "uninstall"]),
        patch.object(sys.stderr, "isatty", return_value=True),
    ):
        if _should_notify():
            raise AssertionError(
                "expected _should_notify to return False during self uninstall"
            )


def check_update_render_notice_includes_expected_content() -> None:
    from io import StringIO

    from envmgr.services.update_check import _render_notice, _stderr

    # Capture Rich-styled stderr output
    buf = StringIO()
    original_file = _stderr.file
    try:
        _stderr.file = buf
        _render_notice("v0.2.0", "0.1.0")
        output = buf.getvalue()
    finally:
        _stderr.file = original_file

    if "v0.2.0" not in output:
        raise AssertionError("expected notice to include latest version")
    if "0.1.0" not in output:
        raise AssertionError("expected notice to include current version")
    if "envmgr self update" not in output:
        raise AssertionError("expected notice to include update command")
