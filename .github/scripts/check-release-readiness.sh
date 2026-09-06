#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Check that a dev -> master release PR would actually produce a release tag.
#
# Merges to master are the release boundary: auto-tag.yml computes the next
# semver from Conventional Commits via git-cliff.  If a "release" PR only
# carries docs/chore/refactor/perf/test/ci commits, git-cliff will not bump a
# version, no tag is created, and the merge silently fails to publish.
#
# This script uses the same git-cliff invocation that auto-tag.yml runs on
# merge, so it predicts exactly what the release will do.  Because git-cliff
# reports the base (already-tagged) version rather than an empty string when
# nothing warrants a bump, the script compares against the latest tag.  It
# prints the would-be tag and exits 0 when a release is produced, and exits 1
# when it is not.
# ---------------------------------------------------------------------------
set -uo pipefail

log() { printf '%s\n' "$*"; }

# Prune any whitespace and mirror auto-tag.yml: the bumped version is the last
# line git-cliff prints.  A non-zero exit here means git-cliff itself failed
# (for example, no tags available in the checkout), which is an error worth
# surfacing rather than a "no release" outcome.
bump_output="$(git cliff --bump --bumped-version 2>&1 | tail -1)" || {
  log "::error::git-cliff failed to compute the next version (is git-cliff installed and were tags fetched?)"
  exit 2
}

bumped_version="$(printf '%s' "${bump_output}" | tr -d '[:space:]')"

# git-cliff reports the base (already-tagged) version -- not an empty string --
# when no Conventional Commit warrants a bump. Compare against the latest tag
# so a batch of docs/chore/refactor commits is correctly treated as non-release.
latest_tag="$(git describe --tags --abbrev=0 2>/dev/null)" || latest_tag=""

if [[ -z "${bumped_version}" || "${bumped_version}" == "${latest_tag}" ]]; then
  log "::error::Merging this release PR would not create a new release tag."
  log "::error::git-cliff found no bump-worthy Conventional Commits since ${latest_tag:-the last tag}."
  log "::error::Add a 'feat:', 'fix:', or breaking ('!') Conventional Commit to publish a release."
  exit 1
fi

log "This release PR will produce tag ${bumped_version}"
