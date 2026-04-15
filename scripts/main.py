import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

from .catalog import (
    CatalogError,
    RoleMetadata,
    build_playbook_tag_index,
    get_available_tags,
    load_role_catalog,
)
from .runtime_config import (
    SETUP_SCHEMA_VERSION,
    ConfigError,
    RuntimeConfig,
    RuntimePaths,
    ensure_runtime_layout,
    get_runtime_paths,
    is_runtime_setup_complete,
    load_runtime_config,
    mark_runtime_setup_complete,
    resolve_inventory_reference,
)
from .scaffold import ScaffoldError, generate_role


# ANSI color codes
class Colors:
    GREEN = "\033[32m"
    RED = "\033[31m"
    RESET = "\033[0m"


DEFAULT_PLAYBOOKS = [
    "playbooks/workstation.yml",
    "playbooks/node.yml",
]
AI_TOOLS_CONTEXT7_METHODS = ("remote", "local")


@dataclass(frozen=True)
class AiToolsInstallOptions:
    manage_claude_code: bool
    manage_codex: bool
    enable_context7: bool
    claude_context7_method: str
    codex_context7_method: str


class WizardCancelled(RuntimeError):
    """Raised when the interactive setup wizard is cancelled by the user."""


def run_command_step(
    step_name: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
) -> bool:
    """Run one validation step and report its outcome."""
    print(f"\n[{step_name}] {' '.join(command)}")
    try:
        subprocess.run(command, check=True, env=env)
        print(f"✓ {step_name} passed")
        return True
    except subprocess.CalledProcessError as error:
        print(f"✗ {step_name} failed with exit code {error.returncode}")
        return False
    except FileNotFoundError:
        print(f"✗ {step_name} failed because '{command[0]}' was not found in PATH")
        return False


def run_assertion_step(step_name: str, check: Callable[[], None]) -> bool:
    """Run one Python-level smoke-test assertion and report its outcome."""
    print(f"\n[{step_name}]")
    try:
        check()
        print(f"✓ {step_name} passed")
        return True
    except (
        AssertionError,
        CatalogError,
        ConfigError,
        FileNotFoundError,
        ScaffoldError,
    ) as error:
        print(f"✗ {step_name} failed: {error}")
        return False


def load_available_tags() -> tuple[list[str], list[str]]:
    """Load role-level and task-level tags from role metadata."""
    try:
        return get_available_tags("roles")
    except CatalogError as error:
        print(f"{Colors.RED}Metadata error: {error}{Colors.RESET}")
        raise SystemExit(1) from error


def resolve_inventory_option(selected_inventory: str | None) -> tuple[Path, str]:
    """Resolve an inventory alias from ~/.envmgr/config.toml."""
    try:
        return resolve_inventory_reference(selected_inventory)
    except ConfigError as error:
        print(f"{Colors.RED}Configuration error: {error}{Colors.RESET}")
        raise SystemExit(1) from error


def load_runtime_config_option() -> RuntimeConfig:
    """Load ~/.envmgr/config.toml and surface a user-friendly configuration error."""
    try:
        return load_runtime_config()
    except ConfigError as error:
        print(f"{Colors.RED}Configuration error: {error}{Colors.RESET}")
        raise SystemExit(1) from error


def require_setup_completed(
    command_name: str,
    *,
    envmgr_home: str | Path | None = None,
) -> None:
    """Exit with setup guidance when the runtime has not been bootstrapped yet."""
    runtime_paths = get_runtime_paths(envmgr_home)
    if is_runtime_setup_complete(runtime_paths):
        return

    print(
        f"{Colors.RED}Setup required: '{command_name}' needs a bootstrapped envmgr "
        f"runtime at {runtime_paths.home}. Please run `uv run setup` first."
        f"{Colors.RESET}"
    )
    raise SystemExit(1)


def resolve_default_playbook_path(config: RuntimeConfig) -> str:
    """Resolve the configured default playbook name into a repository playbook path."""
    configured_playbook = Path(config.default_playbook)
    if configured_playbook.suffix in {".yml", ".yaml"}:
        return str(configured_playbook)
    return str(Path("playbooks") / f"{config.default_playbook}.yml")


def merge_path_entries(entries: list[str]) -> str:
    """Merge search-path entries while preserving order and removing duplicates."""
    unique_entries: list[str] = []
    seen_entries: set[str] = set()
    for entry in entries:
        if not entry or entry in seen_entries:
            continue
        seen_entries.add(entry)
        unique_entries.append(entry)
    return os.pathsep.join(unique_entries)


def build_ansible_runtime_env(paths: RuntimePaths) -> dict[str, str]:
    """Build a consistent Ansible runtime environment rooted in ~/.envmgr."""
    env = os.environ.copy()
    env["ANSIBLE_FORCE_COLOR"] = "true"
    env["ANSIBLE_LOG_PATH"] = str(paths.ansible_log_file)
    env["ANSIBLE_ROLES_PATH"] = merge_path_entries(
        [
            str(Path("roles").resolve()),
            str(paths.galaxy_roles_dir),
        ]
    )
    env["ANSIBLE_COLLECTIONS_PATH"] = merge_path_entries(
        [
            str(paths.galaxy_collections_dir),
        ]
    )
    env["ANSIBLE_LOCAL_TEMP"] = str(paths.tmp_dir)
    return env


def get_existing_default_playbooks() -> list[str]:
    """Return default scenario playbooks that exist in the repository."""
    return [playbook for playbook in DEFAULT_PLAYBOOKS if Path(playbook).exists()]


def resolve_selected_role_metadata(
    selected_tags: list[str],
    roles_dir: str | Path = "roles",
) -> dict[str, RoleMetadata]:
    """Resolve selected tags into a role closure that includes declared dependencies."""
    catalog = [
        metadata for metadata in load_role_catalog(roles_dir) if metadata.enabled
    ]
    metadata_by_name = {metadata.name: metadata for metadata in catalog}
    resolved_metadata: dict[str, RoleMetadata] = {}

    def add_metadata(metadata: RoleMetadata) -> None:
        if metadata.name in resolved_metadata:
            return
        resolved_metadata[metadata.name] = metadata
        for dependency_name in metadata.depends_on:
            dependency = metadata_by_name.get(dependency_name)
            if dependency is None:
                raise CatalogError(
                    f"role '{metadata.name}' depends on unknown role '{dependency_name}'"
                )
            add_metadata(dependency)

    for selected_tag in selected_tags:
        matched_metadata = [
            metadata
            for metadata in catalog
            if selected_tag in metadata.tags or selected_tag in metadata.task_tags
        ]
        if not matched_metadata:
            raise CatalogError(
                f"selected tag '{selected_tag}' does not map to a catalog role"
            )

        for metadata in matched_metadata:
            add_metadata(metadata)

    return resolved_metadata


