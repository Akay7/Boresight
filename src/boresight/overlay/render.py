"""Painting the tags.

Produces a plain image plus the rectangles it occupies. Deliberately
knows nothing about windows, toolkits or display servers -- a backend
takes what this returns and puts it on screen, and a test takes the same
thing and runs it through the real detector.

Tags come from `markers.marker_grid`, the same function the printed
sheet uses, so the two substrates cannot drift onto different bit
patterns.
"""

from __future__ import annotations

import cv2
import numpy as np

from boresight.markers import marker_grid
from boresight.overlay.layout import (
    QUIET_PATCH_FRACTION,
    default_inset_px,
    default_tag_px,
    tag_positions_px,
)

# Straight black and white. The detector thresholds and follows
# contours, so contrast is the only thing that matters here and there is
# no reason to spend any of it on styling.
TAG_DARK = 0
TAG_LIGHT = 255


def patch_margin_px(tag_px: int) -> int:
    return max(1, round(tag_px * QUIET_PATCH_FRACTION))


def tag_image(marker_id: int, tag_px: int) -> np.ndarray:
    """One tag as a greyscale image, `tag_px` on a side.

    `marker_grid` already includes the dictionary's 1-cell quiet border,
    so the grid is 6x6 for DICT_4X4_50's 4x4 payload. Scaled with
    nearest-neighbour: a bit cell is a hard square, and smoothing here
    would be aliasing the detector then has to undo. Interpolation cost
    the rendered fixtures five of eight markers once already.
    """
    grid = marker_grid(marker_id)
    return cv2.resize(grid, (tag_px, tag_px), interpolation=cv2.INTER_NEAREST)


def render_overlay(
    screen_px: tuple[int, int],
    tag_px: int | None = None,
    inset_px: int | None = None,
) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    """Draw every tag for `screen_px`.

    Returns the full-screen greyscale image and the list of opaque
    rectangles `(x, y, w, h)` it actually painted. The rectangles are
    what a backend shows: everything outside them stays untouched, so
    the overlay occludes only the patches and not the whole display.
    """
    tag_px = default_tag_px(screen_px) if tag_px is None else tag_px
    inset_px = default_inset_px(tag_px) if inset_px is None else inset_px
    margin = patch_margin_px(tag_px)

    width, height = screen_px
    canvas = np.zeros((height, width), dtype=np.uint8)
    rectangles: list[tuple[int, int, int, int]] = []

    for marker_id, (x, y) in tag_positions_px(screen_px, tag_px, inset_px).items():
        # The quiet-zone patch is painted opaque rather than composited,
        # so detection does not depend on what the application beneath
        # happens to be showing. A tag blended over bright game content
        # has no reliable edge, and busy content beside one manufactures
        # false quad candidates.
        patch_x = max(0, x - margin)
        patch_y = max(0, y - margin)
        patch_right = min(width, x + tag_px + margin)
        patch_bottom = min(height, y + tag_px + margin)
        canvas[patch_y:patch_bottom, patch_x:patch_right] = TAG_LIGHT

        canvas[y : y + tag_px, x : x + tag_px] = tag_image(marker_id, tag_px)

        rectangles.append(
            (patch_x, patch_y, patch_right - patch_x, patch_bottom - patch_y)
        )

    return canvas, rectangles


def target_image(size_px: int) -> np.ndarray:
    """A zeroing target, `size_px` on a side (rounded up to odd).

    Drawn like a tag -- an opaque light patch, dark marks -- so it reads
    over any content. Rings and a crosshair on a centre dot: a point to
    put the sights on, not an area. Odd-sized so there is a centre pixel
    for the position the server asked for to land on.
    """
    size = max(9, size_px | 1)
    centre = size // 2
    stroke = max(1, size // 24)
    image = np.full((size, size), TAG_LIGHT, dtype=np.uint8)
    for radius in (centre - stroke, (centre * 2) // 3, centre // 3):
        cv2.circle(image, (centre, centre), radius, TAG_DARK, stroke)
    cv2.line(image, (centre, 0), (centre, size - 1), TAG_DARK, 1)
    cv2.line(image, (0, centre), (size - 1, centre), TAG_DARK, 1)
    cv2.circle(image, (centre, centre), stroke, TAG_DARK, -1)
    return image
