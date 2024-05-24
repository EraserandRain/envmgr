import argparse, os, shutil, subprocess
from pathlib import Path

ENTRY_FILE = "entry.yaml"
play = ["ansible-playbook", ENTRY_FILE]


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
        help="List of tags",
    )

    args = parser.parse_args()

    if not args.tags:
        parser.print_help()
        return

    # Construct command based on tags
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

    print("Tags:", args.tags)

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
