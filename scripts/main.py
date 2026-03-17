import argparse
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .catalog import CatalogError, get_available_tags
from .scaffold import ScaffoldError, generate_role


# ANSI color codes
class Colors:
    GREEN = "\033[32m"
    RED = "\033[31m"
    RESET = "\033[0m"


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
    except (AssertionError, CatalogError, FileNotFoundError, ScaffoldError) as error:
        print(f"✗ {step_name} failed: {error}")
        return False


def load_available_tags() -> tuple[list[str], list[str]]:
    """Load role-level and task-level tags from role metadata."""
    try:
        return get_available_tags("roles")
    except CatalogError as error:
        print(f"{Colors.RED}Metadata error: {error}{Colors.RESET}")
        raise SystemExit(1) from error


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
        help="Specify a playbook file (default: entry.yaml)",
    )

    # Add inventory option
    parser.add_argument(
        "-i",
        "--inventory",
        default="inventory/default.yaml",
        help="Specify inventory file (default: inventory/default.yaml)",
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
    selected_tags: list[str] = list(args.tags)
    yaml_file_path = args.playbook or "entry.yaml"

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

    if not Path(yaml_file_path).exists():
        print(
            f"{Colors.RED}Warning: Playbook not found: {yaml_file_path}{Colors.RESET}"
        )
        return

    # Display execution info
    print("\nRunning Ansible playbook with:")
    print(f"  Playbook: {yaml_file_path}")
    print(f"  Inventory: {args.inventory}")
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

    play: list[str] = ["ansible-playbook", "-i", args.inventory, yaml_file_path]
    if selected_tags[0].lower() == "all":
        command = play
    else:
        tags_str = ",".join(selected_tags)
        command = play + ["-t", tags_str]

    # Add vault password option if specified
    if args.ask_vault_pass:
        command.append("--ask-vault-pass")

    # Set ANSIBLE_FORCE_COLOR to force color output
    env = os.environ.copy()
    env["ANSIBLE_FORCE_COLOR"] = "true"

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
        default="inventory/default.yaml",
        help="Specify inventory file (default: inventory/default.yaml)",
    )

    args = parser.parse_args()

    command: list[str] = ["ansible", "-i", args.inventory, "-m", "ping", "all"]

    # Set ANSIBLE_FORCE_COLOR to force color output
    env = os.environ.copy()
    env["ANSIBLE_FORCE_COLOR"] = "true"

    print(f"Testing connection with inventory: {args.inventory}")

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

    # Step 2: Initialize logs directory
    print("2. Initializing logs directory...")
    try:
        os.makedirs("log", exist_ok=True)
        print("✓ Logs directory initialized")
    except Exception as e:
        print(f"✗ Failed to create logs directory: {e}")
        return

    # Step 3: Install ansible roles and collections
    print("3. Installing ansible roles and collections...")
    try:
        subprocess.run(
            [
                "ansible-galaxy",
                "role",
                "install",
                "-p",
                "./.ansible/roles",
                "-r",
                "requirements.yaml",
            ],
            check=True,
        )
        subprocess.run(
            ["ansible-galaxy", "collection", "install", "-r", "requirements.yaml"],
            check=True,
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
        default="inventory/default.yaml",
        help="Specify inventory file for playbook syntax checks",
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

    env = os.environ.copy()
    env["ANSIBLE_FORCE_COLOR"] = "true"

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
                ["ansible-playbook", "-i", args.inventory, playbook, "--syntax-check"],
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

    parser = argparse.ArgumentParser(
        description="Run lightweight smoke tests for metadata, scaffolds, and playbooks"
    )
    parser.add_argument(
        "-i",
        "--inventory",
        default="inventory/default.yaml",
        help="Specify inventory file for playbook smoke checks",
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

    env = os.environ.copy()
    env["ANSIBLE_FORCE_COLOR"] = "true"

    print("Running smoke tests...")

    results = [
        run_assertion_step("metadata catalog", check_metadata_catalog),
        run_assertion_step("role scaffold", check_scaffold_generation),
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
                ["ansible-playbook", "-i", args.inventory, playbook, "--list-tags"],
                env=env,
            )
        )

    if all(results):
        print("\n✓ Smoke tests passed")
        return

    print("\n✗ Smoke tests failed")
    raise SystemExit(1)
