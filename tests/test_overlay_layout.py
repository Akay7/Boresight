"""The derived on-screen layout.

Pure geometry -- no display, no toolkit, no rendering. These run
everywhere, including on a machine with no graphical session and the
overlay extra not installed.

The property worth reading first is
`test_the_assumed_scale_does_not_reach_the_aim_point`: it is what lets
the overlay ignore a display's reported physical size, which is
frequently wrong or absent.
"""

from __future__ import annotations

import numpy as np
import pytest

from boresight.detect import DetectedMarker
from boresight.inject import FakeCursorBackend
from boresight.marker_map import MarkerMap
from boresight.overlay.layout import (
    DEFAULT_TAG_FRACTION,
    OverlayGeometryError,
    default_inset_px,
    default_tag_px,
    overlay_layout,
    tag_positions_px,
)
from boresight.pipeline import AimPipeline, FrameOutcome

SCREEN = (1920, 1080)
IMAGE_SIZE = (1280, 720)


# --- Placement --------------------------------------------------------


def test_the_layout_has_the_same_eight_ids_as_the_printed_one() -> None:
    """Same numbering as config/markers.toml, so a camera, a file and
    this function all mean the same thing by "marker 5"."""
    layout = overlay_layout(SCREEN)

    assert set(layout.markers) == set(range(8))


def test_corners_and_midpoints_land_where_they_belong() -> None:
    positions = tag_positions_px(SCREEN, tag_px=80, inset_px=20)
    width, height = SCREEN

    assert positions[0] == (20, 20)
    assert positions[1] == (width - 100, 20)
    assert positions[2] == (width - 100, height - 100)
    assert positions[3] == (20, height - 100)
    # Midpoints are centred on their edge, not merely somewhere along it.
    assert positions[4] == (round((width - 80) / 2), 20)
    assert positions[6] == (round((width - 80) / 2), height - 100)
    assert positions[5] == (width - 100, round((height - 80) / 2))
    assert positions[7] == (20, round((height - 80) / 2))


def test_every_tag_lies_inside_the_panel() -> None:
    """The opposite of the printed layout, whose tags are all outside it.
    This is what relieves the close-range dropout: at 1400mm the printed
    bezel tags left the frustum entirely."""
    layout = overlay_layout(SCREEN)
    width, height = layout.screen_size_mm

    for marker in layout.markers.values():
        assert marker.x_mm >= 0
        assert marker.y_mm >= 0
        assert marker.x_mm + marker.size_mm <= width
        assert marker.y_mm + marker.size_mm <= height


def test_no_two_tags_overlap() -> None:
    """An overlap shows the detector one malformed quad rather than two
    markers, so it costs both."""
    layout = overlay_layout(SCREEN)
    boxes = [
        (m.x_mm, m.y_mm, m.x_mm + m.size_mm, m.y_mm + m.size_mm)
        for m in layout.markers.values()
    ]

    for index, (ax0, ay0, ax1, ay1) in enumerate(boxes):
        for bx0, by0, bx1, by1 in boxes[index + 1 :]:
            separated = ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0
            assert separated, "two tags overlap"


def test_the_default_tag_size_follows_the_sizing_table() -> None:
    """~3px per bit cell over a 6x6 grid at playing distance. Pinned so
    a casual change has to acknowledge the derivation."""
    assert default_tag_px(SCREEN) == round(1920 * DEFAULT_TAG_FRACTION)
    assert default_tag_px((1280, 720)) == round(1280 * DEFAULT_TAG_FRACTION)


def test_the_default_inset_leaves_room_for_the_quiet_patch() -> None:
    """The tag is held off the screen edge by at least the patch margin,
    or the patch would be clipped and the tag would lose its quiet zone
    on that side."""
    tag = default_tag_px(SCREEN)

    assert default_inset_px(tag) >= 1
    assert overlay_layout(SCREEN).markers[0].x_mm >= default_inset_px(tag)


def test_a_custom_tag_and_inset_are_honoured() -> None:
    layout = overlay_layout(SCREEN, tag_px=120, inset_px=40)

    assert layout.markers[0].size_mm == 120
    assert (layout.markers[0].x_mm, layout.markers[0].y_mm) == (40, 40)


# --- Geometry that cannot work ---------------------------------------


def test_a_tag_too_large_for_the_screen_is_rejected() -> None:
    with pytest.raises(OverlayGeometryError, match="does not fit"):
        overlay_layout((200, 200), tag_px=300)


def test_a_tag_that_would_collide_with_the_midpoint_is_rejected() -> None:
    """Silently overlapping tags would be far worse than refusing."""
    with pytest.raises(OverlayGeometryError, match="overlaps"):
        overlay_layout((800, 600), tag_px=380, inset_px=10)


@pytest.mark.parametrize(
    "kwargs", [{"tag_px": 0}, {"tag_px": -10}, {"inset_px": -1}, {"scale": 0}]
)
def test_nonsense_parameters_are_rejected(kwargs: dict) -> None:
    with pytest.raises(OverlayGeometryError):
        overlay_layout(SCREEN, **kwargs)


def test_a_non_positive_screen_is_rejected() -> None:
    with pytest.raises(OverlayGeometryError, match="screen size must be positive"):
        overlay_layout((0, 1080))


