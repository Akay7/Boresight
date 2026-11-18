"""Where the on-screen tags go.

One pure function, called by both the renderer and the solver. That is
the whole point: a file or a message between them would introduce a
moment where the drawn layout and the solved layout can differ -- a
stale file, a restart on another monitor, two processes racing. With a
single computation over the same geometry they cannot disagree, which
makes the guarantee structural rather than procedural.
"""

from __future__ import annotations

import math
import re

from boresight.marker_map import Marker, MarkerMap

# Tag edge as a fraction of screen width.
#
# Derived from README's "Sizing" table rather than taste. Decode needs
# ~3px per bit cell over a 6x6 grid, so ~20px across the tag in the
# camera image. A camera framing the display typically has it filling
# roughly 60% of frame width, so at 1280px across that is 20/(0.6*1280)
# = 2.6% of screen width at the absolute floor. This is a little under
# double that, which puts a tag around 55px in frame -- comfortable
# headroom for blur, angle and a camera further back.
DEFAULT_TAG_FRACTION = 0.045

# Opaque margin around each tag, as a fraction of its edge. Matches the
# printed sheet's margin so both substrates present the detector with
# the same quiet zone. The tag is inset from the screen edge by at
# least this much, or the patch would be clipped off-screen and the
# tag would lose the quiet zone on that side.
QUIET_PATCH_FRACTION = 0.25


class OverlayGeometryError(ValueError):
    """Raised when the requested tags cannot fit the display."""


def default_tag_px(screen_px: tuple[int, int]) -> int:
    return max(1, round(screen_px[0] * DEFAULT_TAG_FRACTION))


def default_inset_px(tag_px: int) -> int:
    return round(tag_px * QUIET_PATCH_FRACTION)


def tag_positions_px(
    screen_px: tuple[int, int], tag_px: int, inset_px: int
) -> dict[int, tuple[int, int]]:
    """Top-left pixel of each tag, keyed by marker ID.

    Numbered exactly as the printed reference layout: 0-3 are corners
    clockwise from top-left, 4-7 are edge midpoints clockwise from top.
    Keeping the two layouts on one numbering means a camera, a
    markers.toml and this function all mean the same thing by "marker 5".
    """
    width, height = screen_px
    left = inset_px
    right = width - inset_px - tag_px
    top = inset_px
    bottom = height - inset_px - tag_px
    mid_x = round((width - tag_px) / 2)
    mid_y = round((height - tag_px) / 2)

    return {
        0: (left, top),
        1: (right, top),
        2: (right, bottom),
        3: (left, bottom),
        4: (mid_x, top),
        5: (right, mid_y),
        6: (mid_x, bottom),
        7: (left, mid_y),
    }


def _validate(screen_px: tuple[int, int], tag_px: int, inset_px: int) -> None:
    width, height = screen_px
    if width <= 0 or height <= 0:
        raise OverlayGeometryError(f"screen size must be positive, got {screen_px}")
    if tag_px <= 0:
        raise OverlayGeometryError(f"tag size must be positive, got {tag_px}")
    if inset_px < 0:
        raise OverlayGeometryError(f"inset must not be negative, got {inset_px}")

    for axis, span in (("width", width), ("height", height)):
        if inset_px + tag_px > span:
            raise OverlayGeometryError(
                f"a {tag_px}px tag inset {inset_px}px does not fit the "
                f"{span}px screen {axis}"
            )

    # A corner tag must clear the edge midpoint tag, or two markers
    # overlap and the detector sees one malformed quad instead of two.
    if inset_px + tag_px > (width - tag_px) / 2:
        raise OverlayGeometryError(
            f"a {tag_px}px tag inset {inset_px}px overlaps the top/bottom "
            f"midpoint tag on a {width}px-wide screen; use a smaller tag"
        )
    if inset_px + tag_px > (height - tag_px) / 2:
        raise OverlayGeometryError(
            f"a {tag_px}px tag inset {inset_px}px overlaps the left/right "
            f"midpoint tag on a {height}px-tall screen; use a smaller tag"
        )


