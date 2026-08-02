"""Getting the tags onto the screen, on three platforms that disagree.

The two things an overlay must do -- sit above everything, and refuse
all input -- have no common mechanism across X11, Wayland and Windows.
Qt papers over most of it: `WindowTransparentForInput` becomes an empty
XShape input region on X11 and `WS_EX_TRANSPARENT` on Windows, so one
widget covers two platforms.

Wayland is the exception, and deliberately so upstream: an ordinary
client is not allowed to place itself above other windows. The
sanctioned route is the `wlr-layer-shell` protocol, which KWin and the
wlroots compositors implement and GNOME's Mutter does not. Where it is
missing, this module refuses to start and says why.

That refusal is the important behaviour here. The failure it avoids is
a surface that renders but sits in the normal stacking order and takes
input -- which would swallow the clicks Boresight injects at the aim
point, and would look like a Boresight bug rather than a compositor
limitation.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

PRINTED_MARKERS_HINT = (
    "Printed markers work on any platform and need no overlay: "
    "run the server and open /markers to print a sheet."
)

INSTALL_HINT = (
    "The overlay needs its optional dependencies. Install them with "
    "`uv sync --extra overlay` (or `pip install 'boresight[overlay]'`)."
)


class OverlayUnavailableError(RuntimeError):
    """Raised when this environment cannot host the overlay.

    Always carries a reason a person can act on, and names printed
    markers as the alternative. Never raised for a problem the user
    could fix by installing something -- that is
    `OverlayDependencyError`, which says what to install.
    """


class OverlayDependencyError(OverlayUnavailableError):
    """Raised when the overlay extra is not installed."""


@dataclass(frozen=True)
class Environment:
    """What we can tell about the display environment without a toolkit."""

    platform: str
    session_type: str | None = None
    desktop: str | None = None

    @property
    def is_wayland(self) -> bool:
        return self.platform == "linux" and self.session_type == "wayland"


def detect_environment(env: dict[str, str] | None = None) -> Environment:
    environ = os.environ if env is None else env
    return Environment(
        platform=sys.platform,
        session_type=(environ.get("XDG_SESSION_TYPE") or "").lower() or None,
        desktop=(environ.get("XDG_CURRENT_DESKTOP") or "").lower() or None,
    )


# Compositors implementing wlr-layer-shell, which is what an overlay
# needs on Wayland. GNOME is absent because Mutter declines to
# implement it -- a design position rather than a gap, so this list is
# unlikely to grow on its own.
_LAYER_SHELL_DESKTOPS = ("kde", "plasma", "sway", "hyprland", "wlroots", "river")


def supports_layer_shell(environment: Environment) -> bool:
    desktop = environment.desktop or ""
    return any(name in desktop for name in _LAYER_SHELL_DESKTOPS)


def check_supported(environment: Environment | None = None) -> None:
    """Raise `OverlayUnavailableError` if the overlay cannot work here.

    Checked before any window is created, so the failure arrives as an
    explanation rather than as a window that misbehaves.
    """
    environment = environment or detect_environment()

    if environment.platform not in ("linux", "win32"):
        raise OverlayUnavailableError(
            f"the overlay has no backend for {environment.platform}. "
            f"{PRINTED_MARKERS_HINT}"
        )

    if environment.is_wayland and not supports_layer_shell(environment):
        raise OverlayUnavailableError(
            "this Wayland compositor "
            f"({environment.desktop or 'unknown'}) does not support the "
            "layer-shell protocol, so a client cannot place a surface "
            "above other windows. An overlay here would render but sit "
            "in the normal stacking order and swallow the clicks "
            "Boresight injects.\n"
            "Log into an X11 session, use a compositor with layer-shell "
            f"(KDE, sway, Hyprland), or use printed markers. {PRINTED_MARKERS_HINT}"
        )


def require_toolkit():
    """Import Qt, or explain how to install it.

    An `ImportError` traceback tells a user their installation is
    broken. It is not -- they simply installed the project without an
    optional group, which is the default and the right choice for
    anyone using printed markers.
    """
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError as exc:
        raise OverlayDependencyError(INSTALL_HINT) from exc
    return QtCore, QtGui, QtWidgets
