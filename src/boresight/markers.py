"""Printable ArUco marker generation.

Renders tags from the same dictionary `detect.py` decodes against, so
anything served here is guaranteed detectable. Markers are built as
vector SVG -- one <rect> per dictionary bit cell, including the black
border -- rather than a rasterized image, so print scale carries through
the SVG's own millimeter-unit dimensions instead of depending on any
DPI this code would otherwise have to choose.
"""

from __future__ import annotations

import html
import math
from dataclasses import replace
from urllib.parse import urlencode

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from boresight.detect import DICTIONARY
from boresight.marker_map import Marker, MarkerMap, load_marker_map
from boresight.pipeline import DEFAULT_CONFIG_PATH

router = APIRouter()

DEFAULT_IDS = list(range(8))
DEFAULT_SIZE_MM = 80.0

# Sizes the sheet offers. Every one fits across an A4 page's printable
# width with its one-cell quiet zone (up to ~142mm does); a larger one
# can still be asked for with `size_mm` directly, and the picker says it
# will not fit.
SIZE_PRESETS_MM = (40.0, 50.0, 60.0, 80.0, 100.0, 120.0)

# A4 less the 10mm print margins the sheet asks for on every side.
PRINT_MARGIN_MM = 10.0
A4_PRINTABLE_WIDTH_MM = 210.0 - 2 * PRINT_MARGIN_MM
A4_PRINTABLE_HEIGHT_MM = 297.0 - 2 * PRINT_MARGIN_MM

# A cut-out, top to bottom: padding, the TOP mark, the white quiet zone
# with the tag in it, the id line, the position line, padding. The text
# bands are fixed in mm so a cut-out's height is known here, not left to
# how a browser wraps text -- that is what lets the sheet pair them.
CUTOUT_PADDING_MM = 1.0
UP_BAND_MM = 6.0
LABEL_BAND_MM = 5.0
TAGS_PER_PAGE = 2
PAGE_GAP_MM = 6.0

