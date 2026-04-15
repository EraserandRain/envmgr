#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
compose_file="$repo_root/.github/e2e/docker-compose.yml"
compose_dir=$(dirname "$compose_file")

python3 - "$compose_file" "$compose_dir" <<'PY'
import os
import re
import sys

compose_file, compose_dir = sys.argv[1:3]
context_re = re.compile(r"^\s*context:\s*(.+?)\s*$")
build_re = re.compile(r"^\s*build:\s*([^\s{].*?)\s*$")
missing = []

with open(compose_file, encoding="utf-8") as handle:
    for lineno, line in enumerate(handle, 1):
        match = context_re.match(line) or build_re.match(line)
        if match is None:
            continue

        raw_value = match.group(1).split("#", 1)[0].strip().strip("'\"")
        if not raw_value or raw_value.startswith("${") or "://" in raw_value:
            continue

        resolved_path = (
            raw_value
            if os.path.isabs(raw_value)
            else os.path.normpath(os.path.join(compose_dir, raw_value))
        )
        if not os.path.exists(resolved_path):
            missing.append((lineno, raw_value, resolved_path))

if missing:
    print("Docker Compose sanity check failed: missing build context path(s):", file=sys.stderr)
    for lineno, raw_value, resolved_path in missing:
        print(
            f"  {compose_file}:{lineno}: {raw_value} -> {resolved_path}",
            file=sys.stderr,
        )
    sys.exit(1)
PY

# Keep config validation separate from the path scan so CI fails with a clearer error first.
E2E_AUTHORIZED_KEYS="${E2E_AUTHORIZED_KEYS:-sanity-check-placeholder}" \
  docker compose -f "$compose_file" config >/dev/null
