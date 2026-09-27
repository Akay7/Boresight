"""Which displays the machine has, and pinning the cursor to one on Linux.

A display is chosen by its output name -- `HDMI-A-1`, `\\\\.\\DISPLAY2` --
because that is the one identifier the compositor, xrandr, Qt
(`QScreen.name()`) and Windows share, and it survives a monitor being
unplugged where an index would not.

Windows and macOS list their monitors through their own backends
(`inject_win32`, `inject_darwin`), which map the cursor onto a monitor's
rectangle themselves. On Linux the uinput cursor is an absolute device
the compositor maps, and how it maps one is not something the server
can observe -- so rather than aim at a sub-rectangle and hope, the
device is pinned to the output through the compositor itself:

- KDE Plasma (Wayland): KWin lists every input device on D-Bus, and the
  boresight-cursor tablet has a writable `outputName`. KWin may save
  the choice in `~/.config/kcminputrc`, as System Settings would.
- X11: `xinput map-to-output`.

Anything else is reported as unpinnable, pointing at the compositor's
own tablet settings. Every command goes through an injectable runner,
so the tests feed canned output instead of a desktop.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from boresight.inject import Rect

# The uinput device the cursor moves (see `inject.UinputCursorBackend`).
CURSOR_DEVICE_NAME = "boresight-cursor"

# KWin registers a new device a moment after uinput creates it.
PIN_ATTEMPTS = 20
PIN_INTERVAL_S = 0.1

Runner = Callable[[Sequence[str]], str]


class DisplayError(RuntimeError):
    """A display that cannot be listed, found or pinned, and why."""


@dataclass(frozen=True)
class Display:
    name: str
    # Desktop coordinates: pixels on Windows, points on macOS, logical
    # (scaled) pixels on Linux, where it is for showing only.
    rect: Rect
    primary: bool = False

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "x": self.rect.x,
            "y": self.rect.y,
            "width": self.rect.width,
            "height": self.rect.height,
            "primary": self.primary,
        }


def run(command: Sequence[str]) -> str:
    """Run `command` and return its output; DisplayError if it fails."""
    try:
        done = subprocess.run(
            list(command), capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DisplayError(f"could not run {command[0]}: {error}") from error
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise DisplayError(
            f"{command[0]} failed: {detail[-1] if detail else done.returncode}"
        )
    return done.stdout


def choose(displays: Sequence[Display], name: str) -> Display:
    """The display called `name`, or the primary one for an empty name."""
    if not displays:
        raise DisplayError("this machine reports no displays")
    if not name:
        return next((d for d in displays if d.primary), displays[0])
    for display in displays:
        if display.name == name:
            return display
    available = ", ".join(d.name for d in displays)
    raise DisplayError(f"no display {name!r}; this machine has: {available}")


# --- Linux ---------------------------------------------------------------


def is_kde_wayland(environ: Mapping[str, str] | None = None) -> bool:
    environ = os.environ if environ is None else environ
    return bool(environ.get("WAYLAND_DISPLAY")) and "KDE" in environ.get(
        "XDG_CURRENT_DESKTOP", ""
    ).split(":")


def is_x11(environ: Mapping[str, str] | None = None) -> bool:
    environ = os.environ if environ is None else environ
    return bool(environ.get("DISPLAY")) and not environ.get("WAYLAND_DISPLAY")


def parse_kscreen(text: str) -> list[Display]:
    """`kscreen-doctor -j`: enabled outputs, at their logical size."""
    try:
        outputs = json.loads(text)["outputs"]
    except (ValueError, KeyError, TypeError) as error:
        raise DisplayError(f"unexpected kscreen-doctor output: {error}") from error
    displays = []
    for output in outputs:
        if not output.get("enabled") or not output.get("connected"):
            continue
        scale = float(output.get("scale") or 1.0)
        position, size = output["pos"], output["size"]
        displays.append(
            Display(
                name=output["name"],
                rect=Rect(
                    float(position["x"]),
                    float(position["y"]),
                    size["width"] / scale,
                    size["height"] / scale,
                ),
                # KDE's "primary" is the output with priority 1.
                primary=output.get("priority") == 1,
            )
        )
    return displays


# ` 0: +*HDMI-1 1920/527x1080/296+0+0  HDMI-1`
_XRANDR_MONITOR = re.compile(
    r"^\s*\d+:\s+\+?(?P<primary>\*)?(?P<name>\S+)\s+"
    r"(?P<w>\d+)/\d+x(?P<h>\d+)/\d+\+(?P<x>-?\d+)\+(?P<y>-?\d+)"
)


def parse_xrandr(text: str) -> list[Display]:
    """`xrandr --listmonitors`."""
    displays = []
    for line in text.splitlines():
        match = _XRANDR_MONITOR.match(line)
        if match is None:
            continue
        displays.append(
            Display(
                name=match["name"],
                rect=Rect(
                    float(match["x"]),
                    float(match["y"]),
                    float(match["w"]),
                    float(match["h"]),
                ),
                primary=match["primary"] is not None,
            )
        )
    return displays


def list_linux_displays(
    runner: Runner = run, environ: Mapping[str, str] | None = None
) -> list[Display]:
    if is_kde_wayland(environ):
        try:
            return parse_kscreen(runner(["kscreen-doctor", "-j"]))
        except DisplayError:
            pass  # xrandr still reports XWayland's view of the outputs
    return parse_xrandr(runner(["xrandr", "--listmonitors"]))


_KWIN = ["busctl", "--user"]
_KWIN_SERVICE = "org.kde.KWin"
_KWIN_DEVICES = "/org/kde/KWin/InputDevice"
_KWIN_DEVICE = "org.kde.KWin.InputDevice"


def _busctl_string(text: str) -> str:
    """The value of a `busctl get-property` answer: `s "eDP-1"`."""
    match = re.fullmatch(r's "(.*)"', text.strip())
    return match.group(1) if match else ""


def _kwin_device(runner: Runner, device_name: str) -> str | None:
    """The D-Bus path of the KWin input device called `device_name`."""
    answer = runner(
        [
            *_KWIN,
            "get-property",
            _KWIN_SERVICE,
            _KWIN_DEVICES,
            "org.kde.KWin.InputDeviceManager",
            "devicesSysNames",
        ]
    )
    # `as 3 "event0" "event1" "event2"`
    for sys_name in re.findall(r'"([^"]+)"', answer):
        path = f"{_KWIN_DEVICES}/{sys_name}"
        name = runner(
            [*_KWIN, "get-property", _KWIN_SERVICE, path, _KWIN_DEVICE, "name"]
        )
        if _busctl_string(name) == device_name:
            return path
    return None


def pin_linux_device(
    output: str,
    device_name: str = CURSOR_DEVICE_NAME,
    runner: Runner = run,
    environ: Mapping[str, str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Pin the absolute device `device_name` to `output`.

    Raises DisplayError when the compositor cannot be asked, or refuses.
    """
    if is_kde_wayland(environ):
        path = None
        for attempt in range(PIN_ATTEMPTS):
            path = _kwin_device(runner, device_name)
            if path is not None:
                break
            if attempt + 1 < PIN_ATTEMPTS:
                sleep(PIN_INTERVAL_S)
        if path is None:
            raise DisplayError(f"KWin does not list the {device_name} device")
        runner(
            [
                *_KWIN,
                "set-property",
                _KWIN_SERVICE,
                path,
                _KWIN_DEVICE,
                "outputName",
                "s",
                output,
            ]
        )
        return
    if is_x11(environ):
        runner(["xinput", "map-to-output", device_name, output])
        return
    raise DisplayError(
        "this desktop gives Boresight no way to pin its cursor to a display. "
        f"Map the {device_name!r} tablet to the display in the compositor's "
        "own tablet settings instead."
    )
