"""GitHub Releases API client.

envmgr calls the GitHub Releases API from the installer-managed ``self update``
command and from the background update-available check.  Both used to build the
same URL, request, and ``tag_name`` parse independently, which left release API
knowledge scattered across two modules.  This module is the single owner of that
knowledge: it builds the release URL, requests it with an authenticated header
whenever ``GITHUB_TOKEN`` is set, parses the latest ``tag_name``, and raises
``GitHubAPIError`` on failure.  Callers apply their own policy on top — ``self
update`` re-raises with user-facing guidance, the background check swallows the
error and returns ``None``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Literal

GITHUB_TOKEN_ENV_VAR = "GITHUB_TOKEN"

#: GitHub Releases "latest release" endpoint template. Single source of truth.
_RELEASES_LATEST_URL = "https://api.github.com/repos/{owner}/{repo}/releases/latest"

ErrorKind = Literal["http", "network", "parse", "invalid"]


class GitHubAPIError(RuntimeError):
    """Raised when the GitHub Releases API cannot be resolved."""

    def __init__(
        self,
        message: str,
        *,
        kind: ErrorKind,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status_code = status_code


def github_api_headers() -> dict[str, str]:
    """Return headers for a GitHub REST API request.

    When ``GITHUB_TOKEN`` is set, the headers include an ``Authorization:
    Bearer`` value so the request uses the token's rate limit instead of the
    anonymous 60-requests/hour limit.  The token is read at call time and is
    never persisted or logged.
    """
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get(GITHUB_TOKEN_ENV_VAR)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _latest_release_url(owner: str, repo: str) -> str:
    """Build the GitHub Releases latest-release URL for an owner/repo."""
    return _RELEASES_LATEST_URL.format(owner=owner, repo=repo)


def latest_release_tag(owner: str, repo: str, *, timeout: int = 10) -> str:
    """Resolve the latest GitHub Release tag, raising ``GitHubAPIError`` on failure."""
    api_url = _latest_release_url(owner, repo)
    request = urllib.request.Request(api_url, headers=github_api_headers())
    try:
        # S310 (ssrf): safe — URL is constructed from the owner/repo passed by
        # the caller (installer state or constants), not user-supplied input.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise GitHubAPIError(
            f"GitHub returned HTTP {error.code} while resolving the latest release.",
            kind="http",
            status_code=error.code,
        ) from error
    except (urllib.error.URLError, OSError) as error:
        raise GitHubAPIError(
            "Could not reach GitHub to resolve the latest release.",
            kind="network",
        ) from error

    try:
        release_data = json.loads(body)
    except json.JSONDecodeError as error:
        raise GitHubAPIError(
            "GitHub returned an unexpected response while resolving the latest release.",
            kind="parse",
        ) from error

    tag_name = release_data.get("tag_name") if isinstance(release_data, dict) else None
    if not isinstance(tag_name, str) or not tag_name.strip():
        raise GitHubAPIError(
            "Could not determine the latest release tag from the GitHub API response.",
            kind="invalid",
        )

    return tag_name.strip()
