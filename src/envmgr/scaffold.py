from __future__ import annotations

import re
from pathlib import Path


class ScaffoldError(ValueError):
    """Raised when scaffolding input or layout is invalid."""


ROLE_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ROLE_NAME_TOKEN = "__role_name__"


def validate_role_name(role_name: str) -> None:
    """Ensure role names follow the repository lower-kebab-case convention."""
    if not ROLE_NAME_PATTERN.fullmatch(role_name):
        raise ScaffoldError(
            "role name must use lower-kebab-case, e.g. 'kubernetes-tools'"
        )


def render_template(template: str, role_name: str) -> str:
    """Render scaffold placeholders into file contents."""
    replacements = {
        "{{ role_name }}": role_name,
        "{{ role_title }}": role_name.replace("-", " ").title(),
    }

    rendered = template
    for source, target in replacements.items():
        rendered = rendered.replace(source, target)
    return rendered


def render_relative_path(path: Path, role_name: str) -> Path:
    """Render scaffold placeholders into destination paths."""
    return Path(str(path).replace(ROLE_NAME_TOKEN, role_name))


def generate_role(
    role_name: str,
    *,
    roles_dir: str | Path = "roles",
    scaffold_dir: str | Path = "scaffolds/role",
) -> Path:
    """Generate a new Ansible role from the shared scaffold directory."""
    validate_role_name(role_name)

    roles_path = Path(roles_dir)
    role_path = roles_path / role_name
    template_root = Path(scaffold_dir)

    if role_path.exists():
        raise FileExistsError(f"role already exists: {role_path}")
    if not template_root.exists():
        raise FileNotFoundError(f"scaffold directory not found: {template_root}")

    role_path.mkdir(parents=True, exist_ok=False)

    for template_path in sorted(
        path for path in template_root.rglob("*") if path.is_file()
    ):
        relative_path = template_path.relative_to(template_root)
        destination_path = role_path / render_relative_path(relative_path, role_name)
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        template = template_path.read_text(encoding="utf-8")
        rendered = render_template(template, role_name)
        destination_path.write_text(rendered, encoding="utf-8")

    return role_path
