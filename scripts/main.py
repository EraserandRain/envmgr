import argparse
import os
import shutil
import subprocess
from pathlib import Path

import yaml


# ANSI color codes
class Colors:
    GREEN = "\033[32m"
    RED = "\033[31m"
    RESET = "\033[0m"


def load_tags_from_yaml(file_path: str) -> tuple[list[str], list[str]]:
    """
    Load role-level and task-level tags from YAML files.

    Args:
        file_path: Path to the entry.yaml file

    Returns:
        Tuple of (role_tags, task_tags) as sorted lists
    """
    role_tags: set[str] = set()
    task_tags: set[str] = set()

    # Load role-level tags in entry.yaml
    with open(file_path) as file:
        data = yaml.safe_load(file)
        for item in data:
            if "roles" in item:
                for role in item["roles"]:
                    if "tags" in role:
                        role_tags.update(role["tags"])

    # Load task-level tags from each role's main.yml
    roles_dir = "roles"
    for role_name in os.listdir(roles_dir):
        main_yml = os.path.join(roles_dir, role_name, "tasks", "main.yml")
        if os.path.exists(main_yml):
            with open(main_yml) as file:
                try:
                    tasks = yaml.safe_load(file)
                    if tasks:
                        for task in tasks:
                            if "tags" in task:
                                task_tags.update(task["tags"])
                except yaml.YAMLError:
                    continue

    return sorted(role_tags), sorted(task_tags)


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

    # Define the path to the entry.yaml file
    yaml_file_path = "entry.yaml"

    if args.list_tags:
        role_tags, task_tags = load_tags_from_yaml(yaml_file_path)
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

    role_tags, task_tags = load_tags_from_yaml(yaml_file_path)
    selected_tags: set[str] = set(args.tags)

    # Check if tags exist
    all_tags: set[str] = set(role_tags + task_tags)
    invalid_tags = selected_tags - {"all"} - all_tags
    if invalid_tags:
        print(
            f"{Colors.RED}Warning: Unknown tags: {', '.join(invalid_tags)}{Colors.RESET}"
        )
        print("Use -l or --list-tags to see all available tags")
        return

    # Display execution info
    print("\nRunning Ansible playbook with:")
    print(f"  Inventory: {args.inventory}")
    if args.tags[0].lower() == "all":
        print(f"{Colors.GREEN}  All tags will be executed{Colors.RESET}")
    else:
        print(f"{Colors.GREEN}  Tags:", end=" ")
        for tag in args.tags:
            if tag in role_tags:
                print(f"[Role: {tag}]", end=" ")
            elif tag in task_tags:
                print(f"[Task: {tag}]", end=" ")
        print(f"{Colors.RESET}")
    print()

    play: list[str] = ["ansible-playbook", "-i", args.inventory, yaml_file_path]
    if args.tags[0].lower() == "all":
        command = play
    else:
        tags_str = ",".join(args.tags)
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
        if os.path.exists(os.path.join("roles", args.role)):
            print(f"Role '{args.role}' already exists.")
        else:
            generate_role(args.role)
            print(f"Role '{args.role}' generated successfully.")
    else:
        parser.print_help()


def generate_role(role_name: str) -> None:
    """
    Generate a new Ansible role by copying template files.

    Args:
        role_name: The name of the role to create
    """
    # Define paths
    base_path = "roles"
    template_path = os.path.join(base_path, "templates")
    role_path = os.path.join(base_path, role_name)

    # Create role directory
    create_dir(role_path)

    # Copy template files to role directory
    for root, _dirs, files in os.walk(template_path):
        for file in files:
            src_file = os.path.join(root, file)
            dst_file = os.path.join(
                role_path, root.replace(template_path, "").lstrip(os.path.sep), file
            )
            create_dir(os.path.dirname(dst_file))
            shutil.copy(src_file, dst_file)


def create_dir(path: str) -> None:
    """
    Create a directory

    Args:
        path: Path to the directory
    """
    Path(path).mkdir(parents=True, exist_ok=True)


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

    # Step 3: Install ansible roles
    print("3. Installing ansible roles...")
    try:
        subprocess.run(
            ["ansible-galaxy", "install", "-r", "requirements.yaml"], check=True
        )
        print("✓ Ansible roles installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install ansible roles: {e}")
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
