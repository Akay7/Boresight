"""What `pyproject.toml` promises an installed copy: commands that
resolve to the same programs `python -m` runs."""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text())["project"]


def test_every_console_script_resolves_to_a_callable() -> None:
    scripts = _project()["scripts"]

    assert set(scripts) == {"boresight", "boresight-overlay"}
    for target in scripts.values():
        module_name, _, attribute = target.partition(":")
        assert callable(getattr(importlib.import_module(module_name), attribute))


def test_the_server_command_is_the_module_entry_point() -> None:
    """`boresight` and `python -m boresight.server` must be one program,
    or the validation in `main()` could be skipped by one of them."""
    from boresight import server
    from boresight.overlay import __main__ as overlay

    scripts = _project()["scripts"]
    assert scripts["boresight"] == f"{server.__name__}:{server.main.__name__}"
    assert scripts["boresight-overlay"] == f"{overlay.__name__}:{overlay.main.__name__}"
