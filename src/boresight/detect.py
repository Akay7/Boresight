"""ArUco marker detection with sub-pixel corner refinement.

Dictionary match finds the markers; `cv2.cornerSubPix`, run by the
detector itself (`CORNER_REFINE_SUBPIX`), then moves each corner off the
integer-ish contour vertex onto the actual intensity edge. The solver
fits a homography to these corners and nothing else, so corner noise is
aim noise: on the checked-in fixtures refinement roughly halves corner
error and cuts frame-to-frame aim jitter several-fold (numbers in the
`improve-marker-detection` change's design.md). `undistortPoints` is
still a separate step this module does not perform.

The detector is built once per thread rather than once per frame. One
`AimPipeline` serves every streaming session and the server runs each
frame on an executor thread, so several frames can be in detection at
once; OpenCV does not document `ArucoDetector` as safe to share across
threads, so each thread gets its own rather than relying on it.

`MarkerTracker` is the fast path, one per streaming session. While the
markers it last saw are large enough, it detects on a half-size copy
of the frame and refines the corners back at full resolution, which
returns full-resolution corners at a fraction of the full pass's cost;
whenever that pass could have missed or mislocated something it runs
the full pass instead. Numbers in the `speed-up-marker-detection`
change's design.md. Either way the output is the same contract: corners
in the original frame's pixels.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence

import cv2
import numpy as np

DICTIONARY = "DICT_4X4_50"

# cornerSubPix's search window is a half-size in pixels. OpenCV caps it
# at `relativeCornerRefinmentWinSize` x the marker's module (bit cell)
# size, then at `cornerRefinementWinSize`. A window of one module
# reaches from the corner to the inner edge of the black border and no
# further, so it sees the one corner and not the data bits behind it;
# OpenCV's default of 0.3 module is ~1px on a 25px ESP32-CAM marker,
# too small to refine anything, and wider than a module starts pulling
# corners toward the bits. The 5px cap only bites on markers above
# ~30px, where 5px is already a wide window.
CORNER_REFINEMENT_WIN_SIZE = 5
CORNER_REFINEMENT_RELATIVE_WIN_SIZE = 1.0
# OpenCV's defaults. The fixtures converge well inside both; neither
# moved any measured error when varied (10-100 iterations, 0.1-0.01px).
CORNER_REFINEMENT_MAX_ITERATIONS = 30
CORNER_REFINEMENT_MIN_ACCURACY = 0.1

# The coarse pass works on a frame this fraction of the size. Half is
# the one ratio `cv2.resize` has a fast area-averaging path for; at 0.75
# the resize alone cost more than it saved (measured in design.md).
COARSE_SCALE = 0.5
# The smallest marker, in full-resolution pixels, the tracker trusts the
# coarse pass with: 18px across once halved, 3px per module. The phone
# fixture's ~38px markers came through the coarse pass with every marker
# found and corners within 0.05px of the full pass; the ESP32-CAM
# fixture's ~25px markers lost a third of their detections and some
# corners by several pixels, so those frames stay on the full pass.
COARSE_MIN_SIDE_PX = 36.0
# A full pass at least this often, so a marker the coarse pass cannot
# see -- one entering the frame too small for it -- is found within
# this many frames (a third of a second at 30fps).
FULL_PASS_EVERY_FRAMES = 10
# After the coarse pass misses a marker, this many frames -- the one
# that missed included -- go straight to the full pass. A camera whose
# images the coarse pass keeps failing on then costs one wasted coarse
# pass per this many frames rather than one per frame.
COARSE_BACKOFF_FRAMES = 10


class DetectedMarker:
    def __init__(self, marker_id: int, corners: np.ndarray) -> None:
        self.marker_id = marker_id
        self.corners = corners


def detector_parameters() -> cv2.aruco.DetectorParameters:
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.cornerRefinementWinSize = CORNER_REFINEMENT_WIN_SIZE
    parameters.relativeCornerRefinmentWinSize = CORNER_REFINEMENT_RELATIVE_WIN_SIZE
    parameters.cornerRefinementMaxIterations = CORNER_REFINEMENT_MAX_ITERATIONS
    parameters.cornerRefinementMinAccuracy = CORNER_REFINEMENT_MIN_ACCURACY
    return parameters


def build_detector() -> cv2.aruco.ArucoDetector:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY))
    return cv2.aruco.ArucoDetector(dictionary, detector_parameters())


_per_thread = threading.local()


def thread_detector() -> cv2.aruco.ArucoDetector:
    """This thread's detector, built on first use and kept after."""
    detector = getattr(_per_thread, "detector", None)
    if detector is None:
        detector = build_detector()
        _per_thread.detector = detector
    return detector


def _as_markers(corners, ids) -> list[DetectedMarker]:
    if ids is None:
        return []
    return [
        DetectedMarker(marker_id=int(marker_id), corners=marker_corners[0])
        for marker_corners, marker_id in zip(corners, np.ravel(ids), strict=True)
    ]


def detect_markers(image: np.ndarray) -> list[DetectedMarker]:
    corners, ids, _rejected = thread_detector().detectMarkers(image)
    return _as_markers(corners, ids)


