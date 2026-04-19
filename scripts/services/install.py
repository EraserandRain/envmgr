from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..catalog import (
    CatalogError,
    RoleMetadata,
    build_playbook_tag_index,
    get_available_tags,
    load_playbook_tags,
    load_role_catalog,
)
from ..runtime_config import (
    RuntimeConfig,
    RuntimePaths,
    ensure_runtime_layout,
    load_runtime_config,
    resolve_inventory_reference,
)

DEFAULT_PLAYBOOKS = [
    "playbooks/workstation.yml",
    "playbooks/node.yml",
]
ALL_TAG = "all"
AI_TOOLS_CONTEXT7_METHODS = ("remote", "local")


@dataclass(frozen=True)
class AiToolsInstallOptions:
    manage_claude_code: bool
    manage_codex: bool
    manage_rtk: bool
    enable_context7: bool
    claude_context7_method: str
    codex_context7_method: str


@dataclass(frozen=True)
class AiToolsInstallDefaults:
    applicable: bool
    manage_claude_code: bool
    manage_codex: bool
    manage_rtk: bool


@dataclass(frozen=True)
class InstallPlan:
    selected_tags: list[str]
    role_tags: list[str]
    task_tags: list[str]
    source_playbook_path: str
    execution_playbook_path: str
    uses_temporary_execution_playbook: bool
    inventory_path: Path
    inventory_label: str
    runtime_paths: RuntimePaths
    default_ask_vault_pass: bool
    ai_tools_defaults: AiToolsInstallDefaults


def load_available_tags() -> tuple[list[str], list[str]]:
    """Load role-level and task-level tags from role metadata."""
    return get_available_tags("roles")


def resolve_default_playbook_path(config: RuntimeConfig) -> str:
    """Resolve the configured default playbook name into a repository playbook path."""
    configured_playbook = Path(config.default_playbook)
    if configured_playbook.suffix in {".yml", ".yaml"}:
        return str(configured_playbook)
    return str(Path("playbooks") / f"{config.default_playbook}.yml")


def normalize_selected_tags(raw_tags: list[str]) -> list[str]:
    """Normalize install tags and reject ambiguous uses of the special `all` tag."""
    selected_tags = list(
        dict.fromkeys(tag.strip().lower() for tag in raw_tags if tag.strip())
    )
    if ALL_TAG in selected_tags and selected_tags != [ALL_TAG]:
        raise CatalogError(
            "tag 'all' cannot be combined with other tags; choose either 'all' or specific tags"
        )
    return selected_tags


def validate_selected_tags(
    selected_tags: list[str],
    *,
    role_tags: list[str],
    task_tags: list[str],
) -> None:
    """Validate that the selected tags exist in the role catalog."""
    all_tags = set(role_tags + task_tags)
    invalid_tags = set(selected_tags) - {ALL_TAG} - all_tags
    if invalid_tags:
        raise CatalogError(
            "unknown tags: "
            + ", ".join(sorted(invalid_tags))
            + "\nUse -l or --list-tags to see all available tags"
        )


def is_all_tag_selection(selected_tags: list[str]) -> bool:
    """Return whether the normalized selection targets the entire playbook."""
    return selected_tags == [ALL_TAG]


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


def build_ai_tools_install_defaults(
    selected_tags: list[str],
    *,
    execution_playbook_path: str,
) -> AiToolsInstallDefaults:
    """Compute default AI-tools selections for the chosen tag set."""
    if not playbook_includes_role(execution_playbook_path, "ai_tools"):
        return AiToolsInstallDefaults(
            applicable=False,
            manage_claude_code=False,
            manage_codex=False,
            manage_rtk=False,
        )

    requested_tags = {tag.lower() for tag in selected_tags}
    return AiToolsInstallDefaults(
        applicable=True,
        manage_claude_code=any(
            tag in requested_tags for tag in ("all", "ai_tools", "claude_code")
        ),
        manage_codex=any(tag in requested_tags for tag in ("all", "codex")),
        manage_rtk=any(tag in requested_tags for tag in ("all", "ai_tools", "rtk")),
    )


def resolve_noninteractive_ai_tools_install_options(
    defaults: AiToolsInstallDefaults,
    *,
    manage_claude_code: bool | None,
    manage_codex: bool | None,
    manage_rtk: bool | None,
    enable_context7: bool | None,
    claude_context7_method: str | None,
    codex_context7_method: str | None,
) -> AiToolsInstallOptions | None:
    """Resolve AI-tools install options without any interactive prompts."""
    if not defaults.applicable:
        return None

    resolved_manage_claude_code = (
        defaults.manage_claude_code
        if manage_claude_code is None
        else manage_claude_code
    )
    resolved_manage_codex = (
        defaults.manage_codex if manage_codex is None else manage_codex
    )
    resolved_manage_rtk = defaults.manage_rtk if manage_rtk is None else manage_rtk

    if not (
        resolved_manage_claude_code or resolved_manage_codex or resolved_manage_rtk
    ):
        raise CatalogError(
            "AI tools selection disabled Claude Code, Codex CLI, and RTK; choose at least one tool"
        )

    context7_applicable = resolved_manage_claude_code or resolved_manage_codex
    resolved_enable_context7 = False
    if context7_applicable:
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
        manage_rtk=resolved_manage_rtk,
        enable_context7=resolved_enable_context7,
        claude_context7_method=resolved_claude_context7_method,
        codex_context7_method=resolved_codex_context7_method,
    )


