import os
import shutil


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
    os.makedirs(role_path, exist_ok=True)

    # Copy template files to role directory
    for root, _dirs, files in os.walk(template_path):
        for file in files:
            src_file = os.path.join(root, file)
            dst_file = os.path.join(
                role_path, root.replace(template_path, "").lstrip(os.path.sep), file
            )
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copy(src_file, dst_file)


if __name__ == "__main__":
    role_name = input("Enter role name: ")
    generate_role(role_name)
    print(f"Role '{role_name}' generated successfully.")