def overlay_layout(
    screen_px: tuple[int, int],
    tag_px: int | None = None,
    inset_px: int | None = None,
    scale: float = 1.0,
    area_px: tuple[int, int, int, int] | None = None,
) -> MarkerMap:
    """The layout for tags drawn on a display of `screen_px`.

    `area_px` is `(x, y, width, height)`: the region of the display the
    tags may occupy, defaulting to all of it. It exists because desktop
    panels reserve screen edges -- a KDE panel takes 46px off the bottom
    -- and tags drawn under one are invisible to the camera. The overlay
    passes the compositor's reported available area.

    Marker positions are returned in **full-screen** coordinates
    regardless of the area, and `screen_size` is always the full
    display. That is not cosmetic: the pipeline emits
    `aim_mm / screen_mm` and the cursor backend maps that onto the whole
    display, so normalizing against anything smaller would put the
    cursor at the wrong place by exactly the panel's share of the
    screen.

    `scale` converts pixels to the layout's nominal millimetres. It does
    not have to be correct, and deliberately defaults to 1.0. The
    pipeline emits `aim_mm / screen_mm`; if every marker position and
    the screen size are all `pixels * scale`, the scale cancels exactly.
    What must not happen is a different scale per axis, which would
    distort the aspect ratio and bend the homography -- so one factor is
    applied to both, rather than reading a display's reported physical
    dimensions, which are frequently wrong or absent in EDID.
    """
    if scale <= 0:
        raise OverlayGeometryError(f"scale must be positive, got {scale}")
    if screen_px[0] <= 0 or screen_px[1] <= 0:
        # Checked before the area is derived, so a nonsense screen is
        # reported as such rather than as a nonsense area derived from it.
        raise OverlayGeometryError(f"screen size must be positive, got {screen_px}")

    area_x, area_y, area_w, area_h = (0, 0, *screen_px) if area_px is None else area_px
    if area_w <= 0 or area_h <= 0:
        raise OverlayGeometryError(f"area must be positive, got {area_px}")
    if (
        area_x < 0
        or area_y < 0
        or area_x + area_w > screen_px[0]
        or (area_y + area_h > screen_px[1])
    ):
        raise OverlayGeometryError(
            f"area {area_px} does not fit a {screen_px[0]}x{screen_px[1]} screen"
        )

    area_size = (area_w, area_h)
    tag_px = default_tag_px(area_size) if tag_px is None else tag_px
    inset_px = default_inset_px(tag_px) if inset_px is None else inset_px
    _validate(area_size, tag_px, inset_px)

    markers = {
        marker_id: Marker(
            marker_id=marker_id,
            # Placed within the area, expressed against the whole screen.
            x_mm=(area_x + x) * scale,
            y_mm=(area_y + y) * scale,
            size_mm=tag_px * scale,
        )
        for marker_id, (x, y) in tag_positions_px(area_size, tag_px, inset_px).items()
    }
    return MarkerMap(
        screen_size_mm=(screen_px[0] * scale, screen_px[1] * scale),
        markers=markers,
    )


# The smallest tag worth drawing, as a fraction of screen width: the
# "~20px in frame" floor `DEFAULT_TAG_FRACTION` is derived from, before
# its headroom is added.
MIN_TAG_FRACTION = 0.026

# Six of the eight: the top and bottom midpoints (4 and 6) would sit over
# the picture between the bars.
BAR_MARKER_IDS = (0, 1, 2, 3, 5, 7)


def quiet_patch_px(tag_px: int) -> int:
    """The opaque margin painted around a tag of `tag_px`."""
    return max(1, round(tag_px * QUIET_PATCH_FRACTION))


def min_bar_px(screen_px: tuple[int, int], margin_px: int = 0) -> int:
    """The narrowest side bar that holds a tag of the minimum size."""
    tag = max(1, math.ceil(screen_px[0] * MIN_TAG_FRACTION))
    return tag + 2 * quiet_patch_px(tag) + 2 * margin_px


