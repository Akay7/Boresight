"""Choosing between a printed layout and an on-screen one.

The point of this seam is that it is only a seam: both sources produce
the same type in the same units convention, so nothing downstream has
to know which was chosen.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from boresight.inject import FakeCursorBackend
from boresight.layout_source import (
    LayoutSourceError,
    marker_map_factory,
    resolve_layout,
)
from boresight.marker_map import MarkerMap
from boresight.pipeline import DEFAULT_CONFIG_PATH
from boresight.server import FRAME_SOCKET_PATH, create_app


def test_the_default_is_the_shipped_printed_layout() -> None:
    """Adding a second source must not change what happens to anyone who
    never asked for one."""
    from boresight.marker_map import load_marker_map

    assert resolve_layout() == load_marker_map(DEFAULT_CONFIG_PATH)
    assert resolve_layout("file") == load_marker_map(DEFAULT_CONFIG_PATH)


def test_a_layout_file_of_your_own_can_be_named(tmp_path: Path) -> None:
    path = tmp_path / "mine.toml"
    path.write_text(
        "screen_width_mm = 500\nscreen_height_mm = 300\n\n"
        "[[marker]]\nid = 0\nx = -20\ny = -20\nsize_mm = 40\n"
    )

    layout = resolve_layout(f"file:{path}")

    assert layout.screen_size_mm == (500.0, 300.0)


def test_an_on_screen_layout_is_derived_from_the_display_size() -> None:
    layout = resolve_layout("screen:1920x1080")

    assert layout.screen_size_mm == (1920.0, 1080.0)
    assert set(layout.markers) == set(range(8))


def test_both_sources_produce_the_same_type() -> None:
    """The whole reason this is configuration rather than a code path."""
    assert isinstance(resolve_layout("file"), MarkerMap)
    assert isinstance(resolve_layout("screen:1280x720"), MarkerMap)


@pytest.mark.parametrize(
    "spec", ["nonsense", "screen", "screen:1920", "screen:1920by1080", "wat:1"]
)
def test_an_unrecognised_source_names_the_accepted_forms(spec: str) -> None:
    with pytest.raises(LayoutSourceError) as caught:
        resolve_layout(spec)

    message = str(caught.value)
    assert "file" in message
    assert "screen:1920x1080" in message


def test_a_recognised_but_impossible_screen_is_a_geometry_error() -> None:
    """Distinct from an unparseable spec: this one was understood, and
    the problem is that no layout fits it. Saying 'unrecognised' here
    would send someone hunting for a typo that is not there."""
    from boresight.overlay.layout import OverlayGeometryError

    with pytest.raises(OverlayGeometryError, match="must be positive"):
        resolve_layout("screen:0x0")


def test_a_missing_layout_file_is_reported_as_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_layout(f"file:{tmp_path / 'absent.toml'}")


def test_a_bad_spec_is_rejected_when_written_not_at_first_frame() -> None:
    """`marker_map_factory` resolves once eagerly, so a typo surfaces
    while you are typing it rather than when the phone connects."""
    with pytest.raises(LayoutSourceError, match="unrecognised marker layout"):
        marker_map_factory("screeeen:1920x1080")


def test_the_factory_matches_the_servers_existing_seam() -> None:
    factory = marker_map_factory("screen:1920x1080")

    assert factory().screen_size_mm == (1920.0, 1080.0)


# --- Reaching the pipeline -------------------------------------------


def _app_with(spec: str, backend: FakeCursorBackend):
    return create_app(
        backend_factory=lambda: backend, marker_map_factory=marker_map_factory(spec)
    )


def test_an_on_screen_layout_reaches_the_running_pipeline() -> None:
    backend = FakeCursorBackend()

    with TestClient(_app_with("screen:1920x1080", backend)) as client:
        layout = client.app.state.marker_map

    assert layout.screen_size_mm == (1920.0, 1080.0)
    assert layout.markers[0].size_mm == pytest.approx(86.0)


def test_a_file_layout_still_reaches_it_exactly_as_before() -> None:
    backend = FakeCursorBackend()

    with TestClient(_app_with("file", backend)) as client:
        layout = client.app.state.marker_map

    assert layout.screen_size_mm == (1220.0, 686.0)


def test_the_frame_socket_works_under_an_on_screen_layout() -> None:
    """Not a layout test -- a proof that nothing downstream inspects the
    source. A frame with no markers must behave the same either way."""
    backend = FakeCursorBackend()

    with TestClient(_app_with("screen:1920x1080", backend)) as client:
        with client.websocket_connect(FRAME_SOCKET_PATH) as socket:
            blank = np.zeros((720, 1280, 3), dtype=np.uint8)
            import cv2

            from boresight.stream import pack_frame

            encoded = cv2.imencode(".jpg", blank)[1].tobytes()
            socket.send_bytes(pack_frame(0.0, encoded))
            report = socket.receive_json()

    assert report["outcome"] == "no_markers"
    assert backend.calls == []
