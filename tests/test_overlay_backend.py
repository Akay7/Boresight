"""Whether this machine can host the overlay, decided before any window.

These run everywhere: no display is opened and the Qt extra need not be
installed. Environments are simulated by passing an `Environment` in,
rather than by reading the machine the tests happen to run on.

What is really under test is the refusal path. An overlay that starts
where it cannot work would render but sit in the normal stacking order
and take input -- swallowing the clicks Boresight injects at the aim
point, and looking like a Boresight bug rather than a compositor
limitation.
"""

from __future__ import annotations

import sys

import pytest

from boresight.overlay.backend import (
    Environment,
    OverlayDependencyError,
    OverlayUnavailableError,
    check_supported,
    detect_environment,
    require_toolkit,
    supports_layer_shell,
)

X11 = Environment(platform="linux", session_type="x11", desktop="kde")
WAYLAND_KDE = Environment(platform="linux", session_type="wayland", desktop="kde")
WAYLAND_SWAY = Environment(platform="linux", session_type="wayland", desktop="sway")
WAYLAND_GNOME = Environment(platform="linux", session_type="wayland", desktop="gnome")
WINDOWS = Environment(platform="win32")
MACOS = Environment(platform="darwin")


# --- Environments that work ------------------------------------------


@pytest.mark.parametrize(
    "environment", [X11, WAYLAND_KDE, WAYLAND_SWAY, WINDOWS], ids=lambda e: str(e)
)
def test_supported_environments_pass_the_check(environment: Environment) -> None:
    check_supported(environment)  # must not raise


def test_x11_is_supported_regardless_of_desktop() -> None:
    """On X11 any window manager will honour an override-redirect,
    always-on-top window, so the desktop does not matter."""
    check_supported(Environment(platform="linux", session_type="x11", desktop="gnome"))


# --- Environments that do not ----------------------------------------


def test_wayland_without_layer_shell_is_refused() -> None:
    """GNOME's Mutter declines to implement wlr-layer-shell. That is an
    upstream design position, not a gap that will close, so the honest
    move is to refuse rather than degrade."""
    with pytest.raises(OverlayUnavailableError) as caught:
        check_supported(WAYLAND_GNOME)

    message = str(caught.value)
    assert "layer-shell" in message
    assert "gnome" in message.lower()


def test_the_refusal_names_printed_markers_as_the_alternative() -> None:
    """A refusal that leaves someone stuck is only half a message."""
    with pytest.raises(OverlayUnavailableError) as caught:
        check_supported(WAYLAND_GNOME)

    assert "printed markers" in str(caught.value).lower()


def test_the_refusal_explains_what_would_go_wrong() -> None:
    """Not just 'unsupported'. The consequence -- swallowed clicks -- is
    the part that makes the refusal obviously right rather than
    obstructive."""
    with pytest.raises(OverlayUnavailableError) as caught:
        check_supported(WAYLAND_GNOME)

    assert "click" in str(caught.value).lower()


def test_an_unsupported_platform_is_refused() -> None:
    with pytest.raises(OverlayUnavailableError, match="no backend for darwin"):
        check_supported(MACOS)

    assert "printed markers" in _refusal(MACOS).lower()


def _refusal(environment: Environment) -> str:
    with pytest.raises(OverlayUnavailableError) as caught:
        check_supported(environment)
    return str(caught.value)


# --- Layer-shell detection -------------------------------------------


@pytest.mark.parametrize("desktop", ["kde", "KDE", "plasma", "sway", "hyprland"])
def test_compositors_with_layer_shell_are_recognised(desktop: str) -> None:
    assert supports_layer_shell(
        Environment(platform="linux", session_type="wayland", desktop=desktop.lower())
    )


@pytest.mark.parametrize("desktop", ["gnome", "unity", None])
def test_compositors_without_layer_shell_are_not_assumed(desktop: str | None) -> None:
    """Unknown means unsupported. Guessing optimistically here produces
    exactly the broken overlay the check exists to prevent."""
    assert not supports_layer_shell(
        Environment(platform="linux", session_type="wayland", desktop=desktop)
    )


# --- Reading the environment -----------------------------------------


def test_the_environment_is_read_from_the_session_variables() -> None:
    environment = detect_environment(
        {"XDG_SESSION_TYPE": "Wayland", "XDG_CURRENT_DESKTOP": "KDE"}
    )

    assert environment.session_type == "wayland"
    assert environment.desktop == "kde"
    assert environment.is_wayland is (sys.platform == "linux")


def test_absent_session_variables_do_not_crash() -> None:
    environment = detect_environment({})

    assert environment.session_type is None
    assert environment.desktop is None
    assert not environment.is_wayland


def test_a_wayland_variable_off_linux_is_not_wayland() -> None:
    """`is_wayland` gates a Linux-only protocol check, so it must not
    fire on another platform that happens to set the variable."""
    environment = Environment(platform="win32", session_type="wayland")

    assert not environment.is_wayland


# --- The optional dependency -----------------------------------------


def test_a_missing_toolkit_names_the_extra_to_install(monkeypatch) -> None:
    """An ImportError traceback would say the installation is broken. It
    is not: the overlay group is optional and omitting it is the right
    default for anyone using printed markers."""
    monkeypatch.setitem(sys.modules, "PySide6", None)

    with pytest.raises(OverlayDependencyError) as caught:
        require_toolkit()

    message = str(caught.value)
    assert "--extra overlay" in message
    assert "boresight[overlay]" in message


def test_a_missing_dependency_is_also_an_unavailable_overlay() -> None:
    """So one `except` at the entry point covers both, and neither
    reaches the user as a traceback."""
    assert issubclass(OverlayDependencyError, OverlayUnavailableError)


# --- The entry point --------------------------------------------------


def test_the_entry_point_reports_rather_than_traces(monkeypatch, capsys) -> None:
    from boresight.overlay.__main__ import main

    monkeypatch.setitem(sys.modules, "PySide6", None)

    assert main([]) == 2
    assert "--extra overlay" in capsys.readouterr().err


def test_the_entry_point_reports_an_unsupported_environment(
    monkeypatch, capsys
) -> None:
    from boresight.overlay import qt_backend

    def refuse(*args, **kwargs):
        raise OverlayUnavailableError("nope, and printed markers still work")

    monkeypatch.setattr(qt_backend, "check_supported", refuse)

    from boresight.overlay.__main__ import main

    assert main([]) == 2
    assert "printed markers" in capsys.readouterr().err
