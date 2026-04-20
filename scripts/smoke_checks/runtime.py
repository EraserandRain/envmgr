from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ..main import setup
from ..runtime_config import (
    ensure_runtime_layout,
    get_runtime_paths,
    resolve_inventory_reference,
)
from ..services.runtime import (
    run_runtime_subprocess,
)


def check_setup_logs_ansible_galaxy_runs() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"

        def fake_run(
            command: list[str],
            *,
            env: dict[str, str] | None = None,
            **_kwargs: Any,
        ) -> subprocess.CompletedProcess[Any]:
            return subprocess.CompletedProcess(command, 0)

        with (
            patch("subprocess.run", side_effect=fake_run),
            patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
        ):
            setup()

        runtime_paths = get_runtime_paths(envmgr_home)
        run_records = sorted(runtime_paths.runs_log_dir.glob("*.json"))
        if len(run_records) != 2:
            raise AssertionError(
                "expected setup to log the role and collection galaxy installs"
            )

        payloads = [
            json.loads(record.read_text(encoding="utf-8")) for record in run_records
        ]
        commands = [payload["command"][:3] for payload in payloads]
        if ["ansible-galaxy", "role", "install"] not in commands:
            raise AssertionError(
                "expected setup to log the Galaxy role installation command"
            )
        if ["ansible-galaxy", "collection", "install"] not in commands:
            raise AssertionError(
                "expected setup to log the Galaxy collection installation command"
            )
        if not runtime_paths.setup_marker_file.exists():
            raise AssertionError(
                "expected setup to keep writing the runtime setup marker"
            )


def check_setup_succeeds_outside_repo_cwd() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        envmgr_home = workspace / ".envmgr"
        original_cwd = Path.cwd()
        try:
            os.chdir(workspace)
            with (
                patch.dict(os.environ, {"ENVMGR_HOME": str(envmgr_home)}, clear=False),
                patch(
                    "scripts.commands.setup.run_runtime_subprocess",
                    return_value=subprocess.CompletedProcess(
                        ["ansible-galaxy", "--version"],
                        0,
                    ),
                ) as mock_run_runtime_subprocess,
            ):
                setup()
        finally:
            os.chdir(original_cwd)

        runtime_paths = get_runtime_paths(envmgr_home)
        if not runtime_paths.setup_marker_file.exists():
            raise AssertionError(
                "expected non-repo-cwd setup to keep writing the setup marker"
            )
        if mock_run_runtime_subprocess.call_count != 2:
            raise AssertionError(
                "expected setup outside the repo cwd to run both Galaxy installs"
            )

        expected_requirements = str(repo_root / "requirements.yaml")
        for call in mock_run_runtime_subprocess.call_args_list:
            command = call.args[0]
            if "-r" not in command:
                raise AssertionError(
                    "expected setup to pass the requirements file to ansible-galaxy"
                )
            if command[command.index("-r") + 1] != expected_requirements:
                raise AssertionError(
                    "expected setup outside the repo cwd to resolve requirements.yaml "
                    "from the packaged runtime assets"
                )


def check_multi_node_inventory_topology() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = ensure_runtime_layout(envmgr_home)
        runtime_paths.config_file.write_text(
            """
[default]
inventory = "ci_cluster"
playbook = "node"
ask_vault_pass = false

[inventory]
default = "inventory/default.yaml"
remote = "inventory/remote.yaml"
password = "inventory/password.yaml"
ci_cluster = "inventory/ci-cluster.yaml"
""".lstrip(),
            encoding="utf-8",
        )

        ci_inventory_path = runtime_paths.inventory_dir / "ci-cluster.yaml"
        ci_inventory_path.write_text(
            """
all:
  children:
    node:
      children:
        master:
          hosts:
            master-ci:
              ansible_connection: local
              ansible_python_interpreter: "{{ ansible_playbook_python }}"
        worker:
          hosts:
            worker-ci-1:
              ansible_connection: local
              ansible_python_interpreter: "{{ ansible_playbook_python }}"
            worker-ci-2:
              ansible_connection: local
              ansible_python_interpreter: "{{ ansible_playbook_python }}"
""".lstrip(),
            encoding="utf-8",
        )

        inventory_path, inventory_label = resolve_inventory_reference(
            "ci_cluster",
            envmgr_home=envmgr_home,
        )
        if inventory_label != "ci_cluster":
            raise AssertionError("expected ci_cluster inventory alias to resolve")

        try:
            list_hosts_result = run_runtime_subprocess(
                [
                    "ansible-playbook",
                    "-i",
                    str(inventory_path),
                    "playbooks/node.yml",
                    "--list-hosts",
                ],
                check=True,
                runtime_paths=runtime_paths,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            output = (error.stdout or error.stderr or "").strip()
            raise AssertionError(
                "expected node playbook to list hosts for ci_cluster inventory"
                + (f": {output}" if output else "")
            ) from error

        list_hosts_output = list_hosts_result.stdout
        for host_name in ("master-ci", "worker-ci-1", "worker-ci-2"):
            if host_name not in list_hosts_output:
                raise AssertionError(f"expected node playbook to target {host_name}")

        topology_playbook_path = Path(temp_dir) / "ci-cluster-topology.yml"
        topology_playbook_path.write_text(
            """
- name: Verify master topology
  hosts: master
  gather_facts: false
  tasks:
    - name: Assert master inventory wiring
      ansible.builtin.assert:
        that:
          - inventory_hostname == 'master-ci'
          - groups['master'] | length == 1
          - groups['worker'] | length == 2
          - groups['node'] | sort | join(',') == 'master-ci,worker-ci-1,worker-ci-2'
          - "'master' in group_names"
          - "'worker' not in group_names"

- name: Verify worker topology
  hosts: worker
  gather_facts: false
  tasks:
    - name: Assert worker inventory wiring
      ansible.builtin.assert:
        that:
          - inventory_hostname in groups['worker']
          - groups['master'][0] == 'master-ci'
          - groups['worker'] | sort | join(',') == 'worker-ci-1,worker-ci-2'
          - "'worker' in group_names"
          - "'master' not in group_names"
""".lstrip(),
            encoding="utf-8",
        )

        try:
            run_runtime_subprocess(
                [
                    "ansible-playbook",
                    "-i",
                    str(inventory_path),
                    str(topology_playbook_path),
                ],
                check=True,
                runtime_paths=runtime_paths,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            output = "\n".join(
                part
                for part in (
                    (error.stdout or "").strip(),
                    (error.stderr or "").strip(),
                )
                if part
            )
            raise AssertionError(
                "expected ci_cluster topology playbook to validate master and "
                "worker group wiring" + (f": {output}" if output else "")
            ) from error
