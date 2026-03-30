import argparse
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .catalog import CatalogError, build_playbook_tag_index, get_available_tags
from .runtime_config import (
    ConfigError,
    RuntimeConfig,
    RuntimePaths,
    ensure_runtime_layout,
    load_runtime_config,
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
    """Resolve an inventory alias from ~/.envmgr/config.toml or an explicit path."""
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
    legacy_roles_dir = str(Path(".ansible/roles").resolve())
    legacy_collections_dir = str(Path(".ansible/collections").resolve())
    env["ANSIBLE_FORCE_COLOR"] = "true"
    env["ANSIBLE_LOG_PATH"] = str(paths.ansible_log_file)
    env["ANSIBLE_ROLES_PATH"] = merge_path_entries(
        [
            str(Path("roles").resolve()),
            str(paths.galaxy_roles_dir),
            legacy_roles_dir,
            env.get("ANSIBLE_ROLES_PATH", ""),
        ]
    )
    env["ANSIBLE_COLLECTIONS_PATH"] = merge_path_entries(
        [
            str(paths.galaxy_collections_dir),
            legacy_collections_dir,
            env.get("ANSIBLE_COLLECTIONS_PATH", ""),
        ]
    )
    env["ANSIBLE_LOCAL_TEMP"] = str(paths.tmp_dir)
    return env


def get_existing_default_playbooks() -> list[str]:
    """Return default scenario playbooks that exist in the repository."""
    return [playbook for playbook in DEFAULT_PLAYBOOKS if Path(playbook).exists()]


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
        help="Specify an inventory alias from ~/.envmgr/config.toml or an explicit inventory path",
    )

    # Add vault password option
    parser.add_argument(
        "--ask-vault-pass", action="store_true", help="Ask for vault password"
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

    # Display execution info
    print("\nRunning Ansible playbook with:")
    print(f"  Playbook: {yaml_file_path}")
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
    print()

    play: list[str] = ["ansible-playbook", "-i", str(inventory_path), yaml_file_path]
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

    # Use Popen for real-time output
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env
    )

    # Read and print output line by line
    try:
        if process.stdout is not None:
            for line in process.stdout:
                print(line, end="")
            process.stdout.close()
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()


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
        help="Specify an inventory alias from ~/.envmgr/config.toml or an explicit inventory path",
    )

    args = parser.parse_args()

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
    Setup the envmgr project by syncing dependencies, initializing logs, and installing ansible roles.
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

    # Step 3: Initialize repository logs directory
    print("3. Initializing logs directory...")
    try:
        os.makedirs("log", exist_ok=True)
        print("✓ Logs directory initialized")
    except Exception as e:
        print(f"✗ Failed to create logs directory: {e}")
        return

    # Step 4: Install ansible roles and collections
    print("4. Installing ansible roles and collections...")
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
        help="Specify an inventory alias from ~/.envmgr/config.toml or an explicit inventory path",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        help="Specify a playbook file to syntax-check (can be used multiple times)",
    )

    args = parser.parse_args()

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

    def check_inventory_path_fallback_with_invalid_config() -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            envmgr_home = temp_path / ".envmgr"
            runtime_paths = ensure_runtime_layout(envmgr_home)
            runtime_paths.config_file.write_text(
                '[default]\ninventory = "default"\ninvalid = [\n',
                encoding="utf-8",
            )

            worktree = temp_path / "worktree"
            explicit_inventory = worktree / "inventory" / "default.yaml"
            explicit_inventory.parent.mkdir(parents=True, exist_ok=True)
            explicit_inventory.write_text("all:\n  hosts: {}\n", encoding="utf-8")

            resolved_path, resolved_label = resolve_inventory_reference(
                "inventory/default.yaml",
                envmgr_home=envmgr_home,
                cwd=worktree,
            )

            if resolved_path != explicit_inventory.resolve():
                raise AssertionError("expected explicit inventory path fallback to win")
            if resolved_label != str(explicit_inventory.resolve()):
                raise AssertionError("expected explicit inventory label to be the path")

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

    parser = argparse.ArgumentParser(
        description="Run lightweight smoke tests for metadata, scaffolds, and playbooks"
    )
    parser.add_argument(
        "-i",
        "--inventory",
        help="Specify an inventory alias from ~/.envmgr/config.toml or an explicit inventory path",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        help="Specify a playbook file to smoke-check (can be used multiple times)",
    )

    args = parser.parse_args()

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
        run_assertion_step("runtime config bootstrap", check_runtime_config_bootstrap),
        run_assertion_step(
            "inventory path fallback with invalid config",
            check_inventory_path_fallback_with_invalid_config,
        ),
        run_assertion_step(
            "invalid TOML surfaces config error",
            check_invalid_toml_surfaces_config_error,
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
