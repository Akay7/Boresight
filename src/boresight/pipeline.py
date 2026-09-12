"""Frame in, cursor move out.

Composes the three pieces that already exist -- `detect.py` finds
markers, `marker_map.py` says where they physically are, `solve.py`
turns that into a screen-space aim point -- and emits the result through
an `inject.py` cursor backend.

Stateless by construction: `process_frame` retains nothing between
calls. That is a real constraint rather than an accident, and it is why
several judgement calls here look conservative. `solve.py` deliberately
declines to decide what to do about a low-confidence aim point, leaving
it to its consumer; this module is that consumer, and without temporal
context the only honest answers are "emit it and say how much evidence
it rests on" and "when there is nothing to solve, emit nothing".
Holding the last good pose and decaying it -- README's actual answer to
dropout -- needs state, and belongs to the filtering stage that lands
on this seam next.

`process_frame` can also be asked for the geometry behind its answer,
as a `FrameDebug`. That is opt-in per call rather than a property of
the pipeline, because one `AimPipeline` is shared by every streaming
session: a flag on the instance would let one client's debug view
change what another client's frames compute.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2
import numpy as np

from boresight.detect import DetectedMarker, detect_markers
from boresight.inject import CursorBackend
from boresight.marker_map import MarkerMap
from boresight.solve import (
    Correspondence,
    InsufficientCorrespondencesError,
    SolveResult,
    solve,
)

# Resolved relative to this module, not the working directory, and kept
# inside the package so it ships in the wheel. As a bare relative path
# it was neither: an installed Boresight had no layout file at all, and
# a checkout resolved it against wherever you happened to be standing.
DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "markers.toml"

Point = tuple[float, float]
Detector = Callable[[np.ndarray], Sequence[DetectedMarker]]


class FrameOutcome(Enum):
    """Why a frame did or did not move the cursor.

    Dropout is the expected steady state, not an error -- detection
    fails for a few frames mid-swing, and close-range frames can have
    no marker in view at all. So the unsolvable cases are returned
    values rather than exceptions; a caller should not have to wrap
    every frame in try/except to handle the normal case.
    """

    SOLVED = "solved"
    NO_MARKERS = "no_markers"
    INSUFFICIENT_CORRESPONDENCES = "insufficient_correspondences"
    SOLVE_FAILED = "solve_failed"


def _round_point(point: Point) -> list[float]:
    return [round(point[0], 1), round(point[1], 1)]


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


@dataclass(frozen=True)
class MarkerDebug:
    """One detection, as it sat in the image the detector was given."""

    marker_id: int
    corners_px: tuple[Point, ...]

    # Whether the layout declares this ID. A tag being seen and skipped
    # and a tag not being seen at all produce the same aim point and
    # look identical from outside; this is the difference.
    mapped: bool


@dataclass(frozen=True)
class FrameDebug:
    """Where the frame's answer came from, in the frame's own pixels.

    Everything here is derived from values the solve already produced,
    inside the same call and after emission. Nothing is recomputed, so
    the geometry cannot describe a different solve than the one that
    moved the cursor.
    """

    image_size_px: tuple[int, int]
    markers: tuple[MarkerDebug, ...]

    # Present only when the frame solved. Absent rather than stale: the
    # consumer draws this over a live image, and last frame's quad over
    # this frame's picture is a confident lie.
    screen_quad_px: tuple[Point, ...] | None = None
    cursor_px: Point | None = None
    reprojection_error_max_px: float | None = None
    reprojection_error_mean_px: float | None = None

    def as_message(self) -> dict:
        """The geometry as it travels to a client that asked for it.

        Coordinates go out at one decimal place. These are drawn onto a
        preview a few hundred pixels wide, so anything finer is invisible
        by construction, and this rides the same per-frame telemetry
        message at the capture frame rate.
        """
        return {
            "image_px": list(self.image_size_px),
            "markers": [
                {
                    "id": marker.marker_id,
                    "corners_px": [_round_point(c) for c in marker.corners_px],
                    "mapped": marker.mapped,
                }
                for marker in self.markers
            ],
            "screen_quad_px": (
                None
                if self.screen_quad_px is None
                else [_round_point(c) for c in self.screen_quad_px]
            ),
            "cursor_px": (
                None if self.cursor_px is None else _round_point(self.cursor_px)
            ),
            "reprojection_max_px": _round_or_none(self.reprojection_error_max_px),
            "reprojection_mean_px": _round_or_none(self.reprojection_error_mean_px),
        }


@dataclass(frozen=True)
class FrameResult:
    outcome: FrameOutcome

    # Unclamped, in screen millimetres. Kept alongside the emitted
    # position so an off-panel aim stays visible: once clamped, an aim
    # 800mm past the edge and an aim exactly at the edge are the same
    # two numbers.
    aim_point_mm: Point | None = None

    # Normalized to [0, 1], exactly as handed to the cursor backend.
    position: Point | None = None
    clamped: bool = False

    markers_detected: int = 0
    markers_mapped: int = 0
    markers_ignored: int = 0

    # Straight from SolveResult. Propagated rather than acted on: a
    # flagged solve means the aim point was extrapolated beyond the
    # visible markers, which bounds nothing about its accuracy in
    # either direction.
    aim_point_inside_hull: bool | None = None
    aim_point_hull_distance_mm: float | None = None

    # Only when the caller asked for it. None means "not requested",
    # never "nothing to say" -- a frame that detected nothing still
    # produces a FrameDebug, with an empty marker list.
    debug: FrameDebug | None = None

    @property
    def emitted(self) -> bool:
        return self.outcome is FrameOutcome.SOLVED


def _as_grayscale(frame: np.ndarray) -> np.ndarray:
    """README's pipeline starts here, and a camera hands over colour."""
    if frame.ndim == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame


# Kept off the literal 0.0/1.0 edge, not just inside it. The cursor
# device is classified as a touchscreen (inject.py) so that positioning
# lands directly rather than through relative-motion acceleration; the
# same classification means several desktop environments watch for a
# pointer reaching the exact screen edge to trigger a bound gesture
# (KDE's Electric Borders "Show Desktop", touch edge-swipe overview,
# and similar), which reads as windows minimizing or rearranging
# themselves for no apparent reason. A margin this small is
# imperceptible against the accuracy numbers in README's "Marker
# visibility and accuracy" section.
EDGE_MARGIN = 0.01


def _clamp_unit(value: float) -> float:
    return min(1.0 - EDGE_MARGIN, max(EDGE_MARGIN, value))


def _to_image_px(homography: np.ndarray, points_mm: Sequence[Point]) -> list[Point]:
    """Screen millimetres -> image pixels.

    `solve.py` fits the homography screen-to-image, so this is its
    forward direction and needs no inversion -- it is the same matrix
    that produced the aim point, run the other way.
    """
    array = np.array(points_mm, dtype=np.float64).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(array, homography)
    return [(float(x), float(y)) for x, y in projected[:, 0, :]]


class AimPipeline:
    """Detection, marker lookup, solving, and emission for one frame.

    Holds only its collaborators; everything that varies per frame is an
    argument. The detector is injectable for the same reason the
    server's cursor backend is: so tests can drive the policy branches
    without rendering an image that produces them.
    """

    def __init__(
        self,
        marker_map: MarkerMap,
        backend: CursorBackend,
        detector: Detector = detect_markers,
    ) -> None:
        self._map = marker_map
        self._backend = backend
        self._detect = detector

    def process_frame(self, frame: np.ndarray, *, debug: bool = False) -> FrameResult:
        height, width = frame.shape[:2]
        image_size_px = (int(width), int(height))

        detected = self._detect(_as_grayscale(frame))
        if not detected:
            return FrameResult(
                outcome=FrameOutcome.NO_MARKERS,
                markers_detected=0,
                debug=FrameDebug(image_size_px, ()) if debug else None,
            )

        correspondences: list[Correspondence] = []
        detections: list[MarkerDebug] = []
        mapped = 0
        for marker in detected:
            corners_mm = self._map.corners_mm(marker.marker_id)
            if debug:
                detections.append(
                    MarkerDebug(
                        marker_id=marker.marker_id,
                        corners_px=tuple(
                            (float(corner[0]), float(corner[1]))
                            for corner in marker.corners
                        ),
                        mapped=corners_mm is not None,
                    )
                )
            if corners_mm is None:
                # A stray ArUco code in the room is an ordinary thing
                # to see. Skip it; do not fail the frame over it.
                continue
            mapped += 1
            for screen_point, image_point in zip(
                corners_mm, marker.corners, strict=True
            ):
                correspondences.append(
                    (screen_point, (float(image_point[0]), float(image_point[1])))
                )

        counts = {
            "markers_detected": len(detected),
            "markers_mapped": mapped,
            "markers_ignored": len(detected) - mapped,
        }
        seen = FrameDebug(image_size_px, tuple(detections)) if debug else None

        try:
            result = solve(correspondences, (float(width), float(height)))
        except InsufficientCorrespondencesError:
            return FrameResult(
                outcome=FrameOutcome.INSUFFICIENT_CORRESPONDENCES,
                debug=seen,
                **counts,
            )
        except ValueError:
            # findHomography declined -- degenerate correspondences.
            return FrameResult(outcome=FrameOutcome.SOLVE_FAILED, debug=seen, **counts)

        aim_x_mm, aim_y_mm = result.aim_point_mm
        screen_width_mm, screen_height_mm = self._map.screen_size_mm
        raw = (aim_x_mm / screen_width_mm, aim_y_mm / screen_height_mm)
        position = (_clamp_unit(raw[0]), _clamp_unit(raw[1]))

        self._backend.move_absolute(*position)

        return FrameResult(
            outcome=FrameOutcome.SOLVED,
            aim_point_mm=result.aim_point_mm,
            position=position,
            clamped=position != raw,
            aim_point_inside_hull=result.aim_point_inside_hull,
            aim_point_hull_distance_mm=result.aim_point_hull_distance_mm,
            debug=None if seen is None else self._solved_debug(seen, result, position),
            **counts,
        )

    def _solved_debug(
        self, seen: FrameDebug, result: SolveResult, position: Point
    ) -> FrameDebug:
        """The solve, placed back in the image it came from.

        `position` is deliberately the *emitted* one -- normalized
        against the configured screen size and clamped by
        `_clamp_unit` -- rather than `result.aim_point_mm`. Pushing the
        aim point back through the homography it was derived from is an
        identity: it returns the image centre, which is where the
        consumer's reticle already is, so it could never disagree and
        would test nothing. Carrying the emitted number back the long
        way exercises the whole output path, and any gap between it and
        the image centre is a real disagreement between what was solved
        and what was sent.
        """
        screen_width_mm, screen_height_mm = self._map.screen_size_mm
        # Clockwise from top-left, matching `Marker.corners_mm`'s order
        # so both quads are read the same way round.
        screen_corners_mm = [
            (0.0, 0.0),
            (screen_width_mm, 0.0),
            (screen_width_mm, screen_height_mm),
            (0.0, screen_height_mm),
        ]
        cursor_mm = (position[0] * screen_width_mm, position[1] * screen_height_mm)

        projected = _to_image_px(result.homography, [*screen_corners_mm, cursor_mm])
        errors = result.reprojection_errors_px

        return FrameDebug(
            image_size_px=seen.image_size_px,
            markers=seen.markers,
            screen_quad_px=tuple(projected[:4]),
            cursor_px=projected[4],
            reprojection_error_max_px=max(errors),
            reprojection_error_mean_px=sum(errors) / len(errors),
        )


