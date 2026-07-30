"""Minimal ArUco marker detection.

Detection through dictionary match only -- per README's Pipeline
section, cornerSubPix refinement and undistortPoints are separate steps
this module does not perform. Built as the smallest wrapper needed to
exercise solve.py against real detection output on a synthetic image
(no camera involved); a fuller detect.py (subpixel refinement, contour
tuning, etc.) is future work once a real camera feed exists.
"""

from __future__ import annotations

import cv2
import numpy as np

DICTIONARY = "DICT_4X4_50"


class DetectedMarker:
    def __init__(self, marker_id: int, corners: np.ndarray) -> None:
        self.marker_id = marker_id
        self.corners = corners


def detect_markers(image: np.ndarray) -> list[DetectedMarker]:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY))
    detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
    corners, ids, _rejected = detector.detectMarkers(image)

    if ids is None:
        return []

    return [
        DetectedMarker(marker_id=int(marker_id), corners=marker_corners[0])
        for marker_corners, marker_id in zip(corners, ids, strict=True)
    ]