def read_playbook_role_name(role_entry: Any, playbook_path: Path) -> str:
    """Read a role name from a playbook role entry."""
    if isinstance(role_entry, str):
        return role_entry

    if isinstance(role_entry, dict):
        role_name = role_entry.get("role")
        if isinstance(role_name, str) and role_name.strip():
            return role_name

    raise CatalogError(f"{playbook_path} contains an invalid role entry")


def read_playbook_role_tags(
    role_entry: dict[str, Any], playbook_path: Path
) -> list[str]:
    """Normalize a playbook role tag list."""
    value = role_entry.get("tags")
    role_name = role_entry.get("role", "<unknown>")
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise CatalogError(
        f"{playbook_path} role '{role_name}' field 'tags' must be a string or list of strings"
    )


def playbook_includes_role(source_playbook: str, role_name: str) -> bool:
    """Return whether the playbook references a specific role."""
    playbook_path = Path(source_playbook)
    with playbook_path.open(encoding="utf-8") as file:
        playbook_data = yaml.safe_load(file)

    if not isinstance(playbook_data, list):
        raise CatalogError(f"{playbook_path} must contain a YAML list of plays")

    for play in playbook_data:
        if not isinstance(play, dict):
            raise CatalogError(f"{playbook_path} contains an invalid play definition")

        roles = play.get("roles", [])
        if roles is None:
            continue
        if not isinstance(roles, list):
            raise CatalogError(f"{playbook_path} field 'roles' must be a list")

        for role_entry in roles:
            if read_playbook_role_name(role_entry, playbook_path) == role_name:
                return True

    return False


def prompt_bool(message: str, *, default: bool) -> bool:
    """Prompt for a yes/no decision and return the selected value."""
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            response = input(f"{message} [{hint}]: ").strip().lower()
        except EOFError:
            return default
        except KeyboardInterrupt as error:
            print()
            raise SystemExit(130) from error

        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False

        print("Please answer 'y' or 'n'.")


def render_context7_method_label(method: str) -> str:
    """Return a user-facing label for a Context7 connection mode."""
    if method == "remote":
        return "Remote service"
    return "Local MCP process"


def prompt_context7_method(tool_name: str, *, default: str) -> str:
    """Prompt for a user-friendly Context7 connection mode."""
    options = [
        (
            "1",
            "remote",
            "Remote service",
            "Connect to the hosted Context7 MCP endpoint.",
        ),
        (
            "2",
            "local",
            "Local MCP process",
            "Run Context7 locally through `npx` on this machine.",
        ),
    ]
    option_by_token = {token: method for token, method, _label, _description in options}
    option_by_token.update(
        {method: method for _token, method, _label, _description in options}
    )
    default_token = next(
        token for token, method, _label, _description in options if method == default
    )

    print(f"\n{tool_name} Context7 connection:")
    for token, method, label, description in options:
        suffix = " (Recommended)" if method == default else ""
        print(f"  {token}) {label}{suffix}")
        print(f"     {description}")

    while True:
        try:
            response = input(f"Choose 1 or 2 [{default_token}]: ").strip().lower()
        except EOFError:
            return default
        except KeyboardInterrupt as error:
            print()
            raise SystemExit(130) from error

        if not response:
            return default

        selected = option_by_token.get(response)
        if selected is not None:
            return selected

        print("Please choose 1/2, or type 'remote'/'local'.")


def build_ai_tools_setup_summary(
    options: AiToolsInstallOptions,
    *,
    context7_api_key_present: bool,
) -> list[str]:
    """Build a short setup summary for the interactive AI tools wizard."""
    lines = [
        "",
        "AI Tools Setup Summary",
        f"- Claude Code: {'enabled' if options.manage_claude_code else 'disabled'}",
        f"- Codex CLI: {'enabled' if options.manage_codex else 'disabled'}",
        f"- Context7: {'enabled' if options.enable_context7 else 'disabled'}",
    ]
    if options.enable_context7:
        if options.manage_claude_code:
            lines.append(
                "- Claude Code Context7: "
                f"{render_context7_method_label(options.claude_context7_method)}"
            )
        if options.manage_codex:
            lines.append(
                "- Codex CLI Context7: "
                f"{render_context7_method_label(options.codex_context7_method)}"
            )
        if not context7_api_key_present:
            lines.append("- Context7 API key: not set; envmgr will continue without it")
    return lines


def run_ai_tools_setup_wizard(
    *,
    default_manage_claude_code: bool,
    default_manage_codex: bool,
    manage_claude_code: bool | None,
    manage_codex: bool | None,
    enable_context7: bool | None,
    claude_context7_method: str | None,
    codex_context7_method: str | None,
    context7_api_key_present: bool,
) -> AiToolsInstallOptions:
    """Run the interactive AI tools setup wizard and return the selected options."""
    print("\nAI Tools Setup")
    print("We'll help you choose which AI tools to install on this machine.")
    print("Press Ctrl+C at any time to cancel.")

    while True:
        resolved_manage_claude_code = (
            default_manage_claude_code
            if manage_claude_code is None
            else manage_claude_code
        )
        resolved_manage_codex = (
            default_manage_codex if manage_codex is None else manage_codex
        )

        if manage_claude_code is None:
            resolved_manage_claude_code = prompt_bool(
                "Install Claude Code?",
                default=default_manage_claude_code,
            )
        if manage_codex is None:
            resolved_manage_codex = prompt_bool(
                "Install Codex CLI?",
                default=default_manage_codex,
            )

        if resolved_manage_claude_code or resolved_manage_codex:
            break

        if manage_claude_code is not None or manage_codex is not None:
            raise CatalogError(
                "AI tools selection disabled both Claude Code and Codex CLI; choose at least one tool"
            )

        print("Select at least one tool to continue.")

    resolved_enable_context7 = True if enable_context7 is None else enable_context7
    if enable_context7 is None:
        resolved_enable_context7 = prompt_bool(
            "Enable optional Context7 integration?",
            default=True,
        )

    resolved_claude_context7_method = (
        "remote" if claude_context7_method is None else claude_context7_method
    )
    resolved_codex_context7_method = (
        "remote" if codex_context7_method is None else codex_context7_method
    )

    if resolved_enable_context7:
        if resolved_manage_claude_code and claude_context7_method is None:
            resolved_claude_context7_method = prompt_context7_method(
                "Claude Code",
                default="remote",
            )
        if resolved_manage_codex and codex_context7_method is None:
            resolved_codex_context7_method = prompt_context7_method(
                "Codex CLI",
                default="remote",
            )

    options = AiToolsInstallOptions(
        manage_claude_code=resolved_manage_claude_code,
        manage_codex=resolved_manage_codex,
        enable_context7=resolved_enable_context7,
        claude_context7_method=resolved_claude_context7_method,
        codex_context7_method=resolved_codex_context7_method,
    )

    for line in build_ai_tools_setup_summary(
        options,
        context7_api_key_present=context7_api_key_present,
    ):
        print(line)

    if not prompt_bool("Install with these settings?", default=True):
        raise WizardCancelled("AI Tools Setup cancelled before installation.")

    return options