def build_ai_tools_extra_vars(options: AiToolsInstallOptions) -> dict[str, Any]:
    """Build Ansible extra vars for AI-tools install-time choices."""
    return {
        "ai_tools_manage_claude_code_override": options.manage_claude_code,
        "ai_tools_manage_codex_override": options.manage_codex,
        "ai_tools_manage_rtk_override": options.manage_rtk,
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
        if selected_tags and not is_all_tag_selection(selected_tags):
            playbook_tags = load_playbook_tags(explicit_playbook)
            requested_tags = set(selected_tags)
            if not requested_tags.issubset(playbook_tags):
                raise CatalogError(
                    f"selected tags are not valid in {explicit_playbook}; "
                    "choose a matching playbook"
                )
        return explicit_playbook

    if not selected_tags:
        raise CatalogError("no tags selected")

    if is_all_tag_selection(selected_tags):
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


def build_install_plan(
    selected_tags: list[str],
    *,
    explicit_playbook: str | None,
    inventory_reference: str | None,
    role_tags: list[str] | None = None,
    task_tags: list[str] | None = None,
    envmgr_home: str | Path | None = None,
) -> InstallPlan:
    """Build the execution plan for one `envmgr install` invocation."""
    if not selected_tags:
        raise CatalogError("no tags selected for execution")

    if role_tags is None or task_tags is None:
        resolved_role_tags, resolved_task_tags = load_available_tags()
    else:
        resolved_role_tags, resolved_task_tags = role_tags, task_tags
    validate_selected_tags(
        selected_tags,
        role_tags=resolved_role_tags,
        task_tags=resolved_task_tags,
    )

    runtime_paths = ensure_runtime_layout(envmgr_home)
    runtime_config = load_runtime_config(envmgr_home)

    resolved_explicit_playbook = explicit_playbook
    if is_all_tag_selection(selected_tags) and resolved_explicit_playbook is None:
        resolved_explicit_playbook = resolve_default_playbook_path(runtime_config)

    source_playbook_path = resolve_install_playbook(
        selected_tags,
        explicit_playbook=resolved_explicit_playbook,
    )
    if not Path(source_playbook_path).exists():
        raise CatalogError(f"playbook not found: {source_playbook_path}")

    inventory_path, inventory_label = resolve_inventory_reference(
        inventory_reference,
        envmgr_home=envmgr_home,
    )

    execution_playbook_path = source_playbook_path
    uses_temporary_execution_playbook = False
    try:
        if not is_all_tag_selection(selected_tags):
            execution_playbook_path = build_execution_playbook(
                source_playbook_path,
                selected_tags,
            )
            uses_temporary_execution_playbook = True
        ai_tools_defaults = build_ai_tools_install_defaults(
            selected_tags,
            execution_playbook_path=execution_playbook_path,
        )
    except Exception:
        if uses_temporary_execution_playbook:
            Path(execution_playbook_path).unlink(missing_ok=True)
        raise

    return InstallPlan(
        selected_tags=list(selected_tags),
        role_tags=list(resolved_role_tags),
        task_tags=list(resolved_task_tags),
        source_playbook_path=source_playbook_path,
        execution_playbook_path=execution_playbook_path,
        uses_temporary_execution_playbook=uses_temporary_execution_playbook,
        inventory_path=inventory_path,
        inventory_label=inventory_label,
        runtime_paths=runtime_paths,
        default_ask_vault_pass=runtime_config.default_ask_vault_pass,
        ai_tools_defaults=ai_tools_defaults,
    )


def build_install_command(
    install_plan: InstallPlan,
    *,
    ask_vault_pass: bool,
    ai_tools_options: AiToolsInstallOptions | None,
) -> list[str]:
    """Build the final ansible-playbook command for an install plan."""
    command = [
        "ansible-playbook",
        "-i",
        str(install_plan.inventory_path),
        install_plan.execution_playbook_path,
    ]
    if not is_all_tag_selection(install_plan.selected_tags):
        command.extend(["-t", ",".join(install_plan.selected_tags)])
    if ask_vault_pass:
        command.append("--ask-vault-pass")
    if ai_tools_options is not None:
        command.extend(
            ["--extra-vars", json.dumps(build_ai_tools_extra_vars(ai_tools_options))]
        )
    return command


def cleanup_install_plan(install_plan: InstallPlan) -> None:
    """Delete the temporary execution playbook created for a scoped install."""
    if install_plan.uses_temporary_execution_playbook:
        Path(install_plan.execution_playbook_path).unlink(missing_ok=True)