# --- Scale ------------------------------------------------------------


def _detections_for(layout: MarkerMap, aim_fraction: tuple[float, float]) -> list:
    """Synthetic detections placing `aim_fraction` of the panel at the
    image centre, via a similarity transform in layout units."""
    width, height = layout.screen_size_mm
    centre = (width * aim_fraction[0], height * aim_fraction[1])
    # Fit the whole layout comfortably inside the frame whatever the
    # layout's units happen to be.
    scale_px_per_unit = IMAGE_SIZE[0] * 0.5 / width

    detected = []
    for marker_id, marker in sorted(layout.markers.items()):
        corners = [
            [
                scale_px_per_unit * (x - centre[0]) + IMAGE_SIZE[0] / 2.0,
                scale_px_per_unit * (y - centre[1]) + IMAGE_SIZE[1] / 2.0,
            ]
            for x, y in marker.corners_mm()
        ]
        detected.append(
            DetectedMarker(
                marker_id=marker_id, corners=np.array(corners, dtype=np.float32)
            )
        )
    return detected


def _aim_at(layout: MarkerMap, aim_fraction: tuple[float, float]):
    backend = FakeCursorBackend()
    detected = _detections_for(layout, aim_fraction)
    pipeline = AimPipeline(layout, backend, detector=lambda _frame: detected)
    frame = np.zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=np.uint8)
    return pipeline.process_frame(frame)


@pytest.mark.parametrize("aim", [(0.5, 0.5), (0.25, 0.75), (0.1, 0.9)])
def test_the_assumed_scale_does_not_reach_the_aim_point(aim: tuple) -> None:
    """The property the whole units decision rests on.

    Positions and screen size are both `pixels * scale`, and the
    pipeline emits `aim_mm / screen_mm`, so the scale cancels. This is
    why the overlay can ignore a display's reported physical size --
    which EDID often gets wrong or omits entirely.
    """
    pixels = _aim_at(overlay_layout(SCREEN, scale=1.0), aim)
    millimetres = _aim_at(overlay_layout(SCREEN, scale=0.2768), aim)
    absurd = _aim_at(overlay_layout(SCREEN, scale=1234.5), aim)

    assert pixels.position == pytest.approx(millimetres.position, abs=1e-6)
    assert pixels.position == pytest.approx(absurd.position, abs=1e-6)
    assert pixels.position == pytest.approx(aim, abs=1e-6)


def test_the_scale_is_uniform_so_the_aspect_ratio_survives() -> None:
    """A per-axis scale would bend the homography. One factor for both
    keeps a square tag square."""
    layout = overlay_layout(SCREEN, scale=0.5)
    width, height = layout.screen_size_mm

    assert width / height == pytest.approx(SCREEN[0] / SCREEN[1])
    for marker in layout.markers.values():
        assert marker.size_mm == pytest.approx(default_tag_px(SCREEN) * 0.5)


# --- Interchangeability with a loaded layout -------------------------


def test_a_derived_layout_drives_the_pipeline_unchanged() -> None:
    """No special handling versus one loaded from a file: same type,
    same units convention, same consumer."""
    layout = overlay_layout(SCREEN)

    result = _aim_at(layout, (0.5, 0.5))

    assert result.outcome is FrameOutcome.SOLVED
    assert result.markers_mapped == 8
    assert result.position == pytest.approx((0.5, 0.5), abs=1e-6)
    assert result.aim_point_inside_hull


def test_almost_the_whole_panel_is_inside_the_correspondence_hull() -> None:
    """The hull is bounded by the tags' outer corners, so it covers the
    panel except a border one inset wide -- 22px of 1920 at the default
    size. Aim anywhere but that sliver and the solve is interpolating.

    The printed layout cannot say this: its tags sit outside the panel,
    so the hull is larger, but close range loses them entirely.
    """
    layout = overlay_layout(SCREEN)
    inset = default_inset_px(default_tag_px(SCREEN))
    # A pixel inside the boundary rather than exactly on it: the
    # boundary itself is a float coin-toss and not what this asserts.
    margin = ((inset + 1) / SCREEN[0], (inset + 1) / SCREEN[1])

    for aim in [
        (margin[0], margin[1]),
        (0.5, 0.5),
        (1 - margin[0], 1 - margin[1]),
    ]:
        assert _aim_at(layout, aim).aim_point_inside_hull, aim


def test_even_the_extreme_corner_is_barely_outside_the_hull() -> None:
    """Past that sliver the solve is flagged, correctly -- but by a hair.

    The distance is Euclidean to the nearest hull point, and at the
    screen corner the nearest point is the hull's vertex at
    (inset, inset), so it is inset*sqrt(2), not inset. Bounded here by
    one tag edge, which is generous and still nothing beside the
    printed layout's measured worst case: a sparse view extrapolating
    2037mm on a 1220mm panel.
    """
    layout = overlay_layout(SCREEN)
    tag = default_tag_px(SCREEN)

    corner = _aim_at(layout, (0.0, 0.0))

    assert not corner.aim_point_inside_hull
    assert corner.aim_point_hull_distance_mm > -tag