def resolve_ai_tools_install_options(
    selected_tags: list[str],
    *,
    execution_playbook_path: str,
    manage_claude_code: bool | None,
    manage_codex: bool | None,
    enable_context7: bool | None,
    claude_context7_method: str | None,
    codex_context7_method: str | None,
    interactive: bool,
) -> AiToolsInstallOptions | None:
    """Resolve AI-tools install choices from tags, flags, and interactive prompts."""
    if not playbook_includes_role(execution_playbook_path, "ai_tools"):
        return None

    requested_tags = {tag.lower() for tag in selected_tags}
    default_manage_claude_code = any(
        tag in requested_tags for tag in ("all", "ai_tools", "claude_code")
    )
    default_manage_codex = any(tag in requested_tags for tag in ("all", "codex"))

    if interactive:
        return run_ai_tools_setup_wizard(
            default_manage_claude_code=default_manage_claude_code,
            default_manage_codex=default_manage_codex,
            manage_claude_code=manage_claude_code,
            manage_codex=manage_codex,
            enable_context7=enable_context7,
            claude_context7_method=claude_context7_method,
            codex_context7_method=codex_context7_method,
            context7_api_key_present=bool(os.environ.get("CONTEXT7_API_KEY")),
        )

    resolved_manage_claude_code = (
        default_manage_claude_code if manage_claude_code is None else manage_claude_code
    )
    resolved_manage_codex = (
        default_manage_codex if manage_codex is None else manage_codex
    )

    if not (resolved_manage_claude_code or resolved_manage_codex):
        raise CatalogError(
            "AI tools selection disabled both Claude Code and Codex CLI; choose at least one tool"
        )

    resolved_enable_context7 = True if enable_context7 is None else enable_context7
    resolved_claude_context7_method = (
        "remote" if claude_context7_method is None else claude_context7_method
    )
    resolved_codex_context7_method = (
        "remote" if codex_context7_method is None else codex_context7_method
    )

    return AiToolsInstallOptions(
        manage_claude_code=resolved_manage_claude_code,
        manage_codex=resolved_manage_codex,
        enable_context7=resolved_enable_context7,
        claude_context7_method=resolved_claude_context7_method,
        codex_context7_method=resolved_codex_context7_method,
    )


def build_ai_tools_extra_vars(options: AiToolsInstallOptions) -> dict[str, Any]:
    """Build Ansible extra vars for AI-tools install-time choices."""
    return {
        "ai_tools_manage_claude_code_override": options.manage_claude_code,
        "ai_tools_manage_codex_override": options.manage_codex,
        "ai_tools_context7_enabled": options.enable_context7,
        "ai_tools_claude_context7_method": options.claude_context7_method,
        "ai_tools_codex_context7_method": options.codex_context7_method,
    }


def build_execution_playbook(
    source_playbook: str,
    selected_tags: list[str],
    roles_dir: str | Path = "roles",
) -> str:
    """Build a minimal temporary playbook for the selected tags."""
    playbook_path = Path(source_playbook)
    if not playbook_path.exists():
        raise CatalogError(f"playbook not found: {playbook_path}")

    selected_metadata = resolve_selected_role_metadata(selected_tags, roles_dir)
    selected_tag_set = set(selected_tags)
    required_playbook_roles: dict[str, str] = {}
    roles_requiring_selected_tags: set[str] = set()

    for metadata in selected_metadata.values():
        for playbook_role in metadata.playbook_roles:
            required_playbook_roles[playbook_role] = metadata.name
        if set(metadata.tags).isdisjoint(selected_tag_set):
            roles_requiring_selected_tags.add(metadata.name)

    with playbook_path.open(encoding="utf-8") as file:
        playbook_data = yaml.safe_load(file)

    if not isinstance(playbook_data, list):
        raise CatalogError(f"{playbook_path} must contain a YAML list of plays")

    generated_playbook: list[dict[str, Any]] = []
    selected_tag_list = list(dict.fromkeys(selected_tags))

    for play in playbook_data:
        if not isinstance(play, dict):
            raise CatalogError(f"{playbook_path} contains an invalid play definition")

        roles = play.get("roles", [])
        if roles is None:
            filtered_roles: list[Any] = []
        else:
            if not isinstance(roles, list):
                raise CatalogError(f"{playbook_path} field 'roles' must be a list")

            filtered_roles = []
            for role_entry in roles:
                role_name = read_playbook_role_name(role_entry, playbook_path)
                metadata_name = required_playbook_roles.get(role_name)
                if metadata_name is None:
                    continue

                if isinstance(role_entry, dict):
                    filtered_role_entry: Any = deepcopy(role_entry)
                else:
                    filtered_role_entry = role_entry

                if metadata_name in roles_requiring_selected_tags:
                    if isinstance(filtered_role_entry, str):
                        filtered_role_entry = {
                            "role": filtered_role_entry,
                            "tags": selected_tag_list,
                        }
                    else:
                        existing_tags = read_playbook_role_tags(
                            filtered_role_entry, playbook_path
                        )
                        merged_tags = list(
                            dict.fromkeys(existing_tags + selected_tag_list)
                        )
                        filtered_role_entry["tags"] = merged_tags

                filtered_roles.append(filtered_role_entry)

        filtered_play = deepcopy(play)
        filtered_play["roles"] = filtered_roles
        generated_playbook.append(filtered_play)

    if not any(play.get("roles") for play in generated_playbook):
        raise CatalogError("selected tags did not resolve to any playbook roles")

    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yml",
        prefix=f".envmgr-{playbook_path.stem}-",
        dir=playbook_path.parent,
        delete=False,
    )
    try:
        with temp_file:
            yaml.safe_dump(generated_playbook, temp_file, sort_keys=False)
    except Exception:
        Path(temp_file.name).unlink(missing_ok=True)
        raise

    return temp_file.name


