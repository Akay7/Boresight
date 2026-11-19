"""The overlay's side-bar placement, end to end without a display: what it
draws and reports for a picture aspect, the controller rebuilding the
solver's layout from that report, and the server setting that asks for
it."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from boresight.detect import detect_markers
from boresight.inject import FakeCursorBackend
from boresight.layout_source import resolve_layout
from boresight.marker_source import MarkerSource, MarkerSourceController
from boresight.overlay import __main__ as overlay_main
from boresight.overlay.layout import (
    BAR_MARKER_IDS,
    OverlayGeometryError,
    centred_picture,
    overlay_layout,
    parse_picture_aspect,
    picture_bar_layout,
)
from boresight.overlay.qt_backend import emit_geometry, plan_overlay
from boresight.overlay.render import layout_patches, render_layout, render_overlay
from boresight.settings import SettingsError, resolve_settings

SCREEN = (1280, 720)
WHOLE = (0, 0, *SCREEN)

# --- the shape --------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"), [("4:3", 4 / 3), ("8:7", 8 / 7), (" 16 : 9 ", 16 / 9)]
)
def test_an_aspect_is_width_over_height(text, value) -> None:
    assert parse_picture_aspect(text) == pytest.approx(value)


@pytest.mark.parametrize("text", ["4x3", "4:0", "0:3", "", "1.33", "4:3:2"])
def test_anything_else_is_refused(text) -> None:
    with pytest.raises(OverlayGeometryError, match="WIDTH:HEIGHT"):
        parse_picture_aspect(text)


def test_the_picture_is_full_height_and_centred() -> None:
    assert centred_picture(SCREEN, 4 / 3) == (160, 0, 960, 720)
    assert centred_picture((1920, 1080), 4 / 3) == (240, 0, 1440, 1080)


def test_a_picture_wider_than_the_screen_fills_it() -> None:
    assert centred_picture((800, 720), 4 / 3) == (0, 0, 800, 720)


# --- 1.2 what the overlay draws and reports -----------------------------------


def test_with_an_aspect_the_overlay_draws_the_bar_layout() -> None:
    plan = plan_overlay(SCREEN, WHOLE, picture_aspect="4:3")
    layout = picture_bar_layout(SCREEN, "4:3")

    assert plan.rect == WHOLE
    assert (plan.canvas == render_layout(SCREEN, layout)).all()
    assert plan.rectangles == layout_patches(layout)
    found = {m.marker_id: tuple(m.corners[0]) for m in detect_markers(plan.canvas)}
    assert set(found) == set(BAR_MARKER_IDS)
    for marker_id, (x, y) in found.items():
        marker = layout.markers[marker_id]
        assert abs(x - marker.x_mm) <= 1.5 and abs(y - marker.y_mm) <= 1.5


def test_no_patch_is_drawn_over_the_picture() -> None:
    plan = plan_overlay(SCREEN, WHOLE, picture_aspect="4:3")
    x, _, width, _ = centred_picture(SCREEN, 4 / 3)

    for left, _top, patch_w, _h in plan.rectangles:
        assert left + patch_w <= x or left >= x + width


def test_the_margin_narrows_the_bars() -> None:
    plain = plan_overlay(SCREEN, WHOLE, picture_aspect="4:3")
    narrowed = plan_overlay(SCREEN, WHOLE, picture_aspect="4:3", margin_px=20)

    assert narrowed.tag_px < plain.tag_px
    assert narrowed.margin_px == 20
    assert all(left >= 20 for left, *_ in narrowed.rectangles)


def test_bars_too_narrow_are_refused() -> None:
    with pytest.raises(OverlayGeometryError, match="1000x768"):
        plan_overlay((1000, 768), (0, 0, 1000, 768), picture_aspect="5:4")


def test_without_an_aspect_the_drawing_is_unchanged() -> None:
    area = (0, 30, 1280, 650)
    plan = plan_overlay(SCREEN, area)
    canvas, rectangles = render_overlay((1280, 650))

    assert (plan.canvas == canvas).all() and plan.rectangles == rectangles
    assert plan.picture_aspect is None


def test_the_window_sits_where_the_layout_says_the_tags_are() -> None:
    """With a manual margin the window covers the area after the margin,
    the same area the layout is placed in. (It used to cover the area
    before the margin, drawing every tag `margin` pixels from where the
    solver expected it.)"""
    area = (24, 24, 1232, 672)  # a 24px margin on every side

    plan = plan_overlay(SCREEN, area)

    assert plan.rect == area
    layout = overlay_layout(SCREEN, plan.tag_px, plan.inset_px, area_px=area)
    for (left, top, *_), marker in zip(
        plan.rectangles, layout.markers.values(), strict=True
    ):
        margin = plan.tag_px // 4
        assert abs(plan.rect[0] + left + margin - marker.x_mm) <= 1
        assert abs(plan.rect[1] + top + margin - marker.y_mm) <= 1


def _report(**kwargs) -> dict:
    out = io.StringIO()
    with redirect_stdout(out):
        emit_geometry(**kwargs)
    return json.loads(out.getvalue())


def test_the_report_names_the_aspect_only_when_there_is_one() -> None:
    plain = _report(screen_px=SCREEN, tag_px=58, inset_px=14, area_px=WHOLE)
    bars = _report(
        screen_px=SCREEN,
        tag_px=106,
        inset_px=0,
        area_px=WHOLE,
        picture_aspect="4:3",
        margin_px=8,
    )

    assert "picture_aspect" not in plain and "margin_px" not in plain
    assert (bars["picture_aspect"], bars["margin_px"]) == ("4:3", 8)


def test_the_command_line_passes_the_aspect(monkeypatch) -> None:
    seen = {}

    def run(*args, **kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr("boresight.overlay.qt_backend.run", run)

    assert overlay_main.main(["--picture-aspect", "4:3"]) == 0
    assert seen["picture_aspect"] == "4:3"


def test_a_bad_aspect_on_the_command_line_is_explained(monkeypatch, capsys) -> None:
    def run(*args, **kwargs):
        parse_picture_aspect(kwargs["picture_aspect"])

    monkeypatch.setattr("boresight.overlay.qt_backend.run", run)

    assert overlay_main.main(["--picture-aspect", "wide"]) == 2
    assert "WIDTH:HEIGHT" in capsys.readouterr().err


# --- 1.3 the controller and the server setting ------------------------------

PRINTED = resolve_layout("file")


def _stub(report: dict):
    body = (
        "import json,time;"
        f"print(json.dumps({json.dumps(report)!s}), flush=True);"
        "time.sleep(60)"
    )
    commands: list[list[str]] = []

    def launch(command, **kwargs):
        commands.append(command)
        return subprocess.Popen([sys.executable, "-c", body], **kwargs)

    launch.commands = commands
    return launch


def test_the_solver_gets_the_bar_layout_the_overlay_reported() -> None:
    launcher = _stub(
        {
            "event": "overlay-ready",
            "screen_px": [1280, 720],
            "area_px": [0, 0, 1280, 720],
            "tag_px": 106,
            "inset_px": 0,
            "picture_aspect": "4:3",
            "margin_px": 8,
        }
    )
    controller = MarkerSourceController(
        FakeCursorBackend(),
        PRINTED,
        launcher=launcher,
        overlay_extra_margin_px=8,
        overlay_picture_aspect="4:3",
    )
    try:
        controller.select(MarkerSource.SCREEN)

        assert controller.pipeline.marker_map == picture_bar_layout(SCREEN, "4:3", 8)
        assert "--picture-aspect=4:3" in launcher.commands[0]
        assert controller.state()["geometry"]["picture_aspect"] == "4:3"
    finally:
        controller.shutdown()


def test_without_an_aspect_the_command_and_layout_are_as_before() -> None:
    launcher = _stub(
        {
            "event": "overlay-ready",
            "screen_px": [1920, 1080],
            "tag_px": 86,
            "inset_px": 22,
        }
    )
    controller = MarkerSourceController(FakeCursorBackend(), PRINTED, launcher=launcher)
    try:
        controller.select(MarkerSource.SCREEN)

        assert controller.pipeline.marker_map == overlay_layout((1920, 1080), 86, 22)
        assert not any("picture-aspect" in arg for arg in launcher.commands[0])
    finally:
        controller.shutdown()


def test_a_bad_aspect_is_refused_when_the_controller_is_made() -> None:
    with pytest.raises(OverlayGeometryError):
        MarkerSourceController(
            FakeCursorBackend(), PRINTED, overlay_picture_aspect="square"
        )


def test_the_settings_file_carries_the_aspect(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[view]\noverlay_picture_aspect = "4:3"\n')

    assert resolve_settings(path, env={}).startup.view.overlay_picture_aspect == "4:3"


def test_the_settings_file_refuses_a_malformed_aspect(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[view]\noverlay_picture_aspect = "4x3"\n')

    with pytest.raises(SettingsError):
        resolve_settings(path, env={})
