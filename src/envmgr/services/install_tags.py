from __future__ import annotations

from ..catalog import CatalogError, get_available_tags

ALL_TAG = "all"


def load_available_tags() -> tuple[list[str], list[str]]:
    """Load role-level and task-level tags from role metadata."""
    return get_available_tags()


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
