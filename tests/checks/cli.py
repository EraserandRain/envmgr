from __future__ import annotations

import io
from unittest.mock import patch

from scripts.main import main


def check_dispatcher_routes_install_subcommand() -> None:
    captured_output = io.StringIO()

    with (
        patch("sys.stdout", new=captured_output),
        patch(
            "scripts.commands.install.load_available_tags",
            return_value=(["zsh"], ["codex"]),
        ),
    ):
        main(["install", "-l"])

    output = captured_output.getvalue()
    if "Envmgr available tags:" not in output:
        raise AssertionError("expected dispatcher to route to the install subcommand")
    if "  - zsh" not in output:
        raise AssertionError("expected dispatcher to print install role tags")
    if "  - codex" not in output:
        raise AssertionError("expected dispatcher to print install task tags")


def check_dispatcher_rejects_dev_only_subcommands() -> None:
    captured_error = io.StringIO()

    with patch("sys.stderr", new=captured_error):
        try:
            main(["validate"])
        except SystemExit as error:
            if error.code != 2:
                raise AssertionError(
                    "expected dispatcher to reject dev-only subcommands with exit code 2"
                ) from error
        else:
            raise AssertionError("expected dispatcher to reject dev-only subcommands")

    if "invalid choice" not in captured_error.getvalue():
        raise AssertionError("expected dispatcher rejection to come from argparse")
