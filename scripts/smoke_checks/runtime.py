from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from ..command_text import SETUP_COMMAND
from ..main import require_setup_completed, setup
from ..runtime_config import (
    SETUP_SCHEMA_VERSION,
    ConfigError,
    ensure_runtime_layout,
    get_runtime_paths,
    is_runtime_setup_complete,
    load_runtime_config,
    mark_runtime_setup_complete,
    resolve_inventory_reference,
)
from ..services.runtime import (
    build_ansible_runtime_env,
    popen_runtime_subprocess,
    run_runtime_subprocess,
)


def check_runtime_config_bootstrap() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        config = load_runtime_config(envmgr_home)

        if config.default_inventory != "default":
            raise AssertionError("expected default inventory alias to be 'default'")

        if config.default_playbook != "workstation":
            raise AssertionError("expected default playbook to be 'workstation'")

        default_inventory_path = config.inventories.get("default")
        if default_inventory_path is None or not default_inventory_path.exists():
            raise AssertionError("expected bootstrap default inventory to exist")

        if not config.paths.config_file.exists():
            raise AssertionError("expected bootstrap config.toml to exist")


def check_setup_marker_is_written_after_setup() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")

        if is_runtime_setup_complete(runtime_paths):
            raise AssertionError(
                "expected setup marker to be absent before setup completes"
            )

        (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
        (runtime_paths.galaxy_collections_dir / "community").mkdir()
        mark_runtime_setup_complete(runtime_paths)

        if not is_runtime_setup_complete(runtime_paths):
            raise AssertionError(
                "expected setup marker to mark the runtime as bootstrapped"
            )
        marker_contents = runtime_paths.setup_marker_file.read_text(encoding="utf-8")
        if f"schema_version = {SETUP_SCHEMA_VERSION}" not in marker_contents:
            raise AssertionError(
                "expected setup marker to persist the setup schema version"
            )
        if 'completed_at = "' not in marker_contents:
            raise AssertionError(
                "expected setup marker to persist the completion timestamp"
            )


def check_unbootstrapped_runtime_surfaces_setup_guidance() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        ensure_runtime_layout(envmgr_home)
        captured_output = io.StringIO()

        with patch("sys.stdout", new=captured_output):
            try:
                require_setup_completed("ping", envmgr_home=envmgr_home)
            except SystemExit as error:
                if error.code != 1:
                    raise AssertionError(
                        "expected unbootstrapped runtime to exit with code 1"
                    ) from error
            else:
                raise AssertionError(
                    "expected unbootstrapped runtime to require setup guidance"
                )

        if f"`{SETUP_COMMAND}`" not in captured_output.getvalue():
            raise AssertionError(
                f"expected setup guidance to mention `{SETUP_COMMAND}`"
            )


def check_outdated_setup_stamp_requires_setup() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
        (runtime_paths.galaxy_roles_dir / "gantsign.oh-my-zsh").mkdir()
        (runtime_paths.galaxy_collections_dir / "community").mkdir()
        runtime_paths.setup_marker_file.write_text(
            'schema_version = 0\ncompleted_at = "2026-04-15T00:00:00Z"\n',
            encoding="utf-8",
        )

        if is_runtime_setup_complete(runtime_paths):
            raise AssertionError(
                "expected outdated setup schema versions to require re-running setup"
            )


def check_unknown_inventory_alias_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        ensure_runtime_layout(envmgr_home)

        try:
            resolve_inventory_reference(
                "inventory/default.yaml",
                envmgr_home=envmgr_home,
            )
        except ConfigError as error:
            message = str(error)
            if "inventory alias 'inventory/default.yaml' is not defined" not in message:
                raise AssertionError(
                    "expected unknown inventory inputs to be rejected as aliases"
                ) from error
            return

        raise AssertionError("expected unknown inventory aliases to raise ConfigError")


def check_runtime_env_uses_runtime_paths_only() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")
        original_roles_path = os.environ.get("ANSIBLE_ROLES_PATH")
        original_collections_path = os.environ.get("ANSIBLE_COLLECTIONS_PATH")
        os.environ["ANSIBLE_ROLES_PATH"] = str(
            Path(temp_dir) / "legacy-roles" / ".ansible" / "roles"
        )
        os.environ["ANSIBLE_COLLECTIONS_PATH"] = str(
            Path(temp_dir) / "legacy-collections" / ".ansible" / "collections"
        )
        try:
            env = build_ansible_runtime_env(runtime_paths)
        finally:
            if original_roles_path is not None:
                os.environ["ANSIBLE_ROLES_PATH"] = original_roles_path
            else:
                os.environ.pop("ANSIBLE_ROLES_PATH", None)
            if original_collections_path is not None:
                os.environ["ANSIBLE_COLLECTIONS_PATH"] = original_collections_path
            else:
                os.environ.pop("ANSIBLE_COLLECTIONS_PATH", None)

        if ".ansible/roles" in env["ANSIBLE_ROLES_PATH"]:
            raise AssertionError(
                "expected runtime roles path to exclude .ansible/roles"
            )
        if ".ansible/collections" in env["ANSIBLE_COLLECTIONS_PATH"]:
            raise AssertionError(
                "expected runtime collections path to exclude .ansible/collections"
            )
        if env["ANSIBLE_LOG_PATH"] != str(runtime_paths.ansible_log_file):
            raise AssertionError("expected ansible log path to point to ~/.envmgr")


def check_runtime_subprocess_helpers_use_runtime_paths() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_paths = ensure_runtime_layout(Path(temp_dir) / ".envmgr")

        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                ["ansible-playbook", "--version"],
                0,
            ),
        ) as mock_run:
            run_runtime_subprocess(
                ["ansible-playbook", "--version"],
                runtime_paths=runtime_paths,
                extra_env={"ENVMGR_TEST_FLAG": "run"},
            )

        run_env = mock_run.call_args.kwargs.get("env")
        if not isinstance(run_env, dict):
            raise AssertionError("expected run helper to pass an env mapping")
        if run_env.get("ANSIBLE_LOG_PATH") != str(runtime_paths.ansible_log_file):
            raise AssertionError(
                "expected run helper to point ansible logs at ~/.envmgr"
            )
        if run_env.get("ENVMGR_TEST_FLAG") != "run":
            raise AssertionError(
                "expected run helper to merge extra environment variables"
            )
        run_records = sorted(runtime_paths.runs_log_dir.glob("*.json"))
        if len(run_records) != 1:
            raise AssertionError("expected run helper to write one runtime record")
        run_payload = json.loads(run_records[0].read_text(encoding="utf-8"))
        if run_payload["status"] != "succeeded":
            raise AssertionError("expected run helper to mark successful records")
        if run_payload["mode"] != "run":
            raise AssertionError("expected run helper to record mode=run")
        if run_payload["return_code"] != 0:
            raise AssertionError("expected run helper to persist return_code=0")
        if run_payload["ansible_log_file"] != str(runtime_paths.ansible_log_file):
            raise AssertionError("expected run helper to persist the ansible log path")
        if run_payload["completed_at"] is None:
            raise AssertionError("expected run helper to persist completion timestamps")

        mock_process = Mock()
        mock_process.pid = 4242
        mock_process.wait.return_value = 0
        mock_process.poll.return_value = None
        mock_process.returncode = 0

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            process = popen_runtime_subprocess(
                ["ansible-playbook", "--version"],
                runtime_paths=runtime_paths,
                extra_env={"ENVMGR_TEST_FLAG": "popen"},
                stdout=subprocess.PIPE,
            )
            process.wait()

        popen_env = mock_popen.call_args.kwargs.get("env")
        if not isinstance(popen_env, dict):
            raise AssertionError("expected popen helper to pass an env mapping")
        if popen_env.get("ANSIBLE_LOCAL_TEMP") != str(runtime_paths.tmp_dir):
            raise AssertionError(
                "expected popen helper to point ansible temp files at ~/.envmgr"
            )
        if popen_env.get("ENVMGR_TEST_FLAG") != "popen":
            raise AssertionError(
                "expected popen helper to merge extra environment variables"
            )
        popen_records = sorted(runtime_paths.runs_log_dir.glob("*.json"))
        if len(popen_records) != 2:
            raise AssertionError(
                "expected popen helper to append a second runtime record"
            )
        popen_payload = json.loads(popen_records[-1].read_text(encoding="utf-8"))
        if popen_payload["mode"] != "popen":
            raise AssertionError("expected popen helper to record mode=popen")
        if popen_payload["status"] != "succeeded":
            raise AssertionError("expected popen helper to mark successful records")
        if popen_payload["pid"] != 4242:
            raise AssertionError("expected popen helper to persist the child pid")
        if popen_payload["return_code"] != 0:
            raise AssertionError(
                "expected popen helper to persist the child return code"
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


def check_inventory_aliases_stay_under_runtime_inventory_dir() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = ensure_runtime_layout(envmgr_home)
        runtime_paths.config_file.write_text(
            """
[default]
inventory = "default"

[inventory]
default = "../outside/default.yaml"
""".lstrip(),
            encoding="utf-8",
        )

        try:
            load_runtime_config(envmgr_home)
        except ConfigError as error:
            if "must stay under" not in str(error):
                raise AssertionError(
                    "expected inventory aliases outside ~/.envmgr/inventory to fail"
                ) from error
            return

        raise AssertionError("expected out-of-tree inventory aliases to fail")


def check_invalid_toml_surfaces_config_error() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = ensure_runtime_layout(envmgr_home)
        runtime_paths.config_file.write_text(
            '[default]\ninventory = "default"\ninvalid = [\n',
            encoding="utf-8",
        )

        try:
            load_runtime_config(envmgr_home)
        except ConfigError as error:
            if "contains invalid TOML" not in str(error):
                raise AssertionError(
                    "expected invalid TOML errors to be wrapped in ConfigError"
                ) from error
            return

        raise AssertionError("expected invalid TOML to raise ConfigError")


def check_missing_runtime_inventory_file_is_recreated() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        envmgr_home = Path(temp_dir) / ".envmgr"
        runtime_paths = ensure_runtime_layout(envmgr_home)
        runtime_paths.default_inventory_file.unlink()

        resolved_path, resolved_label = resolve_inventory_reference(
            None, envmgr_home=envmgr_home
        )
        if resolved_label != "default":
            raise AssertionError("expected recreated runtime inventory to keep alias")
        if resolved_path != runtime_paths.default_inventory_file.resolve():
            raise AssertionError(
                "expected recreated runtime inventory path to match ~/.envmgr"
            )
        if not runtime_paths.default_inventory_file.exists():
            raise AssertionError(
                "expected missing runtime inventory file to be recreated"
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
