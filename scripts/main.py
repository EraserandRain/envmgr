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


def load_tags_from_yaml(file_path):
    role_tags = set()
    task_tags = set()

    # Load role-level tags in entry.yaml
    with open(file_path, "r") as file:
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
            with open(main_yml, "r") as file:
                try:
                    tasks = yaml.safe_load(file)
                    if tasks:
                        for task in tasks:
                            if "tags" in task:
                                task_tags.update(task["tags"])
                except yaml.YAMLError:
                    continue

    return sorted(role_tags), sorted(task_tags)


def install():
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
    selected_tags = set(args.tags)

    # Check if tags exist
    all_tags = set(role_tags + task_tags)
    invalid_tags = selected_tags - {"all"} - all_tags
    if invalid_tags:
        print(
            f"{Colors.RED}Warning: Unknown tags: {', '.join(invalid_tags)}{Colors.RESET}"
        )
        print("Use -l or --list-tags to see all available tags")
        return

    # Display execution info
    print("\nRunning Ansible playbook with:")
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

    play = ["ansible-playbook", yaml_file_path]
    if args.tags[0].lower() == "all":
        command = play
    else:
        tags_str = ",".join(args.tags)
        command = play + ["-t", tags_str]

    # Set ANSIBLE_FORCE_COLOR to force color output
    env = os.environ.copy()
    env["ANSIBLE_FORCE_COLOR"] = "true"

    # Use Popen for real-time output
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env
    )

    # Read and print output line by line
    try:
        for line in process.stdout:
            print(line, end="")
        process.stdout.close()
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
    pass


def create():
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
    pass


def generate_role(role_name):
    """
    Generate a new Ansible role by copying template files.

    Args:
        role_name (str): The name of the role to create
    """
    # Define paths
    base_path = "roles"
    template_path = os.path.join(base_path, "templates")
    role_path = os.path.join(base_path, role_name)

    # Create role directory
    create_dir(role_path)

    # Copy template files to role directory
    for root, dirs, files in os.walk(template_path):
        for file in files:
            src_file = os.path.join(root, file)
            dst_file = os.path.join(
                role_path, root.replace(template_path, "").lstrip(os.path.sep), file
            )
            create_dir(os.path.dirname(dst_file))
            shutil.copy(src_file, dst_file)
    pass


def create_dir(path):
    """
    Create a directory

    Args:
        path (str): Path to the directory
    """
    Path(path).mkdir(parents=True, exist_ok=True)
    pass
