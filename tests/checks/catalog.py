from __future__ import annotations

from scripts.catalog import CatalogError
from scripts.services.install import resolve_install_playbook


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
        pass
    else:
        raise AssertionError("expected docker to require an explicit playbook")

    if (
        resolve_install_playbook(
            ["init"], explicit_playbook="playbooks/workstation.yml"
        )
        != "playbooks/workstation.yml"
    ):
        raise AssertionError("expected init to stay valid on workstation playbook")

    try:
        resolve_install_playbook(["init"], explicit_playbook="playbooks/node.yml")
    except CatalogError:
        return

    raise AssertionError("expected init to be rejected on node playbook")
