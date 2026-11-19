"""Tags in the bars beside a centred picture: a 4:3 or 8:7 game shown on
a 16:9 TV leaves bars at the sides, and tags there never cover the game.

Pure geometry and images, no display: what `render_layout` draws goes
through the real detector and solver.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from boresight.detect import detect_markers
from boresight.inject import FakeCursorBackend
from boresight.overlay.layout import (
    BAR_MARKER_IDS,
    OverlayGeometryError,
    bar_layout,
    min_bar_px,
    quiet_patch_px,
)
from boresight.overlay.render import render_layout
from boresight.pipeline import AimPipeline, FrameOutcome


def centred(screen: tuple[int, int], aspect: float) -> tuple[int, int, int, int]:
    """A full-height picture of `aspect`, centred: what an emulator shows."""
    width = round(screen[1] * aspect)
    width -= (screen[0] - width) % 2
    return ((screen[0] - width) // 2, 0, width, screen[1])


FOUR_THREE = 4 / 3
NES = 256 * 8 / 7 / 240  # 8:7 pixels

# Outputs and pictures with bars wide enough.
ACCEPTED = [
    ((1280, 720), FOUR_THREE),
    ((1920, 1080), FOUR_THREE),
    ((1280, 720), NES),
    ((1920, 1080), NES),
    ((1366, 768), FOUR_THREE),
    ((640, 480), NES),
]


def _patch(marker) -> tuple[int, int, int, int]:
    margin = quiet_patch_px(round(marker.size_mm))
    return (
        round(marker.x_mm) - margin,
        round(marker.y_mm) - margin,
        round(marker.x_mm + marker.size_mm) + margin,
        round(marker.y_mm + marker.size_mm) + margin,
    )


@pytest.mark.parametrize(
    ("screen", "aspect", "margin"),
    [(screen, aspect, 0) for screen, aspect in ACCEPTED]
    + [((1280, 720), FOUR_THREE, 12), ((1920, 1080), NES, 12)],
)
def test_no_tag_or_patch_touches_the_picture(screen, aspect, margin) -> None:
    picture = centred(screen, aspect)
    layout = bar_layout(screen, picture, margin)

    for marker in layout.markers.values():
        left, top, right, bottom = _patch(marker)
        in_left_bar = right <= picture[0]
        in_right_bar = left >= picture[0] + picture[2]
        assert in_left_bar or in_right_bar, marker
        assert left >= margin and top >= margin
        assert right <= screen[0] - margin and bottom <= screen[1] - margin


@pytest.mark.parametrize(("screen", "aspect"), ACCEPTED)
def test_patches_do_not_overlap_each_other(screen, aspect) -> None:
    layout = bar_layout(screen, centred(screen, aspect))
    patches = [_patch(marker) for marker in layout.markers.values()]

    for i, a in enumerate(patches):
        for b in patches[i + 1 :]:
            overlap = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
            assert not overlap, (a, b)


def test_numbering_matches_the_printed_layout() -> None:
    layout = bar_layout((1280, 720), centred((1280, 720), FOUR_THREE))
    at = {m: (layout.markers[m].x_mm, layout.markers[m].y_mm) for m in BAR_MARKER_IDS}

    assert set(layout.markers) == {0, 1, 2, 3, 5, 7}
    # 0-3 clockwise from top-left; 7 left middle, 5 right middle.
    assert at[0][0] == at[3][0] == at[7][0] < 640 < at[1][0] == at[2][0] == at[5][0]
    assert at[0][1] == at[1][1] < at[7][1] == at[5][1] < at[3][1] == at[2][1]


def test_tags_are_as_large_as_the_bar_allows() -> None:
    picture = centred((1280, 720), FOUR_THREE)  # bars of 160px
    tag = bar_layout((1280, 720), picture).markers[0].size_mm

    assert tag + 2 * quiet_patch_px(round(tag)) <= 160
    assert (tag + 1) + 2 * quiet_patch_px(round(tag + 1)) > 160


def test_layout_is_in_screen_pixels() -> None:
    layout = bar_layout((1280, 720), centred((1280, 720), FOUR_THREE))

    assert layout.screen_size_mm == (1280.0, 720.0)


def test_narrow_bars_are_refused_with_the_resolution_and_the_width() -> None:
    screen = (1000, 768)
    picture = centred(screen, NES)  # bars of 32px

    with pytest.raises(OverlayGeometryError) as raised:
        bar_layout(screen, picture)

    message = str(raised.value)
    assert "1000x768" in message
    assert f"{min_bar_px(screen)}px" in message


def test_no_bars_at_all_is_refused() -> None:
    with pytest.raises(OverlayGeometryError):
        bar_layout((800, 600), (0, 0, 800, 600))


def test_a_margin_that_eats_the_bar_is_refused() -> None:
    with pytest.raises(OverlayGeometryError):
        bar_layout((1280, 720), centred((1280, 720), FOUR_THREE), margin_px=70)


# --- what is drawn ---------------------------------------------------


@pytest.mark.parametrize(("screen", "aspect"), ACCEPTED[:4])
def test_drawn_tags_decode_where_the_layout_puts_them(screen, aspect) -> None:
    layout = bar_layout(screen, centred(screen, aspect))
    image = render_layout(screen, layout)

    found = {m.marker_id: m.corners[0] for m in detect_markers(image)}

    assert set(found) == set(BAR_MARKER_IDS)
    for marker_id, (x, y) in found.items():
        marker = layout.markers[marker_id]
        assert abs(x - marker.x_mm) <= 1.5 and abs(y - marker.y_mm) <= 1.5


def test_nothing_is_drawn_in_the_picture() -> None:
    screen = (1280, 720)
    x, _, width, _ = centred(screen, FOUR_THREE)

    image = render_layout(screen, bar_layout(screen, centred(screen, FOUR_THREE)))

    assert not image[:, x : x + width].any()


# --- a camera on the screen aims where it points ---------------------

CAMERA = (1280, 960)
SCALE = 0.45


def _camera_view(image, target) -> np.ndarray:
    """What a camera sees when its centre points at `target` on the screen:
    scaled, slightly rotated and in perspective, the rest of the room grey."""
    to_target = np.array(
        [[1, 0, -target[0]], [0, 1, -target[1]], [0, 0, 1]], dtype=np.float64
    )
    angle = np.radians(4)
    lens = np.array(
        [
            [SCALE * np.cos(angle), -SCALE * np.sin(angle), 0],
            [SCALE * np.sin(angle), SCALE * np.cos(angle), 0],
            [0.00008, -0.00005, 1],
        ]
    )
    to_centre = np.array(
        [[1, 0, CAMERA[0] / 2], [0, 1, CAMERA[1] / 2], [0, 0, 1]], dtype=np.float64
    )
    return cv2.warpPerspective(
        image, to_centre @ lens @ to_target, CAMERA, borderValue=100
    )


@pytest.mark.parametrize("where", ["centre", "top-left", "top-right", "bottom-right"])
def test_aim_at_the_picture_is_recovered(where) -> None:
    screen = (1280, 720)
    x, _, width, height = centred(screen, FOUR_THREE)
    layout = bar_layout(screen, (x, 0, width, height))
    image = render_layout(screen, layout)
    image[:, x : x + width] = 128  # mid-grey stands in for a game
    # Inside the pipeline's edge margin, which applies here as everywhere.
    inset = 0.03 * height
    target = {
        "centre": (x + width / 2, height / 2),
        "top-left": (x + inset, inset),
        "top-right": (x + width - inset, inset),
        "bottom-right": (x + width - inset, height - inset),
    }[where]

    pipeline = AimPipeline(layout, FakeCursorBackend(), tracking=False)
    result = pipeline.process_frame(_camera_view(image, target))

    assert result.outcome is FrameOutcome.SOLVED
    assert result.markers_mapped == 6
    assert result.position[0] == pytest.approx(target[0] / screen[0], abs=0.003)
    assert result.position[1] == pytest.approx(target[1] / screen[1], abs=0.003)
