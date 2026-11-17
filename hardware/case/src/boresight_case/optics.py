"""The camera's view out of the muzzle, as a solid that no part may enter."""

from __future__ import annotations

import math
from collections.abc import Sequence

from build123d import Part, Plane, Rectangle, loft

from boresight_case.geom import X, Z, unit, v
from boresight_case.vendor import fov_half_angles

# Added to each half-angle, so a part that grazes the frame's edge on paper
# stays out of it on a real print.
FOV_MARGIN_DEG = 3.0
# The entrance pupil sits about this far behind the lens front, and is
# about this wide in radius, for every lens the kits carry.
PUPIL_BEHIND = 1.0
PUPIL_RADIUS = 1.3


def view_frustum(
    camera: str,
    lens_front: Sequence[float],
    length: float,
    axis: Sequence[float] = X,
    up: Sequence[float] = Z,
    margin_deg: float = FOV_MARGIN_DEG,
) -> Part:
    """The view of `camera`, from its lens front plane out to `length` beyond
    it, widened by `margin_deg` each way. Its horizontal angle opens across
    axis x up, its vertical angle along `up`."""
    th, tv = fov_half_angles(camera)
    th += math.radians(margin_deg)
    tv += math.radians(margin_deg)
    a = unit(axis)
    u = unit(up)
    side = u.cross(a).normalized()
    near = v(lens_front)
    far = near + a * length

    def section(at, d):
        w = 2 * (PUPIL_RADIUS + (d + PUPIL_BEHIND) * math.tan(th))
        h = 2 * (PUPIL_RADIUS + (d + PUPIL_BEHIND) * math.tan(tv))
        return Plane(origin=at, x_dir=side, z_dir=a) * Rectangle(w, h)

    return loft([section(near, 0.0), section(far, length)])