# Modules across a marker, border included: what OpenCV divides a
# marker's side by to get the module size its refinement window uses.
_MODULES_ACROSS = (
    cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY)).markerSize
    + 2 * detector_parameters().markerBorderBits
)
_REFINEMENT_CRITERIA = (
    cv2.TERM_CRITERIA_MAX_ITER | cv2.TERM_CRITERIA_EPS,
    CORNER_REFINEMENT_MAX_ITERATIONS,
    CORNER_REFINEMENT_MIN_ACCURACY,
)


def side_px(marker: DetectedMarker) -> float:
    """The marker's shortest edge, in the pixels of its corners."""
    edges = marker.corners - np.roll(marker.corners, 1, axis=0)
    return float(np.linalg.norm(edges, axis=1).min())


def _refinement_window(corners: np.ndarray) -> int:
    """The half-size the detector itself would refine these corners with.

    OpenCV's own rule for `relativeCornerRefinmentWinSize`, so a corner
    refined here sees the same neighbourhood a full pass would give it.
    """
    edges = corners - np.roll(corners, 1, axis=0)
    module_px = float(np.linalg.norm(edges, axis=1).mean()) / _MODULES_ACROSS
    window = round(CORNER_REFINEMENT_RELATIVE_WIN_SIZE * module_px)
    return max(1, min(CORNER_REFINEMENT_WIN_SIZE, window))


def detect_markers_coarse(
    image: np.ndarray, scale: float = COARSE_SCALE
) -> list[DetectedMarker]:
    """Find markers on a downscaled copy, then refine at full resolution.

    Two refinements, not one. The detector refines on the small image as
    it always does, which puts each corner within a fraction of a small
    pixel; scaled up, that is still up to a couple of full pixels out,
    and on a noisy frame the bare contour vertex was up to 6px out --
    past the reach of a 5px refinement window. The second `cornerSubPix`
    then runs on the full-resolution image, so the corners returned are
    as precise as the full pass's, in the same coordinates.
    """
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    corners, ids, _rejected = thread_detector().detectMarkers(small)
    markers = _as_markers(corners, ids)
    for marker in markers:
        # Area-averaged: small pixel i covers full pixels i/scale up to
        # (i + 1)/scale, so its centre sits half a small pixel in.
        full = ((marker.corners + 0.5) / scale - 0.5).astype(np.float32)
        window = _refinement_window(full)
        refined = cv2.cornerSubPix(
            image,
            full.reshape(-1, 1, 2),
            (window, window),
            (-1, -1),
            _REFINEMENT_CRITERIA,
        )
        marker.corners = refined.reshape(4, 2)
    return markers


Detector = Callable[[np.ndarray], Sequence[DetectedMarker]]


class MarkerTracker:
    """One session's detector: the coarse pass when it is safe, the
    full pass when it is not.

    Callable like `detect_markers`, and returns what the full pass would
    have, only sooner. The coarse pass runs only while every marker the
    previous frame found was at least `min_side_px` across, and its
    answer stands only if it found every one of those markers again and
    nothing smaller than that. Anything else -- no markers last frame, a
    marker lost or found too small, a full pass due -- runs the full pass
    on this same frame, so a miss costs time, never a detection.

    Holds state between frames, so one belongs to one session. Not safe
    to share between threads; a session processes one frame at a time,
    which is all it needs. The OpenCV detector underneath is still the
    calling thread's own (`thread_detector`).
    """

    def __init__(
        self,
        full: Detector = detect_markers,
        coarse: Detector = detect_markers_coarse,
        *,
        min_side_px: float = COARSE_MIN_SIDE_PX,
        full_pass_every: int = FULL_PASS_EVERY_FRAMES,
        backoff_frames: int = COARSE_BACKOFF_FRAMES,
    ) -> None:
        self._full = full
        self._coarse = coarse
        self._min_side_px = min_side_px
        self._full_pass_every = full_pass_every
        self._backoff_frames = backoff_frames

        self._tracked: set[int] = set()
        self._smallest_px = 0.0
        self._since_full = 0
        self._backoff = 0

        # Observability for the benchmark and the tests.
        self.full_passes = 0
        self.coarse_passes = 0
        self.coarse_misses = 0

    def __call__(self, image: np.ndarray) -> list[DetectedMarker]:
        if self._coarse_due():
            found = list(self._coarse(image))
            if self._trust(found):
                self.coarse_passes += 1
                self._since_full += 1
                self._remember(found)
                return found
            self.coarse_misses += 1
            self._backoff = self._backoff_frames

        found = list(self._full(image))
        self.full_passes += 1
        self._since_full = 0
        self._backoff = max(0, self._backoff - 1)
        self._remember(found)
        return found

    def _coarse_due(self) -> bool:
        return (
            bool(self._tracked)
            and self._backoff == 0
            and self._smallest_px >= self._min_side_px
            and self._since_full + 1 < self._full_pass_every
        )

    def _trust(self, found: list[DetectedMarker]) -> bool:
        if not self._tracked <= {marker.marker_id for marker in found}:
            return False
        return all(side_px(marker) >= self._min_side_px for marker in found)

    def _remember(self, found: list[DetectedMarker]) -> None:
        self._tracked = {marker.marker_id for marker in found}
        self._smallest_px = min((side_px(marker) for marker in found), default=0.0)
