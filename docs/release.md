# Release Guide

This guide keeps release audit and distribution details out of the README. Use
it when preparing GitHub Release artifacts, auditing installer behavior, or
writing release notes.

## Release Audit

Before publishing a release tag:

- Confirm the versioned commit is final and the tag will be immutable.
- Run `uv sync --locked`.
- Run `envmgr setup` or `uv run envmgr setup` from the checkout fallback.
- Run `uv run validate`.
- Run `uv run smoke-test`.
- Run `uv build --no-sources`.
- Inspect wheel and sdist contents for packaged runtime assets.
- Verify installed wheels expose only the public `envmgr` runtime command.
- Verify checkout-only helpers are not exposed by installed wheels.
- Generate and verify SHA256 checksums for all release assets.
- Smoke-test an isolated wheel install with `uv tool install`.

## Release Workflow

GitHub Release publishing is tag-driven. Push version tags matching `vX.Y.Z`
only after the release commit is ready. The release workflow runs locked
dependency sync, setup, validation, smoke tests, release-style builds, artifact
inspection, installer preparation, SHA256 checksum generation, isolated wheel
install smoke testing, changelog generation via
[git-cliff](https://github.com/orhun/git-cliff), and `gh release create`. The
workflow prepends fixed install, SHA256 verification, upgrade, uninstall, and
clean-reinstall guidance; git-cliff appends the changelog from Conventional
Commits history.

Release artifacts should include only:

- `envmgr-<version>-py3-none-any.whl`
- `envmgr-<version>.tar.gz`
- `install.sh`
- `SHA256SUMS`

Never publish an `envmgr-dev-helpers` artifact. Installed wheels must not expose
checkout-only helper shims such as `create`, `lint`, `ansible-check`,
`typecheck`, `validate`, or `smoke-test`.

## Installer Audit

Users should be able to inspect and verify release assets before running the
installer:

```bash
release=v0.1.0
version="${release#v}"
base="https://github.com/EraserandRain/envmgr/releases/download/${release}"

curl -fsSLO "${base}/envmgr-${version}-py3-none-any.whl"
curl -fsSLO "${base}/envmgr-${version}.tar.gz"
curl -fsSLO "${base}/install.sh"
curl -fsSLO "${base}/SHA256SUMS"

sha256sum -c SHA256SUMS
less install.sh
bash install.sh --dry-run --version "${version}"
```

The installer uses `uv tool install --force` against the release wheel, records
installer-managed state under `~/.envmgr/install.toml`, and does not edit shell
profiles or hidden PATH files. `--version VERSION` pins a release, and
`--dry-run` prints the planned wheel URL and command.

## Self-management

Installer-managed GitHub Release installs can update or remove themselves:

```bash
envmgr self update
envmgr self update --version 0.1.0
envmgr self uninstall --yes
```

`envmgr self update` resolves the latest GitHub Release by default. Pass
`--version` to pin a specific release. `envmgr self uninstall` prompts
through Rich unless `--yes` or `-y` is provided, removes installer state and the
uv tool install, and preserves runtime data under `~/.envmgr/`.

Non-installer installs should be updated or removed with the same tool that
created them. For stale shims from an older install, run `uv tool uninstall
envmgr`, rerun the GitHub Release installer, and run `hash -r` in existing
shells.

## Release Notes Checklist

git-cliff generates the changelog body from Conventional Commits history.
The workflow prepends fixed guidance that includes:

- Install guidance that links to `install.sh`.
- SHA256 verification guidance.
- Upgrade guidance with `envmgr self update [--version <version>]`.
- Uninstall guidance with `envmgr self uninstall [--yes]`.
- Clean-reinstall guidance for stale shims.

## CI Alignment

Keep release automation aligned with the main validation, smoke, package
surface, init-install, and Docker Compose master/worker e2e jobs. If runtime
command exposure, packaged assets, installer behavior, or helper entrypoints
change, update CI and this release guide in the same patch.