def resolve_install_playbook(
    selected_tags: list[str],
    *,
    explicit_playbook: str | None,
) -> str:
    """Resolve a playbook for install operations based on explicit input or tag scope."""
    if explicit_playbook:
        return explicit_playbook

    if not selected_tags:
        raise CatalogError("no tags selected")

    if selected_tags[0].lower() == "all":
        raise CatalogError("tag 'all' requires --playbook so the scenario is explicit")

    playbook_paths = get_existing_default_playbooks()
    if not playbook_paths:
        raise CatalogError("no scenario playbooks found under playbooks/")

    playbook_tag_index = build_playbook_tag_index(playbook_paths)
    requested_tags = set(selected_tags)
    matching_playbooks = [
        playbook
        for playbook, playbook_tags in playbook_tag_index.items()
        if requested_tags.issubset(playbook_tags)
    ]

    if len(matching_playbooks) == 1:
        return matching_playbooks[0]

    if not matching_playbooks:
        raise CatalogError(
            "selected tags do not map to a scenario playbook; use --playbook explicitly"
        )

    matching_names = ", ".join(matching_playbooks)
    raise CatalogError(
        f"selected tags are valid in multiple playbooks ({matching_names}); use --playbook explicitly"
    )


def install() -> None:
    """
    Install and configure the envmgr project using Ansible.
    """
    parser = argparse.ArgumentParser(
        description="Install and Configure envmgr with ansible"
    )

    # Define the positional argument for tags
    parser.add_argument(
        "tags",
        nargs="*",
        help="List of tags: tag1 tag2 ...",
    )

    # Add an optional argument to list tags
    parser.add_argument(
        "-l", "--list-tags", action="store_true", help="List all available tags"
    )
    parser.add_argument(
        "--playbook",
        help="Specify a playbook file explicitly when tags are ambiguous",
    )

    # Add inventory option
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )

    # Add vault password option
    parser.add_argument(
        "--ask-vault-pass", action="store_true", help="Ask for vault password"
    )
    parser.add_argument(
        "--claude-code",
        dest="ai_tools_manage_claude_code",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, explicitly install Claude Code",
    )
    parser.add_argument(
        "--no-claude-code",
        dest="ai_tools_manage_claude_code",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip Claude Code",
    )
    parser.add_argument(
        "--codex",
        dest="ai_tools_manage_codex",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, explicitly install Codex CLI",
    )
    parser.add_argument(
        "--no-codex",
        dest="ai_tools_manage_codex",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip Codex CLI",
    )
    parser.add_argument(
        "--context7",
        dest="ai_tools_context7",
        action="store_const",
        const=True,
        default=None,
        help="When AI tools are selected, enable Context7 integration",
    )
    parser.add_argument(
        "--no-context7",
        dest="ai_tools_context7",
        action="store_const",
        const=False,
        help="When AI tools are selected, skip Context7 integration",
    )
    parser.add_argument(
        "--claude-context7-method",
        choices=AI_TOOLS_CONTEXT7_METHODS,
        help="Choose the Context7 transport for Claude Code",
    )
    parser.add_argument(
        "--codex-context7-method",
        choices=AI_TOOLS_CONTEXT7_METHODS,
        help="Choose the Context7 transport for Codex CLI",
    )

    args = parser.parse_args()

    if args.list_tags:
        role_tags, task_tags = load_available_tags()
        print("Envmgr available tags:")
        print("\nRole level tags:")
        for tag in role_tags:
            print(f"  - {tag}")
        print("\nTask level tags:")
        for tag in task_tags:
            print(f"  - {tag}")
        return

    if not args.tags:
        parser.print_help()
        return

    require_setup_completed("install")

    role_tags, task_tags = load_available_tags()
    runtime_paths = ensure_runtime_layout()
    runtime_config: RuntimeConfig | None = None

    def require_runtime_config() -> RuntimeConfig:
        nonlocal runtime_config
        if runtime_config is None:
            runtime_config = load_runtime_config_option()
        return runtime_config

    def load_default_ask_vault_pass() -> bool:
        if runtime_config is not None:
            return runtime_config.default_ask_vault_pass
        try:
            return load_runtime_config().default_ask_vault_pass
        except ConfigError:
            return False

    selected_tags: list[str] = list(args.tags)
    if not selected_tags:
        print(f"{Colors.RED}Warning: No tags selected for execution{Colors.RESET}")
        return

    selected_tag_set: set[str] = set(selected_tags)

    # Check if tags exist
    all_tags: set[str] = set(role_tags + task_tags)
    invalid_tags = selected_tag_set - {"all"} - all_tags
    if invalid_tags:
        print(
            f"{Colors.RED}Warning: Unknown tags: {', '.join(invalid_tags)}{Colors.RESET}"
        )
        print("Use -l or --list-tags to see all available tags")
        return

    try:
        yaml_file_path = resolve_install_playbook(
            selected_tags,
            explicit_playbook=(
                args.playbook
                or (
                    resolve_default_playbook_path(require_runtime_config())
                    if selected_tags[0].lower() == "all"
                    else None
                )
            ),
        )
    except CatalogError as error:
        print(f"{Colors.RED}Warning: {error}{Colors.RESET}")
        return

    if not Path(yaml_file_path).exists():
        print(
            f"{Colors.RED}Warning: Playbook not found: {yaml_file_path}{Colors.RESET}"
        )
        return

    inventory_path, inventory_label = resolve_inventory_option(args.inventory)
    execution_playbook_path = yaml_file_path
    if selected_tags[0].lower() != "all":
        try:
            execution_playbook_path = build_execution_playbook(
                yaml_file_path,
                selected_tags,
            )
        except CatalogError as error:
            print(f"{Colors.RED}Warning: {error}{Colors.RESET}")
            return

    interactive_ai_tools = sys.stdin.isatty() and sys.stdout.isatty()
    ai_tools_flags_provided = any(
        value is not None
        for value in (
            args.ai_tools_manage_claude_code,
            args.ai_tools_manage_codex,
            args.ai_tools_context7,
            args.claude_context7_method,
            args.codex_context7_method,
        )
    )
    use_ai_tools_wizard = interactive_ai_tools and not ai_tools_flags_provided
    try:
        ai_tools_options = resolve_ai_tools_install_options(
            selected_tags,
            execution_playbook_path=execution_playbook_path,
            manage_claude_code=args.ai_tools_manage_claude_code,
            manage_codex=args.ai_tools_manage_codex,
            enable_context7=args.ai_tools_context7,
            claude_context7_method=args.claude_context7_method,
            codex_context7_method=args.codex_context7_method,
            interactive=use_ai_tools_wizard,
        )
    except WizardCancelled as error:
        print(error)
        if execution_playbook_path != yaml_file_path:
            Path(execution_playbook_path).unlink(missing_ok=True)
        return
    except CatalogError as error:
        print(f"{Colors.RED}Warning: {error}{Colors.RESET}")
        if execution_playbook_path != yaml_file_path:
            Path(execution_playbook_path).unlink(missing_ok=True)
        return
    if ai_tools_options is None and ai_tools_flags_provided:
        print(
            f"{Colors.RED}Warning: AI-tools flags were ignored because this run does not include the ai_tools role{Colors.RESET}"
        )

    # Display execution info
    print("\nRunning Ansible playbook with:")
    print(f"  Playbook: {yaml_file_path}")
    if execution_playbook_path != yaml_file_path:
        print(f"  Execution playbook: {execution_playbook_path}")
    print(f"  Inventory: {inventory_label} -> {inventory_path}")
    if selected_tags[0].lower() == "all":
        print(f"{Colors.GREEN}  All tags will be executed{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}  Tags:", end=" ")
        for tag in selected_tags:
            if tag in role_tags:
                print(f"[Role: {tag}]", end=" ")
            elif tag in task_tags:
                print(f"[Task: {tag}]", end=" ")
        print(f"{Colors.RESET}")
    if ai_tools_options is not None:
        context7_status = "enabled" if ai_tools_options.enable_context7 else "disabled"
        print(
            f"  AI tools: Claude Code={ai_tools_options.manage_claude_code}, "
            f"Codex CLI={ai_tools_options.manage_codex}, Context7={context7_status}"
        )
        if ai_tools_options.enable_context7:
            if ai_tools_options.manage_claude_code:
                print(
                    "  Claude Code Context7 method: "
                    f"{ai_tools_options.claude_context7_method}"
                )
            if ai_tools_options.manage_codex:
                print(
                    f"  Codex Context7 method: {ai_tools_options.codex_context7_method}"
                )
            if not os.environ.get("CONTEXT7_API_KEY"):
                print("  Context7 API key: not set (continuing without it)")
    print()

    play: list[str] = [
        "ansible-playbook",
        "-i",
        str(inventory_path),
        execution_playbook_path,
    ]
    if selected_tags[0].lower() == "all":
        command = play
    else:
        tags_str = ",".join(selected_tags)
        command = play + ["-t", tags_str]

    # Add vault password option if specified
    default_ask_vault_pass = (
        load_default_ask_vault_pass() if not args.ask_vault_pass else False
    )
    if args.ask_vault_pass or default_ask_vault_pass:
        command.append("--ask-vault-pass")

    env = build_ansible_runtime_env(runtime_paths)
    if ai_tools_options is not None:
        command.extend(
            ["--extra-vars", json.dumps(build_ai_tools_extra_vars(ai_tools_options))]
        )

    # Use Popen for real-time output
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        # Read and print output line by line
        if process.stdout is not None:
            for line in process.stdout:
                print(line, end="")
            process.stdout.close()
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
    finally:
        if execution_playbook_path != yaml_file_path:
            Path(execution_playbook_path).unlink(missing_ok=True)


