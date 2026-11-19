"""Starting the gun with the user's desktop session.

`boresight-gun --autostart` writes a desktop autostart entry: the XDG
mechanism every Linux desktop session runs, Raspberry Pi OS's included.
It needs no root and no particular init system. The entry runs this same
Python, from this same venv, with the same configuration, and starts it
again after a failure (but not after a clean exit) with a short pause
in between.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

ENTRY_NAME = "boresight-gun.desktop"
RESTART_PAUSE_S = 2


def autostart_dir(environ=os.environ) -> Path:
    base = environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart"


def gun_command(config: Path | None) -> list[str]:
    """This interpreter running the gun, so the entry starts the same
    install. The config path is made absolute: the session starts it from
    the home directory."""
    command = [sys.executable, "-m", "boresight.gun"]
    if config is not None:
        command += ["--config", str(Path(config).resolve())]
    return command


def restart_script(command: list[str], pause_s: float = RESTART_PAUSE_S) -> str:
    """A shell loop that runs `command` until it exits cleanly."""
    return f"until {shlex.join(command)}; do sleep {pause_s:g}; done"


def _desktop_quote(argument: str) -> str:
    """One argument of a desktop entry's `Exec`, by the spec: in double
    quotes, with `"`, backquote, `$` and backslash escaped by a backslash.
    `%` is escaped as `%%` separately, for the whole line."""
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in argument)
    return f'"{escaped}"'


def entry_text(command: list[str], pause_s: float = RESTART_PAUSE_S) -> str:
    exec_line = "sh -c " + _desktop_quote(restart_script(command, pause_s))
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Boresight gun\n"
        "Comment=Aim with the gun's camera at this display\n"
        f"Exec={exec_line.replace('%', '%%')}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def write_entry(config: Path | None, environ=os.environ) -> Path:
    folder = autostart_dir(environ)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ENTRY_NAME
    path.write_text(entry_text(gun_command(config)))
    return path


def remove_entry(environ=os.environ) -> Path | None:
    path = autostart_dir(environ) / ENTRY_NAME
    if not path.exists():
        return None
    path.unlink()
    return path
