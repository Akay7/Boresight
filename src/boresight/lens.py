"""A camera's lens model, and where calibrated ones are kept.

The solver fits a homography, which assumes a pinhole camera. Real
lenses bend straight lines -- phone wide-angles and the ESP32-CAM's
OV2640 visibly so -- and the fit absorbs that as aim error, worst near
the frame edge. `LensModel` removes it from the handful of points the
solver actually uses (the marker corners and the aim pixel) rather than
remapping the whole frame: ~32 points per frame instead of ~1M pixels.

Points are undistorted with `P = K`, so they stay in pixel units of an
ideal pinhole camera with the same intrinsics. Every other number in
the pipeline (reprojection error, the debug overlay's scale) keeps its
meaning.

Calibrations come from `calibration.py` and are stored per client kind,
camera and frame size in one JSON file. See the `add-lens-calibration`
change's design.md for why the key is that and not less.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("boresight")

DEFAULT_LENS_PATH = Path(".boresight") / "lenses.json"

# `undistortPoints` inverts the distortion iteratively. OpenCV's default
# of 5 iterations leaves a visible residual at the corners of a strongly
# distorted frame, exactly where the correction matters most; 20 is
# still microseconds for 32 points.
UNDISTORT_CRITERIA = (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 20, 1e-6)

Point = tuple[float, float]


@dataclass(frozen=True)
class LensModel:
    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray
    image_size: tuple[int, int]
    rms_px: float = 0.0
    views: int = 0
    created: float = field(default_factory=time.time)

    def undistort_points(self, points: np.ndarray) -> np.ndarray:
        """Raw image pixels -> ideal pinhole pixels, shape preserved."""
        array = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
        undistorted = cv2.undistortPoints(
            array,
            self.camera_matrix,
            self.dist_coeffs,
            P=self.camera_matrix,
            criteria=UNDISTORT_CRITERIA,
        )
        return undistorted.reshape(np.shape(points))

    def distort_points(self, points: np.ndarray) -> np.ndarray:
        """Ideal pinhole pixels -> raw image pixels: the inverse of above.

        For drawing on the picture the camera actually took: back to
        normalised rays through K^-1, then through the full lens model
        with no rotation or translation.
        """
        array = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        rays = (
            np.linalg.inv(self.camera_matrix)
            @ np.column_stack([array, np.ones(len(array))]).T
        )
        projected, _ = cv2.projectPoints(
            rays.T.reshape(-1, 1, 3),
            np.zeros(3),
            np.zeros(3),
            self.camera_matrix,
            self.dist_coeffs,
        )
        return projected.reshape(np.shape(points))

    def undistort_point(self, point: Point) -> Point:
        x, y = self.undistort_points(np.array([point], dtype=np.float64))[0]
        return float(x), float(y)

    def as_dict(self) -> dict:
        return {
            "camera_matrix": self.camera_matrix.tolist(),
            "dist_coeffs": self.dist_coeffs.ravel().tolist(),
            "image_size": list(self.image_size),
            "rms_px": self.rms_px,
            "views": self.views,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LensModel:
        matrix = np.array(data["camera_matrix"], dtype=np.float64)
        coeffs = np.array(data["dist_coeffs"], dtype=np.float64).ravel()
        width, height = (int(side) for side in data["image_size"])
        if matrix.shape != (3, 3) or coeffs.size not in (4, 5, 8, 12, 14):
            raise ValueError("not a camera matrix and distortion vector")
        return cls(
            camera_matrix=matrix,
            dist_coeffs=coeffs,
            image_size=(width, height),
            rms_px=float(data.get("rms_px", 0.0)),
            views=int(data.get("views", 0)),
            created=float(data.get("created", 0.0)),
        )


def lens_key(client: str | None, camera: str | None, size: Sequence[int]) -> str:
    """Which stored calibration a stream uses.

    The resolution is part of it and is never scaled: a phone may crop
    rather than scale between capture modes, and a calibration reused
    at the wrong size would be silently wrong instead of absent.
    """
    width, height = size
    return f"{client or 'unidentified'}|{camera or ''}|{int(width)}x{int(height)}"


class LensStore:
    """Calibrations by `lens_key`, persisted to one JSON file.

    Read once at construction, written on every `put` (write a temp file
    and replace, under a lock: two sessions can finish calibrating at
    once, from different executor threads). Lookups are plain dict
    reads.
    """

    def __init__(self, path: Path | str | None = DEFAULT_LENS_PATH) -> None:
        self._path = None if path is None else Path(path)
        self._lock = threading.Lock()
        self._lenses: dict[str, LensModel] = {}
        if self._path is not None and self._path.exists():
            self._lenses = self._read(self._path)

    @staticmethod
    def _read(path: Path) -> dict[str, LensModel]:
        # A broken file costs the calibrations, not the server: without
        # them aim is exactly what it was before calibration existed.
        try:
            raw = json.loads(path.read_text())
            return {key: LensModel.from_dict(value) for key, value in raw.items()}
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            logger.warning(
                "ignoring lens calibrations in %s (%s); aim is uncorrected",
                path,
                error,
            )
            return {}

    def get(self, key: str) -> LensModel | None:
        return self._lenses.get(key)

    def put(self, key: str, lens: LensModel) -> None:
        with self._lock:
            self._lenses = {**self._lenses, key: lens}
            if self._path is None:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {name: model.as_dict() for name, model in self._lenses.items()},
                    indent=2,
                )
            )
            os.replace(temporary, self._path)

    def listing(self) -> list[dict]:
        return [
            {
                "key": key,
                "image_size": list(lens.image_size),
                "rms_px": round(lens.rms_px, 3),
                "views": lens.views,
                "created": lens.created,
            }
            for key, lens in sorted(self._lenses.items())
        ]
