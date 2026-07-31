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

router = APIRouter()

DEFAULT_IDS = list(range(8))
DEFAULT_SIZE_MM = 80.0


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

    try:
        for marker_id in marker_ids:
            marker_svg(marker_id, size_mm)  # validate before rendering the page
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    tags = "".join(
        f'<div class="marker">'
        f'<img src="/markers/{marker_id}.svg?size_mm={size_mm}" '
        f'alt="marker {marker_id}">'
        f'<div class="label">id {marker_id}</div>'
        "</div>"
        for marker_id in marker_ids
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Boresight markers</title>"
        "<style>"
        "body { font-family: sans-serif; }"
        ".instructions { font-weight: bold; }"
        ".marker { display: inline-block; margin: 1em; text-align: center; }"
        "</style></head><body>"
        '<p class="instructions">Print at 100% / actual size'
        " &mdash; never &quot;fit to page&quot;.</p>"
        f"{tags}"
        "</body></html>"
    )
