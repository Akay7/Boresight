"""The server must import where Linux-only modules do not exist.

Run in a fresh interpreter with those modules made unimportable, so a
top-level import of one -- the easiest way to break Windows and macOS
without noticing -- fails here, on Linux, too.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

BLOCKED = ("evdev", "fcntl", "PySide6")

SCRIPT = textwrap.dedent(
    f"""
    import importlib.abc
    import sys

    BLOCKED = {BLOCKED!r}

    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ModuleNotFoundError(f"blocked: {{name}}")
            return None

    for name in list(sys.modules):
        if name.split(".")[0] in BLOCKED:
            del sys.modules[name]
    sys.meta_path.insert(0, Block())

    import boresight.inject_darwin
    import boresight.inject_win32
    import boresight.marker_source
    import boresight.pipeline
    import boresight.server

    boresight.server.create_app()
    print("ok")
    """
)


def test_the_server_imports_without_linux_only_modules() -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
