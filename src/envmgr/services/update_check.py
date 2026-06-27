"""Non-blocking update-available check with 24 h local cache.

Spawns a daemon thread that checks the GitHub Releases API on CLI startup
(after the cache TTL expires) and prints a one-line notice to stderr when a
newer version is available.  Network errors are silently ignored.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from importlib import metadata
from pathlib import Path

from rich.console import Console
from rich.style import Style
from rich.text import Text

_CHECK_INTERVAL = timedelta(hours=24)
_DEFAULT_OWNER = "EraserandRain"
_DEFAULT_REPO = "envmgr"
_GITHUB_LATEST = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
_CACHE_FILENAME = "update-check.json"
_SELF_SKIP_COMMANDS = frozenset({"update", "uninstall"})

_stderr = Console(stderr=True, highlight=False)
_NOTICE_STYLE = Style(color="bright_yellow", bold=True)
_VERSION_STYLE = Style(color="bright_green")
_CURRENT_STYLE = Style(color="bright_black")
_CMD_STYLE = Style(color="bright_cyan")


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------


def start_update_check_background(envmgr_home: str | Path | None = None) -> None:
    """Fire a daemon thread that checks for a newer envmgr release.

    The check is skipped when any of these hold:
    * ``CI`` is set
    * ``NO_UPDATE_NOTIFIER`` is set
    * stderr is not a TTY
    * the command is ``envmgr self update`` or ``envmgr self uninstall``
    """

    if not _should_notify():
        return

    if envmgr_home is None:
        envmgr_home = Path(os.environ.get("ENVMGR_HOME", str(Path.home() / ".envmgr")))

    thread = threading.Thread(
        target=_check_and_notify,
        args=(Path(envmgr_home),),
        daemon=True,
    )
    thread.start()


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _should_notify() -> bool:
    if os.environ.get("CI"):
        return False
    if os.environ.get("NO_UPDATE_NOTIFIER"):
        return False
    if not sys.stderr.isatty():
        return False

    # Skip during self update / uninstall — the user is already managing
    # their install.
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "self" and args[1] in _SELF_SKIP_COMMANDS:
        return False

    return True


def _current_version() -> str:
    try:
        return metadata.version("envmgr")
    except metadata.PackageNotFoundError:
        return "0+unknown"


def _cache_path(envmgr_home: Path) -> Path:
    return envmgr_home / _CACHE_FILENAME


def _read_cache(cache_path: Path) -> tuple[str | None, datetime | None]:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        last_check = datetime.fromisoformat(data["last_check"])
        latest_version: str | None = data.get("latest_version")
        return latest_version, last_check
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None, None


def _write_cache(cache_path: Path, latest_version: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_check": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latest_version": latest_version,
    }
    cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fetch_latest_tag() -> str | None:
    """Return the latest GitHub Release tag name, or *None* on any error."""
    url = _GITHUB_LATEST.format(owner=_DEFAULT_OWNER, repo=_DEFAULT_REPO)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:  # noqa: S310
            body = response.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None

    tag: str | None = data.get("tag_name") if isinstance(data, dict) else None
    if isinstance(tag, str) and tag.strip():
        return tag.strip()
    return None


def _cache_fresh(cache_path: Path) -> bool:
    _, last_check = _read_cache(cache_path)
    if last_check is None:
        return False
    return datetime.now(timezone.utc) - last_check <= _CHECK_INTERVAL


def _newer(latest_tag: str, current: str) -> bool:
    """Semver-aware comparison: *True* when *latest_tag* > *current*."""

    def _parts(version: str) -> list[int]:
        try:
            return [int(p) for p in version.lstrip("v").split(".")]
        except (ValueError, AttributeError):
            return []

    latest_parts = _parts(latest_tag)
    current_parts = _parts(current)
    if not latest_parts or not current_parts:
        return False
    return latest_parts > current_parts


def _check_and_notify(envmgr_home: Path) -> None:
    try:
        latest_tag, current = _run_check(envmgr_home)
        if latest_tag is not None:
            _render_notice(latest_tag, current)
    except Exception:
        pass  # never let a broken update check affect the user


def _run_check(envmgr_home: Path) -> tuple[str | None, str]:
    """Core check logic, returns ``(latest_tag_or_None, current_version)``."""
    cache_path = _cache_path(envmgr_home)
    current = _current_version()

    # ── cached path ──────────────────────────────────────────────────
    cached_version, _ = _read_cache(cache_path)
    if cached_version is not None and _cache_fresh(cache_path):
        if _newer(cached_version, current):
            return cached_version, current
        return None, current

    # ── network path ─────────────────────────────────────────────────
    latest = _fetch_latest_tag()
    if latest is None:
        # If we have a stale cache entry, still use it so that a
        # transient network failure doesn't suppress an existing notice.
        if cached_version is not None and _newer(cached_version, current):
            return cached_version, current
        return None, current

    _write_cache(cache_path, latest)

    if _newer(latest, current):
        return latest, current

    return None, current


def _render_notice(latest_tag: str, current: str) -> None:
    """Print a Rich-styled update-available notice to stderr."""
    # Leading newline ensures the notice stands apart from preceding output.
    _stderr.print()
    notice = Text.assemble(
        ("⚠  ", _NOTICE_STYLE),
        ("Update available!  ", _NOTICE_STYLE),
        (current, _CURRENT_STYLE),
        (" → ", _NOTICE_STYLE),
        (latest_tag, _VERSION_STYLE),
    )
    _stderr.print(notice)
    hint = Text.assemble(
        ("   Run ", Style(dim=True)),
        ("envmgr self update", _CMD_STYLE),
        (" to upgrade.", Style(dim=True)),
    )
    _stderr.print(hint)
