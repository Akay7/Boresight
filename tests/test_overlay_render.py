"""What the overlay paints, run back through the real detector.

No window and no toolkit -- `render_overlay` returns a plain image, so
the thing that will actually be on screen can be handed to the same
`detect_markers` the camera path uses. If the overlay draws something
its own detector cannot read, that is worth knowing here rather than
from a phone pointed at a television.
"""

from __future__ import annotations

import numpy as np
import pytest

from boresight.detect import detect_markers
from boresight.overlay.layout import (
    default_inset_px,
    default_tag_px,
    overlay_layout,
    tag_positions_px,
)
from boresight.overlay.render import (
    TAG_LIGHT,
    patch_margin_px,
    render_overlay,
    tag_image,
)

SCREEN = (1920, 1080)


@pytest.fixture(scope="module")
def rendered() -> tuple[np.ndarray, list]:
    return render_overlay(SCREEN)


# --- The detector can read it ----------------------------------------


def test_every_rendered_tag_decodes(rendered) -> None:
    canvas, _rectangles = rendered

    detected = detect_markers(canvas)

    assert {marker.marker_id for marker in detected} == set(range(8))


def test_each_tag_decodes_at_the_position_the_layout_claims(rendered) -> None:
    """Closes the loop between the two halves of the design: the tag the
    detector finds at a place must be the tag the solver expects there.
    A transposed or mis-ordered placement would pass the decode test
    above and fail this one."""
    canvas, _rectangles = rendered
    expected = tag_positions_px(
        SCREEN, default_tag_px(SCREEN), default_inset_px(default_tag_px(SCREEN))
    )

    for marker in detect_markers(canvas):
        top_left = marker.corners[0]
        want = expected[marker.marker_id]
        assert top_left[0] == pytest.approx(want[0], abs=2.0)
        assert top_left[1] == pytest.approx(want[1], abs=2.0)


def test_the_rendered_corners_match_the_solved_layout(rendered) -> None:
    """The renderer and the layout function agree to within detection
    noise -- the requirement that they 'cannot disagree', checked
    against pixels rather than asserted."""
    canvas, _rectangles = rendered
    layout = overlay_layout(SCREEN)

    for marker in detect_markers(canvas):
        claimed = layout.corners_mm(marker.marker_id)
        for (want_x, want_y), (got_x, got_y) in zip(
            claimed, marker.corners, strict=True
        ):
            assert got_x == pytest.approx(want_x, abs=2.0)
            assert got_y == pytest.approx(want_y, abs=2.0)


# --- Drawn opaquely, not composited ----------------------------------


def test_each_tag_sits_on_an_opaque_patch(rendered) -> None:
    """Detection must not depend on what the application beneath happens
    to be showing."""
    canvas, _rectangles = rendered
    tag = default_tag_px(SCREEN)
    inset = default_inset_px(tag)
    margin = patch_margin_px(tag)

    for x, y in tag_positions_px(SCREEN, tag, inset).values():
        # A ring just outside the tag, inside the patch, is solid light.
        above = canvas[y - margin : y, x : x + tag]
        left = canvas[y : y + tag, x - margin : x]
        assert np.all(above == TAG_LIGHT)
        assert np.all(left == TAG_LIGHT)


def test_the_overlay_leaves_the_rest_of_the_screen_alone(rendered) -> None:
    """The patches are what a backend shows; everything else stays
    untouched, so the overlay occludes a few percent of the picture
    rather than all of it."""
    canvas, rectangles = rendered

    painted = np.zeros(canvas.shape, dtype=bool)
    for x, y, w, h in rectangles:
        painted[y : y + h, x : x + w] = True

    assert not painted.all(), "the overlay would cover the whole screen"
    assert painted.mean() < 0.10, "the overlay occludes more than a tenth"
    # Nothing was drawn outside the rectangles the backend is told about.
    assert np.all(canvas[~painted] == 0)


def test_the_reported_rectangles_cover_every_tag(rendered) -> None:
    canvas, rectangles = rendered
    tag = default_tag_px(SCREEN)
    inset = default_inset_px(tag)

    assert len(rectangles) == 8
    for x, y in tag_positions_px(SCREEN, tag, inset).values():
        assert any(
            rx <= x and ry <= y and rx + rw >= x + tag and ry + rh >= y + tag
            for rx, ry, rw, rh in rectangles
        ), "a tag is not inside any reported rectangle"


# --- Tag bitmaps ------------------------------------------------------


def test_a_tag_is_scaled_without_smoothing() -> None:
    """A bit cell is a hard square. Interpolation here cost the rendered
    video fixtures five of their eight markers once already."""
    image = tag_image(0, 120)

    assert image.shape == (120, 120)
    assert set(np.unique(image)) <= {0, 255}


def test_tags_come_from_the_same_source_as_the_printed_sheet() -> None:
    """Two substrates, one bit pattern. If these could diverge, a tag
    printed on paper and the same ID drawn on screen would decode as
    different markers."""
    from boresight.markers import marker_grid

    for marker_id in range(8):
        scaled = tag_image(marker_id, 6)
        assert np.array_equal(scaled, marker_grid(marker_id))


# --- Smaller screens --------------------------------------------------


@pytest.mark.parametrize("screen", [(1280, 720), (1920, 1200), (2560, 1440)])
def test_common_screen_sizes_render_and_decode(screen: tuple[int, int]) -> None:
    canvas, _rectangles = render_overlay(screen)

    detected = detect_markers(canvas)

    assert {marker.marker_id for marker in detected} == set(range(8))
