from __future__ import annotations

from pathlib import Path

import click
from typer.main import get_command

from envmgr.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_CONTRACT_FILES = (
    "README.md",
    "AGENTS.md",
    "docs/runtime.md",
    "docs/development.md",
    "docs/release.md",
)


def _read_repo_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _assert_contains(
    *,
    file_name: str,
    text: str,
    fragments: tuple[str, ...],
) -> None:
    missing = [fragment for fragment in fragments if fragment not in text]
    if missing:
        raise AssertionError(
            f"{file_name} is missing required docs contract fragments: "
            + ", ".join(repr(fragment) for fragment in missing)
        )


def _combined_docs_text() -> str:
    return "\n".join(_read_repo_text(file_name) for file_name in DOCS_CONTRACT_FILES)


def _iter_leaf_commands(
    command: click.Command,
    *,
    prefix: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], click.Command]]:
    if not isinstance(command, click.Group):
        return [(prefix, command)]

    leaf_commands: list[tuple[tuple[str, ...], click.Command]] = []
    for name, subcommand in sorted(command.commands.items()):
        subcommand_path = (*prefix, name)
        if isinstance(subcommand, click.Group):
            leaf_commands.extend(
                _iter_leaf_commands(subcommand, prefix=subcommand_path)
            )
        else:
            leaf_commands.append((subcommand_path, subcommand))
    return leaf_commands


def _iter_option_groups(
    command: click.Command,
) -> list[tuple[str, tuple[str, ...]]]:
    option_groups: list[tuple[str, tuple[str, ...]]] = []
    for parameter in command.params:
        raw_options = (
            *getattr(parameter, "opts", ()),
            *getattr(parameter, "secondary_opts", ()),
        )
        long_options = tuple(
            option
            for option in raw_options
            if isinstance(option, str)
            and option.startswith("--")
            and option != "--help"
        )
        if long_options:
            option_groups.append((parameter.name or "option", long_options))
    return option_groups


def check_public_cli_surface_docs_contract() -> None:
    """Require public commands and options to be discoverable in docs."""
    readme = _read_repo_text("README.md")
    docs_text = _combined_docs_text()
    root_command = get_command(app)

    missing_command_docs: list[str] = []
    for command_path, _command in _iter_leaf_commands(root_command):
        invocation = "envmgr " + " ".join(command_path)
        if invocation not in readme:
            missing_command_docs.append(invocation)

    if missing_command_docs:
        raise AssertionError(
            "README.md is missing public CLI command docs: "
            + ", ".join(missing_command_docs)
        )

    missing_option_docs: list[str] = []
    command_entries = [((), root_command), *_iter_leaf_commands(root_command)]
    for command_path, command in command_entries:
        command_label = (
            "envmgr" if not command_path else "envmgr " + " ".join(command_path)
        )
        for parameter_name, option_group in _iter_option_groups(command):
            if not any(option in docs_text for option in option_group):
                missing_option_docs.append(
                    f"{command_label} {parameter_name} ({' / '.join(option_group)})"
                )

    if missing_option_docs:
        raise AssertionError(
            "public CLI options are missing from README/AGENTS/CLI checklist docs: "
            + ", ".join(missing_option_docs)
        )


def check_runtime_playbook_scenario_docs_contract() -> None:
    """Keep runtime playbook scenario semantics synchronized in user docs."""
    readme = _read_repo_text("README.md")
    agents = _read_repo_text("AGENTS.md")

    _assert_contains(
        file_name="README.md",
        text=readme,
        fragments=(
            "Built-in Scenarios",
            "`workstation`",
            "`node`",
            "Ansible playbook topology",
            "Path-like",
            "caller filesystem paths",
            "envmgr install --playbook ./custom-playbook.yml",
        ),
    )
    _assert_contains(
        file_name="AGENTS.md",
        text=agents,
        fragments=(
            "--playbook <scenario-or-path>",
            "scenario names",
            "path-like values",
            "built-in Ansible playbook topology",
        ),
    )
    _assert_contains(
        file_name="AGENTS.md",
        text=agents,
        fragments=(
            "envmgr install --help",
            "envmgr install -l",
            "`workstation`",
            "`node`",
            "path-like values",
            "caller filesystem",
        ),
    )


def check_doctor_dependency_docs_contract() -> None:
    """Keep doctor dependency and warning semantics synchronized in docs."""
    runtime_docs = _read_repo_text("docs/runtime.md")
    agents = _read_repo_text("AGENTS.md")

    _assert_contains(
        file_name="docs/runtime.md",
        text=runtime_docs,
        fragments=(
            "hard command check covers the Ansible runtime commands",
            "`ansible`",
            "`ansible-playbook`",
            "`ansible-galaxy`",
            "`uv` is checked only for",
            "self-management warning",
            "still exits",
            "0 unless another check fails",
        ),
    )
    _assert_contains(
        file_name="AGENTS.md",
        text=agents,
        fragments=(
            "For CLI UX changes, update the `Runtime CLI UX Contracts` section",
            "When playbook resolution semantics, built-in scenarios, or `--playbook` behavior changes",
            "When `envmgr doctor` dependency classification",
        ),
    )
    _assert_contains(
        file_name="AGENTS.md",
        text=agents,
        fragments=(
            "envmgr doctor` and `envmgr doctor --json` exit non-zero only for failing",
            "warning-only reports still exit `0`",
            "hard command check covers Ansible runtime commands",
            "invalid installer-recorded `uv` paths produce a self-management warning",
        ),
    )


def check_release_notes_docs_contract() -> None:
    """Keep release note automation synchronized in release docs."""
    release_docs = _read_repo_text("docs/release.md")
    agents = _read_repo_text("AGENTS.md")

    _assert_contains(
        file_name="docs/release.md",
        text=release_docs,
        fragments=(
            "`gh release create` with `--generate-notes`",
            "workflow prepends fixed install, SHA256 verification, upgrade,",
            "clean-reinstall guidance with `--notes`",
            "GitHub-generated release notes provide the changelog body",
        ),
    )
    _assert_contains(
        file_name="AGENTS.md",
        text=agents,
        fragments=(
            "`gh release create` with GitHub-generated release notes",
            "Release notes prepend fixed install, SHA256 verification, upgrade,",
            "before GitHub-generated notes",
        ),
    )