def create() -> None:
    """
    Create a new Ansible role by prompting the user for a role name and generating the role directory.
    """
    parser = argparse.ArgumentParser(
        description="Create a new Ansible role by prompting the user for a role name and generating the role directory."
    )
    parser.add_argument("role", nargs="?", help="The name of the role to create")

    args = parser.parse_args()

    if args.role:
        try:
            generate_role(args.role)
            print(f"Role '{args.role}' generated successfully.")
            print(
                f"Update roles/{args.role}/meta/envmgr.yml and add the role to the appropriate playbook."
            )
        except FileExistsError:
            print(f"Role '{args.role}' already exists.")
        except (FileNotFoundError, ScaffoldError) as error:
            print(f"{Colors.RED}{error}{Colors.RESET}")
    else:
        parser.print_help()


def ping() -> None:
    """
    Test connection to all hosts using ansible ping module.
    """
    parser = argparse.ArgumentParser(
        description="Test connection to all hosts using ansible ping module"
    )

    # Add inventory option
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )

    args = parser.parse_args()

    require_setup_completed("ping")

    inventory_path, inventory_label = resolve_inventory_option(args.inventory)
    command: list[str] = ["ansible", "-i", str(inventory_path), "-m", "ping", "all"]

    env = build_ansible_runtime_env(ensure_runtime_layout())

    print(f"Testing connection with inventory: {inventory_label} -> {inventory_path}")

    try:
        subprocess.run(command, env=env, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Ping failed with exit code {e.returncode}")
    except FileNotFoundError:
        print("Error: ansible command not found. Please ensure ansible is installed.")


def setup() -> None:
    """
    Setup the envmgr project by syncing dependencies, initializing ~/.envmgr, and installing ansible content.
    """
    print("Setting up envmgr...")

    # Step 1: Sync dependencies with uv
    print("1. Syncing dependencies with uv...")
    try:
        subprocess.run(["uv", "sync"], check=True)
        print("✓ Dependencies synced successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to sync dependencies: {e}")
        return
    except FileNotFoundError:
        print("✗ Error: uv command not found. Please ensure uv is installed.")
        return

    # Step 2: Initialize the user-level envmgr runtime directory
    print("2. Initializing ~/.envmgr...")
    try:
        runtime_paths = ensure_runtime_layout()
        print(f"✓ Runtime config initialized at {runtime_paths.config_file}")
        print(f"  - Ansible log: {runtime_paths.ansible_log_file}")
        print(f"  - Galaxy roles cache: {runtime_paths.galaxy_roles_dir}")
        print(f"  - Galaxy collections cache: {runtime_paths.galaxy_collections_dir}")
    except ConfigError as error:
        print(f"✗ Failed to initialize ~/.envmgr: {error}")
        return
    except OSError as error:
        print(f"✗ Failed to initialize ~/.envmgr: {error}")
        return

    # Step 3: Install ansible roles and collections
    print("3. Installing ansible roles and collections...")
    env = build_ansible_runtime_env(runtime_paths)
    try:
        subprocess.run(
            [
                "ansible-galaxy",
                "role",
                "install",
                "-p",
                str(runtime_paths.galaxy_roles_dir),
                "-r",
                "requirements.yaml",
            ],
            check=True,
            env=env,
        )
        subprocess.run(
            [
                "ansible-galaxy",
                "collection",
                "install",
                "-p",
                str(runtime_paths.galaxy_collections_dir),
                "-r",
                "requirements.yaml",
            ],
            check=True,
            env=env,
        )
        mark_runtime_setup_complete(runtime_paths)
        print("✓ Ansible roles and collections installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install ansible roles or collections: {e}")
        return
    except FileNotFoundError:
        print(
            "✗ Error: ansible-galaxy command not found. Please ensure ansible is installed."
        )
        return

    print("🎉 Setup completed successfully!")


def lint() -> None:
    """
    Run ruff linting and formatting on Python code.
    """
    print("Running Python code linting with ruff...")

    # Run ruff check
    check_command: list[str] = ["ruff", "check", "scripts/"]
    print("1. Running ruff check...")

    try:
        subprocess.run(check_command, check=True)
        print("✓ Ruff check passed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Ruff check failed with exit code {e.returncode}")
        return
    except FileNotFoundError:
        print("Error: ruff command not found. Please ensure ruff is installed.")
        return

    # Run ruff format check
    format_command: list[str] = ["ruff", "format", "--check", "scripts/"]
    print("2. Running ruff format check...")

    try:
        subprocess.run(format_command, check=True)
        print("✓ Ruff format check passed")
    except subprocess.CalledProcessError:
        print("✗ Code formatting issues found. Run 'ruff format scripts/' to fix.")
        return
    except FileNotFoundError:
        print("Error: ruff command not found. Please ensure ruff is installed.")
        return

    print("🎉 All Python linting checks passed!")


def ansible_lint() -> None:
    """
    Run ansible-lint on the roles directory.
    """
    command: list[str] = ["ansible-lint", "./roles"]

    print("Running Ansible linting...")

    try:
        subprocess.run(command, check=True)
        print("✓ Ansible lint passed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Ansible linting failed with exit code {e.returncode}")
    except FileNotFoundError:
        print(
            "Error: ansible-lint command not found. Please ensure ansible-lint is installed."
        )


def typecheck() -> None:
    """
    Run mypy type checking on the scripts directory.
    """
    command: list[str] = ["mypy", "scripts/"]

    print("Running type checking with mypy...")

    try:
        subprocess.run(command, check=True)
        print("✓ Type checking passed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Type checking failed with exit code {e.returncode}")
    except FileNotFoundError:
        print("Error: mypy command not found. Please ensure mypy is installed.")


def validate() -> None:
    """
    Run the project validation suite in one command.
    """
    parser = argparse.ArgumentParser(
        description="Run lint, typecheck, ansible lint, and playbook syntax checks"
    )
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        help="Specify a playbook file to syntax-check (can be used multiple times)",
    )

    args = parser.parse_args()

    require_setup_completed("validate")

    playbooks = args.playbook or [
        playbook
        for playbook in ["playbooks/workstation.yml", "playbooks/node.yml"]
        if Path(playbook).exists()
    ]
    inventory_path, _inventory_label = resolve_inventory_option(args.inventory)

    env = build_ansible_runtime_env(ensure_runtime_layout())

    print("Running project validation...")

    results = [
        run_command_step("ruff check", ["ruff", "check", "scripts/"]),
        run_command_step("ruff format", ["ruff", "format", "--check", "scripts/"]),
        run_command_step("mypy", ["mypy", "scripts/"]),
        run_command_step("ansible-lint", ["ansible-lint", "./roles"]),
    ]

    if not playbooks:
        print("No playbooks selected for syntax checks.")

    for playbook in playbooks:
        if not Path(playbook).exists():
            print(f"✗ syntax-check failed because playbook was not found: {playbook}")
            results.append(False)
            continue
        results.append(
            run_command_step(
                f"syntax-check {playbook}",
                [
                    "ansible-playbook",
                    "-i",
                    str(inventory_path),
                    playbook,
                    "--syntax-check",
                ],
                env=env,
            )
        )

    if all(results):
        print("\n✓ Validation passed")
        return

    print("\n✗ Validation failed")
    raise SystemExit(1)


