"""Stand-ins for the Pi's hardware, for `--emulate` and for tests.

They plug into the same seams the real camera, button and USB device do, so
the capture, aim and output code that runs is the code that runs on a Pi.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


class FixtureCamera:
    """A recorded frame sequence (a `manifest.json` and its images), once
    through, with no frame ever skipped."""

    lossless = True

    def __init__(self, frames_dir: Path | str) -> None:
        frames_dir = Path(frames_dir)
        manifest = json.loads((frames_dir / "manifest.json").read_text())
        self._paths = [frames_dir / entry["file"] for entry in manifest["frames"]]
        self._next = 0

    def grab(self) -> tuple[np.ndarray, float | None] | None:
        if self._next >= len(self._paths):
            return None
        path = self._paths[self._next]
        self._next += 1
        frame = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if frame is None:
            raise FileNotFoundError(f"could not read frame {path}")
        return frame, None

    def close(self) -> None:
        pass


class ScriptedTrigger:
    """A button whose level a test or a script sets."""

    def __init__(self) -> None:
        self.level = False

    def read(self) -> bool:
        return self.level


class RecordingSink:
    """Takes the place of /dev/hidg0 and keeps what would have gone to the
    host."""

    def __init__(self) -> None:
        self.reports: list[bytes] = []
        self.closed = False

    def write(self, report: bytes) -> None:
        self.reports.append(report)

    def close(self) -> None:
        self.closed = True
