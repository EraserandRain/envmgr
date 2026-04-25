#!/usr/bin/env bash
set -euo pipefail

GITHUB_OWNER="EraserandRain"
GITHUB_REPO="envmgr"
DEFAULT_VERSION="0.1.0"
HELPER_SHIMS=(create lint ansible-check typecheck validate smoke-test)

usage() {
  printf '%s\n' \
    "envmgr GitHub Release installer" \
    "" \
    "Usage:" \
    "  curl -fsSL https://github.com/EraserandRain/envmgr/releases/latest/download/install.sh | bash" \
    "  bash install.sh [options]" \
    "" \
    "Options:" \
    "  --version VERSION   Install a specific release version, for example 0.1.0 or v0.1.0." \
    "  --dry-run           Print the planned uv command and state path without installing." \
    "  --no-modify-path    Documented no-op; this installer never edits shell profiles or PATH files." \
    "  -h, --help          Show this help message." \
    "" \
    "The installer requires uv to already be installed and uses:" \
    "  uv tool install --force <github-release-wheel-url>"
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'envmgr installer: %s\n' "$*" >&2
  exit 1
}

normalize_package_version() {
  local requested="$1"
  local package_version="${requested#v}"

  if [[ -z "$package_version" || "$package_version" == "$requested" && "$requested" == v* ]]; then
    die "version must be a concrete release such as 0.1.0 or v0.1.0"
  fi

  printf '%s\n' "$package_version"
}

release_tag_for_version() {
  local requested="$1"

  if [[ "$requested" == v* ]]; then
    printf '%s\n' "$requested"
  else
    printf 'v%s\n' "$requested"
  fi
}

resolve_envmgr_home() {
  if [[ -n "${ENVMGR_HOME:-}" ]]; then
    printf '%s\n' "$ENVMGR_HOME"
    return
  fi

  if [[ -z "${HOME:-}" ]]; then
    die "HOME is not set; set ENVMGR_HOME to choose the envmgr state directory"
  fi

  printf '%s/.envmgr\n' "$HOME"
}

toml_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/ }"
  printf '%s' "$value"
}

write_install_state() {
  local state_file="$1"
  local package_version="$2"
  local release_tag="$3"
  local wheel_url="$4"
  local uv_path="$5"
  local uv_tool_bin_dir="$6"
  local installed_at

  installed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  mkdir -p "$(dirname "$state_file")"
  cat >"$state_file" <<EOF
[install]
source = "github-release"
manager = "install.sh"
owner = "$(toml_escape "$GITHUB_OWNER")"
repo = "$(toml_escape "$GITHUB_REPO")"
version = "$(toml_escape "$package_version")"
release_tag = "$(toml_escape "$release_tag")"
wheel_url = "$(toml_escape "$wheel_url")"
installed_at = "$(toml_escape "$installed_at")"
uv = "$(toml_escape "$uv_path")"
uv_tool_bin_dir = "$(toml_escape "$uv_tool_bin_dir")"
EOF
}

find_tool_in_bin_dir() {
  local bin_dir="$1"
  local command_name="$2"
  local candidate

  for candidate in "$bin_dir/$command_name" "$bin_dir/$command_name.exe"; do
    if [[ -e "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

version="$DEFAULT_VERSION"
dry_run=false
no_modify_path=false

while (($#)); do
  case "$1" in
    --version)
      shift
      if (($# == 0)); then
        die "--version requires a VERSION value"
      fi
      version="$1"
      ;;
    --version=*)
      version="${1#--version=}"
      ;;
    --dry-run)
      dry_run=true
      ;;
    --no-modify-path)
      no_modify_path=true
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
  shift
done

package_version="$(normalize_package_version "$version")"
release_tag="$(release_tag_for_version "$version")"
wheel_url="https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/releases/download/${release_tag}/${GITHUB_REPO}-${package_version}-py3-none-any.whl"
envmgr_home="$(resolve_envmgr_home)"
state_file="${envmgr_home%/}/install.toml"

log "envmgr GitHub Release installer"
log "Planned release: ${release_tag}"
log "Planned wheel: ${wheel_url}"
log "Planned install command: uv tool install --force ${wheel_url}"
log "Installer state file: ${state_file}"
log "PATH handling: no shell profiles or hidden PATH files will be modified."
if [[ "$no_modify_path" == true ]]; then
  log "--no-modify-path acknowledged; it is a no-op because PATH is never modified."
fi

if [[ "$dry_run" == true ]]; then
  log "Dry run complete; no commands were executed."
  exit 0
fi

uv_path="$(command -v uv || true)"
if [[ -z "$uv_path" ]]; then
  die "uv was not found in PATH. Install uv first: https://docs.astral.sh/uv/getting-started/installation/ . This installer does not bootstrap uv yet."
fi

uv_tool_bin_dir="$("$uv_path" tool dir --bin 2>/dev/null)" || die "could not determine the uv tool bin directory with: uv tool dir --bin"
if [[ -z "$uv_tool_bin_dir" ]]; then
  die "uv tool dir --bin returned an empty path"
fi

log "Using uv: ${uv_path}"
log "Using uv tool bin directory: ${uv_tool_bin_dir}"
log "Running: uv tool install --force ${wheel_url}"
"$uv_path" tool install --force "$wheel_url"

envmgr_command="$(find_tool_in_bin_dir "$uv_tool_bin_dir" envmgr)" || die "expected envmgr in the uv tool bin directory after install: ${uv_tool_bin_dir}"
if [[ ! -x "$envmgr_command" ]]; then
  die "envmgr exists but is not executable: ${envmgr_command}"
fi

envmgr_version_output="$("$envmgr_command" --version 2>&1)" || die "installed envmgr failed verification: ${envmgr_command} --version"
if [[ "$envmgr_version_output" != envmgr\ * ]]; then
  die "installed envmgr returned unexpected version output: ${envmgr_version_output}"
fi
log "Verified envmgr: ${envmgr_version_output}"

for helper in "${HELPER_SHIMS[@]}"; do
  if helper_path="$(find_tool_in_bin_dir "$uv_tool_bin_dir" "$helper")"; then
    die "unexpected checkout-only helper shim found after install: ${helper_path}. Remove stale envmgr tool shims, then rerun the installer."
  fi
done
log "Verified checkout-only helper shims were not installed."

write_install_state "$state_file" "$package_version" "$release_tag" "$wheel_url" "$uv_path" "$uv_tool_bin_dir"
log "Recorded installer state: ${state_file}"
log "envmgr installation complete."
