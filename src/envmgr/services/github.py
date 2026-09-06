"""Shared helpers for GitHub REST API requests.

envmgr calls the GitHub Releases API from the installer-managed ``self update``
command and from the background update-available check.  Both go through the
anonymous rate limit unless a token is supplied, which is easy to exhaust on a
shared egress IP.  This module centralizes the request headers so callers send
an authenticated ``Authorization`` header whenever ``GITHUB_TOKEN`` is set.
"""

from __future__ import annotations

import os

GITHUB_TOKEN_ENV_VAR = "GITHUB_TOKEN"


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