def replay(frames_dir: str | Path, pipeline: AimPipeline) -> list[FrameResult]:
    """Run a recorded frame sequence through the pipeline, in order.

    Takes a built pipeline rather than a bare backend so the marker map
    and the backend cannot be specified inconsistently. Reads the
    sequence's `manifest.json` for the frame order; everything else in
    the manifest (ground-truth aim points, render settings) is the
    tests' business, not this function's.
    """
    frames_dir = Path(frames_dir)
    manifest = json.loads((frames_dir / "manifest.json").read_text())

    results = []
    for entry in manifest["frames"]:
        path = frames_dir / entry["file"]
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None:
            raise FileNotFoundError(f"could not read frame {path}")
        results.append(pipeline.process_frame(frame))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    """Replay a recorded sequence against the real cursor, or print it.

    This exists so the detect-solve-inject path is something you can
    watch, not only something a test asserts about -- and so the demo
    and the tests go through the same code.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m boresight.pipeline",
        description="Replay a recorded frame sequence through the aim pipeline.",
    )
    parser.add_argument(
        "frames_dir", help="directory holding manifest.json and the frames"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"marker layout TOML (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the aim track instead of moving the real cursor",
    )
    args = parser.parse_args(argv)

    from boresight.marker_map import load_marker_map

    marker_map = load_marker_map(args.config)

    if args.dry_run:
        from boresight.inject import FakeCursorBackend

        backend: CursorBackend = FakeCursorBackend()
    else:
        from boresight.inject import UinputCursorBackend

        backend = UinputCursorBackend()

    results = replay(args.frames_dir, AimPipeline(marker_map, backend))

    for index, result in enumerate(results, start=1):
        if result.outcome is FrameOutcome.SOLVED:
            aim_x, aim_y = result.aim_point_mm
            position_x, position_y = result.position
            flags = "".join(
                [
                    "" if result.aim_point_inside_hull else " EXTRAPOLATED",
                    " CLAMPED" if result.clamped else "",
                ]
            )
            print(
                f"frame {index:4d}  {result.markers_mapped} markers  "
                f"aim ({aim_x:8.1f}, {aim_y:8.1f}) mm  "
                f"cursor ({position_x:.4f}, {position_y:.4f}){flags}"
            )
        else:
            print(
                f"frame {index:4d}  {result.markers_detected} markers  "
                f"no emission: {result.outcome.value}"
            )

    emitted = sum(1 for result in results if result.emitted)
    print(f"\n{emitted}/{len(results)} frames emitted a cursor move")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