# The range estimate shown next to each size. README's decode floor is
# about 3px per cell, ~20px across a 6-cell tag; the camera is a typical
# phone main camera streaming 1280 wide at ~70 deg horizontal. An upper
# bound, not a promise: angle, motion blur and JPEG all take from it.
RANGE_MIN_TAG_PX = 20.0
RANGE_IMAGE_WIDTH_PX = 1280
RANGE_HFOV_DEG = 70.0

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

    Includes the 1-cell black border on each side (e.g. 6x6 for
    DICT_4X4_50's 4x4 payload), matching README's "Sizing" section. The
    white quiet zone the detector needs goes outside this grid.
    """
    dictionary = _dictionary()
    max_id = dictionary.bytesList.shape[0] - 1
    if not 0 <= marker_id <= max_id:
        raise ValueError(f"marker id must be between 0 and {max_id}")

    return cv2.aruco.generateImageMarker(dictionary, marker_id, _grid_cells())


def _grid_cells() -> int:
    """Cells across a tag: payload bits plus the black border."""
    return _dictionary().markerSize + 2


def quiet_zone_mm(size_mm: float) -> float:
    """The white margin a tag needs: exactly one cell of its own grid.

    One cell of white is what ArUco needs to find the black border's
    outer edge; the sheet prints exactly that and puts every label
    outside it.
    """
    return size_mm / _grid_cells()


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


def estimated_range_m(size_mm: float) -> float:
    """Farthest decodable distance for a tag this size, in metres."""
    focal_px = (RANGE_IMAGE_WIDTH_PX / 2) / math.tan(math.radians(RANGE_HFOV_DEG / 2))
    return size_mm * focal_px / RANGE_MIN_TAG_PX / 1000.0


def fits_a4(size_mm: float) -> bool:
    """Whether one cut-out fits across an A4 page at 100% scale."""
    return size_mm + 2 * quiet_zone_mm(size_mm) <= A4_PRINTABLE_WIDTH_MM


def cutout_height_mm(size_mm: float) -> float:
    """How tall one cut-out prints, labels and dashed box included."""
    return (
        size_mm
        + 2 * quiet_zone_mm(size_mm)
        + UP_BAND_MM
        + 2 * LABEL_BAND_MM
        + 2 * CUTOUT_PADDING_MM
    )


def paginate(sizes_mm: list[float]) -> list[list[int]]:
    """Group cut-outs, by index into `sizes_mm`, onto printed A4 pages.

    In order, at most TAGS_PER_PAGE to a page, stacked; a cut-out joins
    the page before it only if the whole stack still fits the printable
    height. So a tag too big to pair gets a page of its own.
    """
    pages: list[list[int]] = []
    used = 0.0
    for index, size in enumerate(sizes_mm):
        height = cutout_height_mm(size)
        if (
            pages
            and len(pages[-1]) < TAGS_PER_PAGE
            and used + PAGE_GAP_MM + height <= A4_PRINTABLE_HEIGHT_MM
        ):
            pages[-1].append(index)
            used += PAGE_GAP_MM + height
        else:
            pages.append([index])
            used = height
    return pages


def resized_layout(layout: MarkerMap, size_mm: float) -> MarkerMap:
    """The same layout with every tag `size_mm` on a side.

    Each tag keeps its gap to the panel and grows away from it: a tag
    left of the panel grows leftwards, one above it upwards, and one
    alongside an edge about its own centre along that edge. So a bigger
    tag never creeps over the display it is meant to frame, and the
    diagram's positions still describe it.
    """
    if not math.isfinite(size_mm) or size_mm <= 0:
        raise ValueError("size_mm must be positive")

    def moved(start: float, old: float, slot: int) -> float:
        if slot == 0:  # before the panel: keep the edge facing it
            return start + old - size_mm
        if slot == 2:  # past the panel: its near edge is `start` already
            return start
        return start + (old - size_mm) / 2  # alongside: keep the centre

    markers = {}
    for marker_id, marker in layout.markers.items():
        row, column = marker_slot(marker, layout.screen_size_mm)
        markers[marker_id] = replace(
            marker,
            x_mm=moved(marker.x_mm, marker.size_mm, column),
            y_mm=moved(marker.y_mm, marker.size_mm, row),
            size_mm=size_mm,
        )
    return replace(layout, markers=markers)


def _toml_number(value: float) -> str:
    # repr, not :g -- :g rounds to six significant figures, which would
    # quietly move a tag.
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def layout_toml(layout: MarkerMap, header: str = "") -> str:
    """`layout` as a `markers.toml` that `load_marker_map` reads back."""
    width, height = layout.screen_size_mm
    lines = [f"# {line}" if line else "#" for line in header.splitlines()]
    if lines:
        lines.append("")
    lines += [
        f"screen_width_mm = {_toml_number(width)}",
        f"screen_height_mm = {_toml_number(height)}",
    ]
    for marker_id in sorted(layout.markers):
        marker = layout.markers[marker_id]
        lines += [
            "",
            "[[marker]]",
            f"id = {marker_id}",
            f"x = {_toml_number(marker.x_mm)}",
            f"y = {_toml_number(marker.y_mm)}",
            f"size_mm = {_toml_number(marker.size_mm)}",
        ]
    return "\n".join(lines) + "\n"


def _parse_size(size_mm: str | None) -> float | None:
    """The `size_mm` query value. Empty means "as the layout says".

    Taken as a string rather than a float so the picker's "as in layout"
    choice can submit an empty value instead of needing script to drop
    the field.
    """
    if size_mm is None or not size_mm.strip():
        return None
    try:
        value = float(size_mm)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        raise HTTPException(status_code=422, detail="size_mm must be positive")
    return value


def _link(path: str, **params: object) -> str:
    """A same-server link.

    Carries no token even on a guarded server: the request that
    rendered this page either arrived with the session cookie or, with
    the token in its URL, was answered by setting it. Copying the token
    into links would only put it back into URLs and the access log.
    """
    query = urlencode({k: v for k, v in params.items() if v is not None})
    return f"{path}?{query}" if query else path


def _size_picker(
    layout: MarkerMap | None,
    chosen_mm: float | None,
    ids: str | None,
) -> str:
    """Choose a size. A form, so it works without script."""
    layout_sizes = (
        sorted({marker.size_mm for marker in layout.markers.values()})
        if layout is not None
        else []
    )
    options = []
    if len(layout_sizes) > 1:
        selected = " selected" if chosen_mm is None else ""
        options.append(f'<option value=""{selected}>as in the layout (mixed)</option>')
    current = (
        chosen_mm
        if chosen_mm is not None
        else (layout_sizes[0] if len(layout_sizes) == 1 else None)
    )
    for size in sorted({*SIZE_PRESETS_MM, *layout_sizes, *filter(None, [current])}):
        notes = [f"up to ~{estimated_range_m(size):.1f} m"]
        if size in layout_sizes:
            notes.append("matches the layout")
        if not fits_a4(size):
            notes.append("too wide for A4")
        selected = " selected" if size == current else ""
        options.append(
            f'<option value="{size:g}"{selected}>{size:g} mm &mdash; '
            f"{', '.join(notes)}</option>"
        )

    hidden = ""
    if ids is not None:
        hidden += (
            f'<input type="hidden" name="ids" value="{html.escape(ids, quote=True)}">'
        )

    return (
        '<form class="noprint picker" method="get" action="/markers">'
        '<label>Tag size <select name="size_mm">'
        f"{''.join(options)}"
        "</select></label> "
        f"{hidden}"
        '<button type="submit">Show</button>'
        '<p class="hint">Bigger tags are read from farther away. Ranges are'
        " the most a typical phone camera at 1280&times;720 can decode;"
        " expect about two-thirds of that in play.</p>"
        "</form>"
    )


def _size_mismatch(
    layout: MarkerMap | None, chosen_mm: float | None, ids: list[int]
) -> str:
    """Warn when the printed size is not the size the solver assumes."""
    if layout is None or chosen_mm is None:
        return ""
    differing = sorted(
        {
            layout.markers[marker_id].size_mm
            for marker_id in ids
            if marker_id in layout.markers
            and layout.markers[marker_id].size_mm != chosen_mm
        }
    )
    if not differing:
        return ""
    layout_says = " / ".join(f"{size:g}mm" for size in differing)
    download = html.escape(
        _link("/markers/layout.toml", size_mm=f"{chosen_mm:g}"),
        quote=True,
    )
    return (
        '<div class="noprint mismatch">'
        f"<p><b>These tags are {chosen_mm:g}mm, but the layout this server is"
        f" running with says {layout_says}.</b> The solver places every"
        " corner from the layout's size, so tags printed at another size"
        " aim somewhere else &mdash; with no error to warn you.</p>"
        f'<p><a href="{download}">Download a matching markers.toml</a>, save'
        " it, and restart the server with"
        " <code>--markers file:&lt;the saved file&gt;</code>. Every tag keeps"
        " its gap to the screen and grows outwards, so attach them where the"
        " diagram says, the same distance from the screen edge as before.</p>"
        "</div>"
    )


def _sheet_layout(request: Request) -> MarkerMap | None:
    """The printed layout this server solves against, if there is one.

    The server's own layout, not the shipped reference: a sheet labelled
    from one file while the solver reads another is exactly the silent
    ID-swap this page exists to prevent. Falls back to the shipped file
    only when the router is mounted without a server around it.

    The sheet is still useful without any layout -- you get tags, just
    not the labels saying where each one goes -- so a missing or broken
    layout degrades the page rather than failing the request.
    """
    layout = getattr(request.app.state, "marker_map", None)
    if layout is not None:
        return layout
    try:
        return load_marker_map(DEFAULT_CONFIG_PATH)
    except (OSError, ValueError):
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

    The tag sits alone in a white box one grid cell wider on every side
    -- the quiet zone -- and the TOP mark and labels go above and below
    that box, never in it. The sheet tells you to cut on the dashed
    line, outside the labels, so a cut can't reach the quiet zone either.
    The box is given its computed height, border included, so the page
    it was paired onto is the page it prints on.
    """
    quiet = quiet_zone_mm(size_mm)
    detail = f'<div class="where">{label}</div>' if label else ""
    return (
        f'<div class="marker" style="height: {cutout_height_mm(size_mm):.3f}mm">'
        '<div class="up">&#9650; TOP</div>'
        f'<div class="quiet" style="padding: {quiet:.3f}mm">'
        f"{marker_svg(marker_id, size_mm)}"
        "</div>"
        f'<div class="label">id {marker_id} &middot; {size_mm:g}mm</div>'
        f"{detail}"
        "</div>"
    )


def _pages(cutouts: list[str], sizes_mm: list[float]) -> str:
    """The cut-outs, TAGS_PER_PAGE to a printed page where they fit.

    Each page starts with an explicit break, so page 1 stays the
    instructions and every pair prints together, whatever the browser
    would otherwise have split.
    """
    return "".join(
        '<div class="page">' + "".join(cutouts[i] for i in page) + "</div>"
        for page in paginate(sizes_mm)
    )


@router.get("/markers/layout.toml")
def get_layout_toml(request: Request, size_mm: str | None = None) -> Response:
    """The server's printed layout, optionally resized, as a file to save."""
    layout = _sheet_layout(request)
    if layout is None:
        raise HTTPException(status_code=404, detail="no marker layout is loaded")
    chosen = _parse_size(size_mm)
    header = "Boresight marker layout."
    if chosen is not None:
        layout = resized_layout(layout, chosen)
        header += (
            f"\nEvery tag resized to {chosen:g}mm, keeping its gap to the screen."
            "\nPrint the sheet at this size, attach the tags where these"
            "\npositions say, and start the server with"
            "\n  --markers file:<this file>"
        )
    name = "markers.toml" if chosen is None else f"markers-{chosen:g}mm.toml"
    return Response(
        content=layout_toml(layout, header),
        media_type="application/toml",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/markers", response_class=HTMLResponse)
def get_marker_sheet(
    request: Request, ids: str | None = None, size_mm: str | None = None
) -> str:
    layout = _sheet_layout(request)
    raw_ids = ids
    size_mm = _parse_size(size_mm)
    if ids is None:
        marker_ids = DEFAULT_IDS if layout is None else sorted(layout.markers)
    else:
        try:
            marker_ids = [int(part) for part in ids.split(",") if part]
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="ids must be a comma-separated list of integers"
            ) from exc
        if not marker_ids:
            raise HTTPException(status_code=422, detail="ids names no markers")

    def tag_size(marker_id: int) -> float:
        # An explicit size_mm wins; otherwise each tag prints at the size
        # the layout says it is, since that is the size the solver
        # assumes. A printed tag of any other size shifts every corner.
        if size_mm is not None:
            return size_mm
        if layout is not None and marker_id in layout.markers:
            return layout.markers[marker_id].size_mm
        return DEFAULT_SIZE_MM

    try:
        # The SVG is inlined rather than fetched through <img>, so the
        # page prints as one document. It also keeps the sheet whole on
        # a token-guarded server when the browser holds no session
        # cookie (cookies off, a saved page): an <img src> would then
        # carry no credential and every tag would come back 401.
        cutouts = [
            _tag(
                marker_id,
                tag_size(marker_id),
                None
                if layout is None or marker_id not in layout.markers
                else position_label(layout.markers[marker_id], layout.screen_size_mm),
            )
            for marker_id in marker_ids
        ]
        tags = _pages(cutouts, [tag_size(marker_id) for marker_id in marker_ids])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    diagram = "" if layout is None else _layout_diagram(layout, marker_ids)
    picker = _size_picker(layout, size_mm, raw_ids)
    mismatch = _size_mismatch(layout, size_mm, marker_ids)
    sizes = sorted({tag_size(marker_id) for marker_id in marker_ids})
    expected = (
        f"it should be exactly {sizes[0]:g}mm on a side"
        if len(sizes) == 1
        else "each should measure exactly the size printed under it"
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Boresight markers</title>"
        "<style>"
        f"@page {{ margin: {PRINT_MARGIN_MM:g}mm; }}"
        "body { font-family: sans-serif; margin: 1.5em; }"
        ".instructions { font-weight: bold; }"
        "ol { max-width: 46em; }"
        "li { margin-bottom: 0.35em; }"
        ".diagram { border-collapse: collapse; margin: 1em 0; }"
        ".diagram td { border: 1px solid #999; width: 5em; height: 3em;"
        " text-align: center; font-weight: bold; }"
        ".diagram td.screen { background: #eee; font-weight: normal;"
        " color: #555; }"
        # Every vertical size in a cut-out is fixed in mm and matches
        # cutout_height_mm, so the pairing decided in Python holds on paper.
        ".page { break-before: page; page-break-before: always; }"
        ".marker { display: block; width: fit-content; margin: 0 auto;"
        f" box-sizing: border-box; padding: calc({CUTOUT_PADDING_MM:g}mm - 1px)"
        f" {CUTOUT_PADDING_MM:g}mm; text-align: center;"
        " border: 1px dashed #bbb; page-break-inside: avoid;"
        " break-inside: avoid; }"
        f".marker + .marker {{ margin-top: {PAGE_GAP_MM:g}mm; }}"
        f".up {{ height: {UP_BAND_MM:g}mm; line-height: {UP_BAND_MM:g}mm;"
        " font-size: 9pt; letter-spacing: 0.15em; color: #444;"
        " white-space: nowrap; }"
        ".quiet { background: white; width: fit-content; margin: 0 auto;"
        " line-height: 0; }"
        ".quiet svg { display: block; }"
        f".label {{ height: {LABEL_BAND_MM:g}mm; line-height: {LABEL_BAND_MM:g}mm;"
        " font-size: 11pt; font-weight: bold; white-space: nowrap; }"
        f".where {{ height: {LABEL_BAND_MM:g}mm; line-height: {LABEL_BAND_MM:g}mm;"
        " font-size: 9pt; color: #444; white-space: nowrap; }"
        "@media screen { .page { border-top: 1px solid #ddd;"
        " margin-top: 1.5em; padding-top: 1.5em; } }"
        ".picker { margin: 1em 0; }"
        ".picker select, .picker button { font-size: 1em; }"
        ".hint { font-size: 9pt; color: #555; margin: 0.4em 0 0; }"
        ".mismatch { border: 2px solid #c60; background: #fff4e5;"
        " padding: 0.2em 1em; max-width: 46em; }"
        "@media print { body { margin: 0; } .noprint { display: none; } }"
        "</style></head><body>"
        '<p class="instructions">Print at 100% / actual size'
        " &mdash; never &quot;fit to page&quot; &mdash; with the default"
        f" {PRINT_MARGIN_MM:g}mm margins. Two tags print to a page, after"
        " this page of instructions. Measure one tag against a"
        f" ruler before cutting: {expected}.</p>"
        f"{picker}"
        f"{mismatch}"
        '<div class="steps">'
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
        "<li><b>Cut on the dashed line</b>, outside the labels, not around"
        " the tag. The white border round the tag is exactly one cell of"
        " its grid wide: that is the quiet zone the detector needs to find"
        " the tag's edge, so keep it white and don't let tape cover it.</li>"
        "<li>Matte paper only. Gloss catches screen glare and blows out a"
        " corner of the tag.</li>"
        "<li>These positions and sizes come from the layout this server is"
        " running with. If your display is a different size, measure it"
        " into your own <code>markers.toml</code> and start the server"
        " with <code>--markers file:&lt;path&gt;</code> &mdash; the labels"
        " below will follow it.</li>"
        "</ol>"
        f"{diagram}"
        "</div>"
        f"{tags}"
        "</body></html>"
    )
