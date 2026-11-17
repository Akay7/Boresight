"""The aim pipeline must work with only the core dependencies installed,
as on a Raspberry Pi running `boresight-gun`. A subprocess imports it with
every server-only package blocked, which is what a core-only install is."""

from __future__ import annotations

import subprocess
import sys
import textwrap

BLOCK = textwrap.dedent(
    """
    import importlib.abc, sys

    SERVER_ONLY = {"fastapi", "uvicorn", "starlette", "pydantic", "evdev",
                   "cryptography", "segno", "httpx", "websockets", "zeroconf"}

    class Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name.split(".")[0] in SERVER_ONLY:
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    sys.meta_path.insert(0, Blocker())
    """
)


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-c", BLOCK + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_aim_pipeline_imports_without_the_server_dependencies() -> None:
    result = _run(
        """
        import boresight.pipeline, boresight.aim_hold, boresight.lens
        import boresight.zeroing, boresight.inject, boresight.marker_map
        import boresight.one_euro, boresight.detect, boresight.solve
        """
    )
    assert result.returncode == 0, result.stderr


def test_the_server_says_how_to_install_its_dependencies() -> None:
    result = _run("import boresight.server")
    assert result.returncode != 0
    assert "boresight[server]" in result.stderr
