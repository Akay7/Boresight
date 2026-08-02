"""Where the on-screen tags go.

One pure function, called by both the renderer and the solver. That is
the whole point: a file or a message between them would introduce a
moment where the drawn layout and the solved layout can differ -- a
stale file, a restart on another monitor, two processes racing. With a
single computation over the same geometry they cannot disagree, which
makes the guarantee structural rather than procedural.
"""

from __future__ import annotations

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
) -> MarkerMap:
    """The layout for tags drawn on a display of `screen_px`.

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

    tag_px = default_tag_px(screen_px) if tag_px is None else tag_px
    inset_px = default_inset_px(tag_px) if inset_px is None else inset_px
    _validate(screen_px, tag_px, inset_px)

    markers = {
        marker_id: Marker(
            marker_id=marker_id,
            x_mm=x * scale,
            y_mm=y * scale,
            size_mm=tag_px * scale,
        )
        for marker_id, (x, y) in tag_positions_px(screen_px, tag_px, inset_px).items()
    }
    return MarkerMap(
        screen_size_mm=(screen_px[0] * scale, screen_px[1] * scale),
        markers=markers,
    )