def smoke_test() -> None:
    """Run lightweight integration checks without installing software."""

    def check_metadata_catalog() -> None:
        role_tags, task_tags = get_available_tags("roles")

        if "init" not in role_tags:
            raise AssertionError("expected role tag 'init' to be present")
        if "git" not in task_tags:
            raise AssertionError("expected task tag 'git' to be present")

    def check_scaffold_generation() -> None:
        required_files = [
            Path("README.md"),
            Path("defaults/main.yml"),
            Path("vars/main.yml"),
            Path("meta/main.yml"),
            Path("meta/envmgr.yml"),
            Path("tasks/main.yml"),
            Path("tasks/smoke-role.yml"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            role_path = generate_role(
                "smoke-role",
                roles_dir=temp_path / "roles",
                scaffold_dir="scaffolds/role",
            )

            for relative_path in required_files:
                generated_path = role_path / relative_path
                if not generated_path.exists():
                    raise AssertionError(f"missing scaffold output: {generated_path}")

                content = generated_path.read_text(encoding="utf-8")
                if "{{ role_name }}" in content or "{{ role_title }}" in content:
                    raise AssertionError(
                        f"unrendered template placeholder found in {generated_path}"
                    )

            metadata_contents = (role_path / "meta" / "envmgr.yml").read_text(
                encoding="utf-8"
            )
            if "name: smoke-role" not in metadata_contents:
                raise AssertionError("generated metadata did not render role name")

    def check_playbook_resolution() -> None:
        if resolve_install_playbook(["zsh"], explicit_playbook=None) != (
            "playbooks/workstation.yml"
        ):
            raise AssertionError("expected zsh to resolve to workstation playbook")

        if resolve_install_playbook(["kubeadm"], explicit_playbook=None) != (
            "playbooks/node.yml"
        ):
            raise AssertionError("expected kubeadm to resolve to node playbook")

        try:
            resolve_install_playbook(["docker"], explicit_playbook=None)
        except CatalogError:
            return

        raise AssertionError("expected docker to require an explicit playbook")

    def check_execution_playbook_generation() -> None:
        generated_ai_tools_playbook = build_execution_playbook(
            "playbooks/workstation.yml",
            ["ai_tools"],
        )
        generated_codex_playbook = build_execution_playbook(
            "playbooks/workstation.yml",
            ["codex"],
        )

        try:
            with Path(generated_ai_tools_playbook).open(encoding="utf-8") as file:
                ai_tools_data = yaml.safe_load(file)
            with Path(generated_codex_playbook).open(encoding="utf-8") as file:
                codex_data = yaml.safe_load(file)

            if not isinstance(ai_tools_data, list) or not ai_tools_data:
                raise AssertionError(
                    "expected generated ai_tools playbook to contain a play"
                )
            if not isinstance(codex_data, list) or not codex_data:
                raise AssertionError(
                    "expected generated codex playbook to contain a play"
                )

            ai_tools_roles = ai_tools_data[0].get("roles", [])
            codex_roles = codex_data[0].get("roles", [])
            if not isinstance(ai_tools_roles, list) or not isinstance(
                codex_roles, list
            ):
                raise AssertionError("expected generated playbook roles to be a list")

            ai_tools_role_names = [
                read_playbook_role_name(role_entry, Path(generated_ai_tools_playbook))
                for role_entry in ai_tools_roles
            ]
            codex_role_names = [
                read_playbook_role_name(role_entry, Path(generated_codex_playbook))
                for role_entry in codex_roles
            ]

            if ai_tools_role_names != ["node", "ai_tools"]:
                raise AssertionError(
                    f"expected ai_tools execution roles to be ['node', 'ai_tools'], got {ai_tools_role_names}"
                )
            if "gantsign.oh-my-zsh" in ai_tools_role_names:
                raise AssertionError(
                    "expected ai_tools execution playbook to exclude oh-my-zsh"
                )

            if codex_role_names != ["node", "ai_tools"]:
                raise AssertionError(
                    f"expected codex execution roles to be ['node', 'ai_tools'], got {codex_role_names}"
                )

            node_entry = ai_tools_roles[0]
            if not isinstance(node_entry, dict):
                raise AssertionError("expected dependency role entry to include tags")
            if "ai_tools" not in read_playbook_role_tags(
                node_entry,
                Path(generated_ai_tools_playbook),
            ):
                raise AssertionError(
                    "expected node dependency role to inherit the ai_tools tag"
                )

            codex_ai_tools_entry = codex_roles[1]
            if not isinstance(codex_ai_tools_entry, dict):
                raise AssertionError("expected codex role entry to include tags")
            if "codex" not in read_playbook_role_tags(
                codex_ai_tools_entry,
                Path(generated_codex_playbook),
            ):
                raise AssertionError(
                    "expected ai_tools role to inherit the codex tag for task-level runs"
                )
        finally:
            Path(generated_ai_tools_playbook).unlink(missing_ok=True)
            Path(generated_codex_playbook).unlink(missing_ok=True)

    def check_runtime_config_bootstrap() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            config = load_runtime_config(envmgr_home)

            if config.default_inventory != "default":
                raise AssertionError("expected default inventory alias to be 'default'")

            if config.default_playbook != "workstation":
                raise AssertionError("expected default playbook to be 'workstation'")

            default_inventory_path = config.inventories.get("default")
            if default_inventory_path is None or not default_inventory_path.exists():
                raise AssertionError("expected bootstrap default inventory to exist")

            if not config.paths.config_file.exists():
                raise AssertionError("expected bootstrap config.toml to exist")

    def check_setup_marker_is_written_after_setup() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")

            if is_runtime_setup_complete(runtime_paths):
                raise AssertionError(
                    "expected setup marker to be absent before setup completes"
                )

            (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
            (runtime_paths.galaxy_collections_dir / "community").mkdir()
            mark_runtime_setup_complete(runtime_paths)

            if not is_runtime_setup_complete(runtime_paths):
                raise AssertionError(
                    "expected setup marker to mark the runtime as bootstrapped"
                )
            marker_contents = runtime_paths.setup_marker_file.read_text(
                encoding="utf-8"
            )
            if f"schema_version = {SETUP_SCHEMA_VERSION}" not in marker_contents:
                raise AssertionError(
                    "expected setup marker to persist the setup schema version"
                )
            if 'completed_at = "' not in marker_contents:
                raise AssertionError(
                    "expected setup marker to persist the completion timestamp"
                )

    def check_unbootstrapped_runtime_surfaces_setup_guidance() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            ensure_runtime_layout(envmgr_home)
            captured_output = io.StringIO()

            with patch("sys.stdout", new=captured_output):
                try:
                    require_setup_completed("ping", envmgr_home=envmgr_home)
                except SystemExit as error:
                    if error.code != 1:
                        raise AssertionError(
                            "expected unbootstrapped runtime to exit with code 1"
                        ) from error
                else:
                    raise AssertionError(
                        "expected unbootstrapped runtime to require uv run setup"
                    )

            if "`uv run setup`" not in captured_output.getvalue():
                raise AssertionError(
                    "expected setup guidance to mention `uv run setup`"
                )

    def check_outdated_setup_stamp_requires_setup() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
            (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
            (runtime_paths.galaxy_collections_dir / "community").mkdir()
            runtime_paths.setup_marker_file.write_text(
                'schema_version = 0\ncompleted_at = "2026-04-15T00:00:00Z"\n',
                encoding="utf-8",
            )

            if is_runtime_setup_complete(runtime_paths):
                raise AssertionError(
                    "expected outdated setup schema versions to require re-running setup"
                )

    def check_ai_tools_install_option_resolution() -> None:
        options = resolve_ai_tools_install_options(
            ["ai_tools"],
            execution_playbook_path="playbooks/workstation.yml",
            manage_claude_code=None,
            manage_codex=True,
            enable_context7=False,
            claude_context7_method=None,
            codex_context7_method="remote",
            interactive=False,
        )

        if options is None:
            raise AssertionError("expected workstation AI tools playbook to resolve")
        if not options.manage_claude_code:
            raise AssertionError("expected ai_tools tag to keep Claude Code enabled")
        if not options.manage_codex:
            raise AssertionError("expected explicit Codex selection to be honored")
        if options.enable_context7:
            raise AssertionError("expected explicit Context7 disable to be honored")
        if options.codex_context7_method != "remote":
            raise AssertionError(
                "expected Codex Context7 method override to be honored"
            )

        node_options = resolve_ai_tools_install_options(
            ["all"],
            execution_playbook_path="playbooks/node.yml",
            manage_claude_code=None,
            manage_codex=None,
            enable_context7=None,
            claude_context7_method=None,
            codex_context7_method=None,
            interactive=False,
        )
        if node_options is not None:
            raise AssertionError("expected node playbook to skip AI tools resolution")

    def check_ai_tools_setup_wizard_flow() -> None:
        with patch(
            "builtins.input",
            side_effect=["", "y", "", "1", "1", ""],
        ):
            options = resolve_ai_tools_install_options(
                ["ai_tools"],
                execution_playbook_path="playbooks/workstation.yml",
                manage_claude_code=None,
                manage_codex=None,
                enable_context7=None,
                claude_context7_method=None,
                codex_context7_method=None,
                interactive=True,
            )

        if options is None:
            raise AssertionError("expected AI tools wizard to return options")
        if not options.manage_claude_code:
            raise AssertionError("expected wizard to keep Claude Code enabled")
        if not options.manage_codex:
            raise AssertionError("expected wizard to allow enabling Codex CLI")
        if not options.enable_context7:
            raise AssertionError("expected wizard to keep Context7 enabled")
        if options.claude_context7_method != "remote":
            raise AssertionError("expected wizard to select remote for Claude Code")
        if options.codex_context7_method != "remote":
            raise AssertionError("expected wizard to select remote for Codex CLI")

    def check_unknown_inventory_alias_is_rejected() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            ensure_runtime_layout(envmgr_home)

            try:
                resolve_inventory_reference(
                    "inventory/default.yaml",
                    envmgr_home=envmgr_home,
                )
            except ConfigError as error:
                message = str(error)
                if (
                    "inventory alias 'inventory/default.yaml' is not defined"
                    not in message
                ):
                    raise AssertionError(
                        "expected unknown inventory inputs to be rejected as aliases"
                    ) from error
                return

            raise AssertionError(
                "expected unknown inventory aliases to raise ConfigError"
            )

    def check_runtime_env_uses_runtime_paths_only() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
            original_roles_path = os.environ.get("ANSIBLE_ROLES_PATH")
            original_collections_path = os.environ.get("ANSIBLE_COLLECTIONS_PATH")
            os.environ["ANSIBLE_ROLES_PATH"] = str(
                Path(temp_dir) / "legacy-roles" / ".ansible" / "roles"
            )
            os.environ["ANSIBLE_COLLECTIONS_PATH"] = str(
                Path(temp_dir) / "legacy-collections" / ".ansible" / "collections"
            )
            try:
                env = build_ansible_runtime_env(runtime_paths)
            finally:
                if original_roles_path is not None:
                    os.environ["ANSIBLE_ROLES_PATH"] = original_roles_path
                else:
                    os.environ.pop("ANSIBLE_ROLES_PATH", None)
                if original_collections_path is not None:
                    os.environ["ANSIBLE_COLLECTIONS_PATH"] = original_collections_path
                else:
                    os.environ.pop("ANSIBLE_COLLECTIONS_PATH", None)

            if ".ansible/roles" in env["ANSIBLE_ROLES_PATH"]:
                raise AssertionError(
                    "expected runtime roles path to exclude .ansible/roles"
                )
            if ".ansible/collections" in env["ANSIBLE_COLLECTIONS_PATH"]:
                raise AssertionError(
                    "expected runtime collections path to exclude .ansible/collections"
                )
            if env["ANSIBLE_LOG_PATH"] != str(runtime_paths.ansible_log_file):
                raise AssertionError("expected ansible log path to point to ~/.envmgr")

    def check_inventory_aliases_stay_under_runtime_inventory_dir() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            runtime_paths.config_file.write_text(
                """
[default]
inventory = "default"

[inventory]
default = "../outside/default.yaml"
""".lstrip(),
                encoding="utf-8",
            )

            try:
                load_runtime_config(envmgr_home)
            except ConfigError as error:
                if "must stay under" not in str(error):
                    raise AssertionError(
                        "expected inventory aliases outside ~/.envmgr/inventory to fail"
                    ) from error
                return

            raise AssertionError("expected out-of-tree inventory aliases to fail")

    def check_invalid_toml_surfaces_config_error() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            runtime_paths.config_file.write_text(
                '[default]\ninventory = "default"\ninvalid = [\n',
                encoding="utf-8",
            )

            try:
                load_runtime_config(envmgr_home)
            except ConfigError as error:
                if "contains invalid TOML" not in str(error):
                    raise AssertionError(
                        "expected invalid TOML errors to be wrapped in ConfigError"
                    ) from error
                return

            raise AssertionError("expected invalid TOML to raise ConfigError")

    def check_missing_runtime_inventory_file_is_recreated() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            envmgr_home = Path(temp_dir) / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            runtime_paths.default_inventory_file.unlink()

            resolved_path, resolved_label = resolve_inventory_reference(
                None, envmgr_home=envmgr_home
            )
            if resolved_label != "default":
                raise AssertionError(
                    "expected recreated runtime inventory to keep alias"
                )
            if resolved_path != runtime_paths.default_inventory_file.resolve():
                raise AssertionError(
                    "expected recreated runtime inventory path to match ~/.envmgr"
                )
            if not runtime_paths.default_inventory_file.exists():
                raise AssertionError(
                    "expected missing runtime inventory file to be recreated"
                )

    parser = argparse.ArgumentParser(
        description="Run lightweight smoke tests for metadata, scaffolds, and playbooks"
    )
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        help="Specify a playbook file to smoke-check (can be used multiple times)",
    )

    args = parser.parse_args()

    require_setup_completed("smoke-test")

    playbooks = args.playbook or [
        playbook
        for playbook in ["playbooks/workstation.yml", "playbooks/node.yml"]
        if Path(playbook).exists()
    ]
    inventory_path, _inventory_label = resolve_inventory_option(args.inventory)

    env = build_ansible_runtime_env(ensure_runtime_layout())

    print("Running smoke tests...")

    results = [
        run_assertion_step("metadata catalog", check_metadata_catalog),
        run_assertion_step("role scaffold", check_scaffold_generation),
        run_assertion_step("playbook resolution", check_playbook_resolution),
        run_assertion_step(
            "execution playbook generation",
            check_execution_playbook_generation,
        ),
        run_assertion_step("runtime config bootstrap", check_runtime_config_bootstrap),
        run_assertion_step(
            "setup marker is written after setup",
            check_setup_marker_is_written_after_setup,
        ),
        run_assertion_step(
            "unbootstrapped runtime surfaces setup guidance",
            check_unbootstrapped_runtime_surfaces_setup_guidance,
        ),
        run_assertion_step(
            "outdated setup stamp requires setup",
            check_outdated_setup_stamp_requires_setup,
        ),
        run_assertion_step(
            "AI tools install options resolve correctly",
            check_ai_tools_install_option_resolution,
        ),
        run_assertion_step(
            "AI tools setup wizard flow",
            check_ai_tools_setup_wizard_flow,
        ),
        run_assertion_step(
            "unknown inventory aliases are rejected",
            check_unknown_inventory_alias_is_rejected,
        ),
        run_assertion_step(
            "runtime env uses ~/.envmgr paths only",
            check_runtime_env_uses_runtime_paths_only,
        ),
        run_assertion_step(
            "inventory aliases stay under ~/.envmgr/inventory",
            check_inventory_aliases_stay_under_runtime_inventory_dir,
        ),
        run_assertion_step(
            "invalid TOML surfaces config error",
            check_invalid_toml_surfaces_config_error,
        ),
        run_assertion_step(
            "missing runtime inventory file is recreated",
            check_missing_runtime_inventory_file_is_recreated,
        ),
    ]

    if not playbooks:
        print("No playbooks selected for smoke checks.")

    for playbook in playbooks:
        if not Path(playbook).exists():
            print(f"✗ list-tags failed because playbook was not found: {playbook}")
            results.append(False)
            continue
        results.append(
            run_command_step(
                f"list-tags {playbook}",
                [
                    "ansible-playbook",
                    "-i",
                    str(inventory_path),
                    playbook,
                    "--list-tags",
                ],
                env=env,
            )
        )

    if all(results):
        print("\n✓ Smoke tests passed")
        return

    print("\n✗ Smoke tests failed")
    raise SystemExit(1)
