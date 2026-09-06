"""Single-source-of-truth contract checks.

Reads ``single_source_of_truth.yml`` and asserts that each concept's marker
appears only within the module that owns it across ``src/``.  A second
implementation of an owned concept surfaces as this check failing, instead of
lurking as a silent duplicate.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path(__file__).with_name("single_source_of_truth.yml")
SRC_ROOT = REPO_ROOT / "src"


def _load_registry() -> list[dict[str, str]]:
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("single-source-of-truth registry must be a YAML mapping")
    concepts = data.get("concepts")
    if not isinstance(concepts, list):
        raise AssertionError(
            "single-source-of-truth registry must define a 'concepts' list"
        )
    return concepts


def check_single_source_of_truth() -> None:
    """Assert every registered concept's marker is confined to its owner module."""
    concepts = _load_registry()
    if not concepts:
        raise AssertionError("single-source-of-truth registry is empty")

    for concept in concepts:
        name = concept.get("name")
        owner = concept.get("owner")
        marker = concept.get("marker")
        if not isinstance(name, str) or not name.strip():
            raise AssertionError(f"invalid register entry {concept!r}")
        if not isinstance(owner, str) or not owner.strip():
            raise AssertionError(f"invalid register entry {concept!r}")
        if not isinstance(marker, str) or not marker.strip():
            raise AssertionError(f"invalid register entry {concept!r}")

        owner_path = (REPO_ROOT / owner).resolve()
        if not owner_path.exists():
            raise AssertionError(
                f"concept '{name}' owner module does not exist: {owner}"
            )

        owner_sees_marker = False
        offenders: list[str] = []
        for file_path in SRC_ROOT.rglob("*.py"):
            text = file_path.read_text(encoding="utf-8")
            if marker not in text:
                continue
            if file_path.resolve() == owner_path:
                owner_sees_marker = True
                continue
            offenders.append(str(file_path.relative_to(REPO_ROOT)))

        if not owner_sees_marker:
            raise AssertionError(
                f"concept '{name}' marker {marker!r} is missing from its owner "
                f"module {owner}"
            )
        if offenders:
            raise AssertionError(
                f"concept '{name}' (marker {marker!r}) is owned by {owner} but the "
                f"marker also appears in: {', '.join(sorted(offenders))}. Deepen that "
                f"concept into {owner} instead of re-implementing it."
            )
