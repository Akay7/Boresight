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
"""

from __future__ import annotations

import threading

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


def detect_markers(image: np.ndarray) -> list[DetectedMarker]:
    corners, ids, _rejected = thread_detector().detectMarkers(image)

    if ids is None:
        return []

    return [
        DetectedMarker(marker_id=int(marker_id), corners=marker_corners[0])
        for marker_corners, marker_id in zip(corners, ids, strict=True)
    ]
