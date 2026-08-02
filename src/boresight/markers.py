"""Printable ArUco marker generation.

Renders tags from the same dictionary `detect.py` decodes against, so
anything served here is guaranteed detectable. Markers are built as
vector SVG -- one <rect> per dictionary bit cell, including the quiet
border -- rather than a rasterized image, so print scale carries through
the SVG's own millimeter-unit dimensions instead of depending on any
DPI this code would otherwise have to choose.
"""

from __future__ import annotations

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from boresight.detect import DICTIONARY
from boresight.marker_map import Marker, MarkerMap, load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH

router = APIRouter()

DEFAULT_IDS = list(range(8))
DEFAULT_SIZE_MM = 80.0

# White paper around the tag, as a fraction of its edge. The detector
# needs a quiet zone of about one bit cell (a sixth of the tag for
# DICT_4X4_50); this is comfortably more, and matches the 120mm
# cardstock the rendered fixtures put around their 80mm tags. Labels go
# outside it, never inside.
MARGIN_FRACTION = 0.25

_POSITION_LABELS = {
    (0, 0): "top-left corner",
    (0, 1): "top edge, middle",
    (0, 2): "top-right corner",
    (1, 0): "left edge, middle",
    (1, 1): "over the panel",
    (1, 2): "right edge, middle",
    (2, 0): "bottom-left corner",
    (2, 1): "bottom edge, middle",
    (2, 2): "bottom-right corner",
}


def _dictionary() -> cv2.aruco.Dictionary:
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY))


def marker_grid(marker_id: int) -> np.ndarray:
    """The dictionary's bit grid for `marker_id`, one pixel per cell.

    Includes the 1-cell quiet border on each side (e.g. 6x6 for
    DICT_4X4_50's 4x4 payload), matching README's "Sizing" section.
    """
    dictionary = _dictionary()
    max_id = dictionary.bytesList.shape[0] - 1
    if not 0 <= marker_id <= max_id:
        raise ValueError(f"marker id must be between 0 and {max_id}")

    side = dictionary.markerSize + 2
    return cv2.aruco.generateImageMarker(dictionary, marker_id, side)


def marker_svg(marker_id: int, size_mm: float) -> str:
    """A vector SVG of `marker_id` at exactly `size_mm` on a side."""
    if size_mm <= 0:
        raise ValueError("size_mm must be positive")

    grid = marker_grid(marker_id)
    n = grid.shape[0]
    black_cells = "".join(
        f'<rect x="{col}" y="{row}" width="1" height="1"/>'
        for row in range(n)
        for col in range(n)
        if grid[row, col] == 0
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {n} {n}" width="{size_mm}mm" height="{size_mm}mm" '
        f'shape-rendering="crispEdges">'
        f'<rect x="0" y="0" width="{n}" height="{n}" fill="white"/>'
        f'<g fill="black">{black_cells}</g>'
        "</svg>"
    )


