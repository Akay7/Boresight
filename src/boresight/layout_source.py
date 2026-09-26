"""Where the marker layout comes from.

Printed and on-screen markers are alternatives, not a migration. A
layout loaded from `markers.toml` and one derived from a display are
the same type, in the same units convention, and the pipeline cannot
tell them apart -- so choosing between them is configuration rather
than a code path.

Importing this is safe on a default install: the overlay's *layout*
maths is pure arithmetic over `marker_map`, and nothing here reaches
for a graphical toolkit.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from boresight.marker_map import MarkerMap, load_marker_map
from boresight.overlay.layout import overlay_layout
from boresight.pipeline import DEFAULT_CONFIG_PATH

DEFAULT_SPEC = "file"

_SCREEN = re.compile(r"^screen:(\d+)x(\d+)$", re.IGNORECASE)


class LayoutSourceError(ValueError):
    """Raised for a layout source that cannot be understood."""


def resolve_layout(spec: str = DEFAULT_SPEC) -> MarkerMap:
    """Build the layout named by `spec`.

    Accepted forms:

        file                 the shipped reference layout
        file:<path>          a layout of your own
        screen:<W>x<H>       tags drawn on a display of that pixel size
    """
    if spec in ("", "file"):
        return load_marker_map(DEFAULT_CONFIG_PATH)

    if spec.startswith("file:"):
        # Check the text, not a Path: Path("") is Path("."), which is
        # truthy and would then fail as "Is a directory".
        path_text = spec[len("file:") :].strip()
        if not path_text:
            raise LayoutSourceError(
                "file: needs a path, e.g. file:markers.toml, "
                "or use plain 'file' for the default"
            )
        return load_marker_map(Path(path_text))

    screen = _SCREEN.match(spec)
    if screen:
        width, height = int(screen.group(1)), int(screen.group(2))
        # The scale is left at its default of 1.0 on purpose: it cancels
        # under the pipeline's normalization, so pixels serve as the
        # layout's nominal millimetres. See overlay.layout.
        return overlay_layout((width, height))

    raise LayoutSourceError(
        f"unrecognised marker layout {spec!r}. Use 'file', "
        "'file:<path>', or 'screen:<width>x<height>' (e.g. screen:1920x1080)."
    )


def marker_map_factory(spec: str = DEFAULT_SPEC) -> Callable[[], MarkerMap]:
    """A zero-argument factory, matching the server's existing seam.

    The spec is validated now rather than at startup, so a typo is
    reported when it is written instead of when the first frame arrives.
    """
    resolve_layout(spec)
    return lambda: resolve_layout(spec)