def bar_layout(
    screen_px: tuple[int, int],
    viewport: tuple[int, int, int, int],
    margin_px: int = 0,
) -> MarkerMap:
    """The layout for tags drawn in the bars beside a centred picture.

    `viewport` is `(x, y, width, height)`: the picture, which no tag or
    quiet-zone patch may touch. The tags are 0-3 at the corners of the
    bars and 7 and 5 at the middle of the left and right bar, numbered as
    the printed layout is. Each is as large as the narrower bar allows,
    patch and `margin_px` included, and three must stack in the height.

    Positions are in screen pixels with a scale of 1.0, against the whole
    screen, exactly as `overlay_layout` returns them; the scale cancels
    under the pipeline's normalization. Raises `OverlayGeometryError`,
    naming the screen and the bar width it would need, when the bars are
    too narrow for a detectable tag.
    """
    width, height = screen_px
    if width <= 0 or height <= 0:
        raise OverlayGeometryError(f"screen size must be positive, got {screen_px}")
    if margin_px < 0:
        raise OverlayGeometryError(f"margin must not be negative, got {margin_px}")
    view_x, view_y, view_w, view_h = viewport
    if view_x < 0 or view_w <= 0 or view_x + view_w > width:
        raise OverlayGeometryError(
            f"viewport {viewport} does not fit a {width}x{height} screen"
        )
    left_bar = view_x
    right_bar = width - (view_x + view_w)
    bar = min(left_bar, right_bar)

    # Largest tag whose patch fits the bar across and three patches down.
    room_across = bar - 2 * margin_px
    room_down = (height - 2 * margin_px) // 3
    tag = int(min(room_across, room_down) / (1 + 2 * QUIET_PATCH_FRACTION)) + 1
    while tag > 0 and (
        tag + 2 * quiet_patch_px(tag) > room_across
        or tag + 2 * quiet_patch_px(tag) > room_down
    ):
        tag -= 1
    if tag < width * MIN_TAG_FRACTION:
        raise OverlayGeometryError(
            f"a {width}x{height} output leaves {bar}px bars beside the picture; "
            f"tags need bars at least {min_bar_px(screen_px, margin_px)}px wide"
        )

    patch = quiet_patch_px(tag)
    # Patches flush with the outer edge, any spare pixels toward the
    # picture: a sliver of black a pixel wide between a patch and the edge
    # of the frame is enough to stop a tag decoding.
    left_x = margin_px + patch
    right_x = width - margin_px - patch - tag
    top_y = margin_px + patch
    bottom_y = height - margin_px - patch - tag
    mid_y = round((height - tag) / 2)
    positions = {
        0: (left_x, top_y),
        1: (right_x, top_y),
        2: (right_x, bottom_y),
        3: (left_x, bottom_y),
        5: (right_x, mid_y),
        7: (left_x, mid_y),
    }
    return MarkerMap(
        screen_size_mm=(float(width), float(height)),
        markers={
            marker_id: Marker(
                marker_id=marker_id, x_mm=float(x), y_mm=float(y), size_mm=float(tag)
            )
            for marker_id, (x, y) in positions.items()
        },
    )


_ASPECT = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")


def parse_picture_aspect(text: str) -> float:
    """`"4:3"` -> 1.333...; raises `OverlayGeometryError` for anything else."""
    match = _ASPECT.match(text)
    if not match or int(match.group(1)) == 0 or int(match.group(2)) == 0:
        raise OverlayGeometryError(
            f"a picture aspect is WIDTH:HEIGHT, like 4:3 or 8:7, not {text!r}"
        )
    return int(match.group(1)) / int(match.group(2))


def centred_picture(
    screen_px: tuple[int, int], aspect: float
) -> tuple[int, int, int, int]:
    """`(x, y, width, height)` of a full-height picture of `aspect`, centred
    on the screen, as an emulator in windowed full screen shows it. Its
    width takes the screen width's parity, so the two bars are equal."""
    width, height = screen_px
    picture_w = min(width, round(height * aspect))
    picture_w -= (width - picture_w) % 2
    return ((width - picture_w) // 2, 0, picture_w, height)


def picture_bar_layout(
    screen_px: tuple[int, int], picture_aspect: str, margin_px: int = 0
) -> MarkerMap:
    """The tags beside a centred picture of `picture_aspect` ("4:3"). The
    overlay draws this and the solver is given this, from the same three
    numbers the overlay reports."""
    aspect = parse_picture_aspect(picture_aspect)
    return bar_layout(screen_px, centred_picture(screen_px, aspect), margin_px)
