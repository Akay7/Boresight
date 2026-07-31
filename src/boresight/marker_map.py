"""The physical marker layout, as configuration.

Turns a `markers.toml` into the one thing the solver needs and the
detector cannot know: given a detected marker ID, where that marker's
four corners physically sit on the screen plane.

Coordinates are millimetres with the origin at the top-left corner of
the *active display area*, x rightwards and y downwards. Markers live on
the bezel, outside the panel, so negative coordinates and coordinates
past the screen size are normal rather than errors.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

Point = tuple[float, float]

_REQUIRED_MARKER_FIELDS = ("id", "x", "y", "size_mm")


class MarkerMapError(ValueError):
    """Raised when a layout file is malformed.

    Validation is eager and total: a MarkerMap that exists is one the
    pipeline can use. The alternative -- a partially valid map that
    fails during solving -- turns a config typo into a mysterious
    accuracy problem.
    """


@dataclass(frozen=True)
class Marker:
    """One printed tag: its ID, its top-left corner, and its edge length."""

    marker_id: int
    x_mm: float
    y_mm: float
    size_mm: float

    def corners_mm(self) -> list[Point]:
        """The four corners, clockwise from top-left.

        This order is not arbitrary: it matches the order
        `cv2.aruco.ArucoDetector` reports detected corners in, so the
        two sequences can be zipped positionally and each pair
        describes the same physical corner.
        """
        x, y, size = self.x_mm, self.y_mm, self.size_mm
        return [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]


@dataclass(frozen=True)
class MarkerMap:
    screen_size_mm: Point
    markers: dict[int, Marker]

    def corners_mm(self, marker_id: int) -> list[Point] | None:
        """Corners for `marker_id`, or None if the layout does not declare it.

        Absence is a return value rather than an exception because the
        pipeline's correct response to an unmapped detection is to skip
        it -- a stray ArUco code somewhere in the room is an ordinary
        thing to see, not an error condition.
        """
        marker = self.markers.get(marker_id)
        return None if marker is None else marker.corners_mm()


def _positive(value: object, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise MarkerMapError(f"{field} must be a number, got {value!r}")
    if value <= 0:
        raise MarkerMapError(f"{field} must be positive, got {value}")
    return float(value)


def _number(value: object, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise MarkerMapError(f"{field} must be a number, got {value!r}")
    return float(value)


def _parse_marker(entry: dict, index: int) -> Marker:
    where = f"marker entry {index}"
    for field in _REQUIRED_MARKER_FIELDS:
        if field not in entry:
            raise MarkerMapError(f"{where} is missing required field '{field}'")

    marker_id = entry["id"]
    if not isinstance(marker_id, int) or isinstance(marker_id, bool):
        raise MarkerMapError(f"{where}: id must be an integer, got {marker_id!r}")

    return Marker(
        marker_id=marker_id,
        x_mm=_number(entry["x"], f"{where}: x"),
        y_mm=_number(entry["y"], f"{where}: y"),
        size_mm=_positive(entry["size_mm"], f"{where}: size_mm"),
    )


def parse_marker_map(data: dict) -> MarkerMap:
    """Validate an already-parsed layout mapping. See `load_marker_map`."""
    for field in ("screen_width_mm", "screen_height_mm"):
        if field not in data:
            raise MarkerMapError(f"layout is missing required field '{field}'")

    screen_size = (
        _positive(data["screen_width_mm"], "screen_width_mm"),
        _positive(data["screen_height_mm"], "screen_height_mm"),
    )

    entries = data.get("marker", [])
    if not entries:
        raise MarkerMapError("layout declares no markers")

    markers: dict[int, Marker] = {}
    for index, entry in enumerate(entries):
        marker = _parse_marker(entry, index)
        if marker.marker_id in markers:
            raise MarkerMapError(f"duplicate marker id {marker.marker_id}")
        markers[marker.marker_id] = marker

    return MarkerMap(screen_size_mm=screen_size, markers=markers)


def load_marker_map(path: str | Path) -> MarkerMap:
    """Load and validate a `markers.toml`.

    Raises MarkerMapError for a malformed layout, and the standard
    library's own errors for a missing or syntactically invalid file.
    """
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    return parse_marker_map(data)
