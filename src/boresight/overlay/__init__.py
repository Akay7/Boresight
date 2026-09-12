"""Markers drawn on the screen instead of printed and stuck to it.

Removes three costs at once: nothing to print at verified size, nothing
to measure into a layout by hand, and no paper beside a bright panel --
which README names as the dominant failure mode, since auto-exposure
chases the screen and the tags underexpose to mud. On-screen tags are
emissive, so that failure mode does not apply to them.

The overlay must be transparent to input. That is not a nicety: the
system injects its clicks at the aim point, which is on the display the
overlay covers, so an overlay that accepted input would swallow every
shot the gun fired.
"""

from boresight.overlay.layout import (
    DEFAULT_TAG_FRACTION,
    OverlayGeometryError,
    overlay_layout,
)

__all__ = ["DEFAULT_TAG_FRACTION", "OverlayGeometryError", "overlay_layout"]