@router.get("/markers/{marker_id}.svg")
def get_marker_svg(marker_id: int, size_mm: float = DEFAULT_SIZE_MM) -> Response:
    try:
        svg = marker_svg(marker_id, size_mm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(content=svg, media_type="image/svg+xml")


def marker_slot(marker: Marker, screen_size_mm: tuple[float, float]) -> tuple[int, int]:
    """Which of the nine regions around the panel a marker sits in.

    Row and column are each 0 (before the panel), 1 (alongside it) or 2
    (past it), which is enough to name every position in the layout
    without the layout having to spell them out.
    """
    width, height = screen_size_mm
    column = (
        0 if marker.x_mm + marker.size_mm <= 0 else 2 if marker.x_mm >= width else 1
    )
    row = 0 if marker.y_mm + marker.size_mm <= 0 else 2 if marker.y_mm >= height else 1
    return row, column


def position_label(marker: Marker, screen_size_mm: tuple[float, float]) -> str:
    return _POSITION_LABELS[marker_slot(marker, screen_size_mm)]


def _reference_layout() -> MarkerMap | None:
    """The shipped layout, if it is readable.

    The sheet is still useful without it -- you get tags, just not the
    labels saying where each one goes -- so a missing or broken layout
    degrades the page rather than failing the request.
    """
    try:
        return load_marker_map(DEFAULT_CONFIG_PATH)
    except OSError, ValueError:
        return None


def _layout_diagram(layout: MarkerMap, marker_ids: list[int]) -> str:
    """A picture of where each ID belongs, built from the layout itself."""
    grid: dict[tuple[int, int], list[str]] = {}
    for marker_id in marker_ids:
        marker = layout.markers.get(marker_id)
        if marker is None:
            continue
        grid.setdefault(marker_slot(marker, layout.screen_size_mm), []).append(
            str(marker_id)
        )

    rows = ""
    for row in range(3):
        cells = ""
        for column in range(3):
            if (row, column) == (1, 1):
                width, height = layout.screen_size_mm
                cells += (
                    f'<td class="screen">screen<br><small>{width:.0f} '
                    f"&times; {height:.0f} mm</small></td>"
                )
            else:
                ids = " ".join(grid.get((row, column), []))
                cells += f"<td>{ids or '&middot;'}</td>"
        rows += f"<tr>{cells}</tr>"
    return f'<table class="diagram">{rows}</table>'


def _tag(marker_id: int, size_mm: float, label: str | None) -> str:
    """One cut-out: orientation mark, tag, and what it is.

    The labels sit outside the tag's white margin, and the sheet tells
    you to cut on the dashed line, so nothing printed here can encroach
    on the quiet zone the detector needs.
    """
    margin = size_mm * MARGIN_FRACTION
    detail = f'<div class="where">{label}</div>' if label else ""
    return (
        f'<div class="marker" style="padding: {margin}mm">'
        '<div class="up">&#9650; TOP</div>'
        f"{marker_svg(marker_id, size_mm)}"
        f'<div class="label">id {marker_id}</div>'
        f"{detail}"
        "</div>"
    )


@router.get("/markers", response_class=HTMLResponse)
def get_marker_sheet(ids: str | None = None, size_mm: float = DEFAULT_SIZE_MM) -> str:
    if ids is None:
        marker_ids = DEFAULT_IDS
    else:
        try:
            marker_ids = [int(part) for part in ids.split(",") if part]
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="ids must be a comma-separated list of integers"
            ) from exc

    layout = _reference_layout()
    try:
        # The SVG is inlined rather than fetched through <img>, so the
        # page prints as one document. It also has to be: when the
        # server is token-guarded, a browser requesting the src would
        # send no token and every tag would come back 401.
        tags = "".join(
            _tag(
                marker_id,
                size_mm,
                None
                if layout is None or marker_id not in layout.markers
                else position_label(layout.markers[marker_id], layout.screen_size_mm),
            )
            for marker_id in marker_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    diagram = "" if layout is None else _layout_diagram(layout, marker_ids)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Boresight markers</title>"
        "<style>"
        "body { font-family: sans-serif; margin: 1.5em; }"
        ".instructions { font-weight: bold; }"
        "ol { max-width: 46em; }"
        "li { margin-bottom: 0.35em; }"
        ".diagram { border-collapse: collapse; margin: 1em 0; }"
        ".diagram td { border: 1px solid #999; width: 5em; height: 3em;"
        " text-align: center; font-weight: bold; }"
        ".diagram td.screen { background: #eee; font-weight: normal;"
        " color: #555; }"
        ".marker { display: inline-block; margin: 0.5em; text-align: center;"
        " border: 1px dashed #bbb; page-break-inside: avoid;"
        " break-inside: avoid; }"
        ".up { font-size: 9pt; letter-spacing: 0.15em; color: #444;"
        " margin-bottom: 0.4em; }"
        ".label { font-weight: bold; margin-top: 0.4em; }"
        ".where { font-size: 9pt; color: #444; }"
        "@media print { .noprint { display: none; } }"
        "</style></head><body>"
        '<p class="instructions">Print at 100% / actual size'
        " &mdash; never &quot;fit to page&quot;. Measure one tag against a"
        f" ruler before cutting: it should be exactly {size_mm:g}mm on a side.</p>"
        '<div class="noprint">'
        "<ol>"
        "<li><b>Attach each tag upright</b>, with &#9650; TOP pointing up."
        " The detector reads a tag's rotation from its own bit pattern, so a"
        " tag stuck on sideways is still recognised &mdash; but its corners"
        " then pair with the wrong screen coordinates. This matters more the"
        " fewer tags you use: with all eight in view the error is averaged"
        " away, with one or two it is not.</li>"
        "<li><b>Put each ID where the diagram says.</b> IDs are positions,"
        " not decoration. Swap two and the solver still fits a homography"
        " perfectly well &mdash; it just aims somewhere else, with no"
        " error to warn you.</li>"
        "<li><b>Cut on the dashed line</b>, not around the tag. The white"
        " margin is the quiet zone the detector needs to find the tag's"
        " edge.</li>"
        "<li>Matte paper only. Gloss catches screen glare and blows out a"
        " corner of the tag.</li>"
        "<li>These positions describe the shipped reference layout. If your"
        " display is a different size, measure it into your own"
        " <code>markers.toml</code> &mdash; the labels below will follow"
        " it.</li>"
        "</ol>"
        f"{diagram}"
        "</div>"
        f"{tags}"
        "</body></html>"
    )
