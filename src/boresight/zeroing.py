"""Zeroing the gun: where the barrel points, not where the camera does.

The solve aims with the image centre, which is where the *camera*
points. A camera is never mounted exactly along the barrel, and a
light-gun game hides the cursor, so the player cannot see the error to
compensate for it. Zeroing is the fix a real sight gets: shoot known
targets, then correct.

The correction is modelled on the physics rather than fitted as a
screen-space warp (see the add-boresight-calibration design):

- Angular misalignment. A pinhole camera sees every direction at a
  fixed pixel, and the barrel is a direction, so a tilted mount means
  the barrel aims at a fixed image point `c + D*offset` instead of the
  centre `c` -- at any distance and any angle to the screen.
- Parallax. The barrel line runs a few centimetres beside the camera.
  On the screen that is a constant offset; in the image it is `(f/z)*t`
  and shrinks with distance. `f/z` is the local image scale the frame's
  own homography already measures, so no camera intrinsics are needed.

A screen-space fit is exact only at the pose it was made from; this
one stays right when the player moves. The price is that it cannot
absorb a mis-measured marker layout, which shows up as a residual
instead of being hidden.

Pure geometry and bookkeeping: no FastAPI, no devices, no Qt.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

Point = tuple[float, float]

logger = logging.getLogger("boresight")

# Next to the TLS material, and like it relative to where the server is
# started. One JSON object for every client that has zeroed.
DEFAULT_ZEROING_PATH = Path(".boresight") / "zeroing.json"

# How far apart, as a ratio of image scale, the shots' distances must be
# before parallax is fitted separately from tilt. From one distance the
# two are indistinguishable (every shot has the same scale), and a split
# fitted from a few percent of spread is noise amplified. 1.3 is about a
# 30% change of distance: a step or two back from a couch.
PARALLAX_MIN_SPREAD = 1.3

# Overlay targets sit this far in from the corners of its area, as a
# fraction of the area: inside the marker hull, so the shot's frame is
# interpolated rather than extrapolated, and well clear of the tags.
OVERLAY_TARGET_INSET = 0.15

# The identity a session that never said who it is zeroes under.
UNIDENTIFIED_KEY = "unidentified"

_CLIENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass(frozen=True, eq=False)
class SightFrame:
    """What one solved frame knows about the camera, for zeroing.

    Equality is identity: it carries a matrix, and nothing compares two
    of these for sameness.
    """

    homography: np.ndarray  # screen mm -> image px, as `solve.py` fits it
    image_size_px: tuple[int, int]
    screen_size_mm: Point
    # The image point the solve aimed through, when not the frame's
    # centre: with a lens calibration, the centre undistorted (`lens.py`).
    centre: Point | None = None

    @property
    def centre_px(self) -> Point:
        if self.centre is not None:
            return self.centre
        return (self.image_size_px[0] / 2.0, self.image_size_px[1] / 2.0)

    def to_image(self, point_mm: Point) -> Point:
        return _transform(self.homography, point_mm)

    def to_screen(self, point_px: Point) -> Point:
        return _transform(np.linalg.inv(self.homography), point_px)

    def scale(self, point_mm: Point) -> float:
        """Image pixels per screen width, locally at `point_mm`.

        The geometric mean of the homography's Jacobian there -- exactly
        `f/z` for a camera facing the screen, and a few percent off at a
        steep angle, which on a parallax of centimetres is millimetres.
        """
        h = self.homography
        x, y = point_mm
        w = h[2, 0] * x + h[2, 1] * y + h[2, 2]
        u = (h[0, 0] * x + h[0, 1] * y + h[0, 2]) / w
        v = (h[1, 0] * x + h[1, 1] * y + h[1, 2]) / w
        jacobian = (
            np.array(
                [
                    [h[0, 0] - u * h[2, 0], h[0, 1] - u * h[2, 1]],
                    [h[1, 0] - v * h[2, 0], h[1, 1] - v * h[2, 1]],
                ]
            )
            / w
        )
        return math.sqrt(abs(float(np.linalg.det(jacobian)))) * self.screen_size_mm[0]


def _transform(matrix: np.ndarray, point: Point) -> Point:
    array = np.array([[point]], dtype=np.float64)
    x, y = cv2.perspectiveTransform(array, matrix)[0, 0]
    return (float(x), float(y))


@dataclass(frozen=True)
class Zero:
    """One client's correction.

    `offset` is where the barrel aims in the image relative to the
    centre, as a fraction of the frame's width and height, so a change of
    resolution at the same aspect keeps it. `parallax` is the lateral
    camera-to-barrel offset in screen widths -- a unit that means the
    same against a printed layout (millimetres) and the overlay's
    (pixels), since both normalize to the same screen.
    """

    offset: Point = (0.0, 0.0)
    parallax: Point = (0.0, 0.0)
    shots: int = 0
    # RMS distance of the corrected shots from their targets, in screen
    # widths. None for a zero that did not come from a fit.
    residual: float | None = None

    def aim_px(self, frame: SightFrame) -> Point:
        """The image point the barrel aims at, in this frame."""
        cx, cy = frame.centre_px
        width, height = frame.image_size_px
        x = cx + self.offset[0] * width
        y = cy + self.offset[1] * height
        if self.parallax != (0.0, 0.0):
            # Scaled at the tilt-corrected aim rather than the raw one:
            # it is nearer where the barrel actually hits.
            k = frame.scale(frame.to_screen((x, y)))
            x += k * self.parallax[0]
            y += k * self.parallax[1]
        return (x, y)

    def aim_mm(self, frame: SightFrame) -> Point:
        """Where the barrel hits the screen, in the layout's millimetres."""
        return frame.to_screen(self.aim_px(frame))

    def as_dict(self) -> dict:
        return {
            "offset": list(self.offset),
            "parallax": list(self.parallax),
            "shots": self.shots,
            "residual": self.residual,
        }

    @classmethod
    def from_dict(cls, data: object) -> Zero:
        """Raises ValueError for anything that is not a stored zero."""
        if not isinstance(data, dict):
            raise ValueError("not an object")
        residual = data.get("residual")
        return cls(
            offset=_pair(data.get("offset")),
            parallax=_pair(data.get("parallax")),
            shots=int(data.get("shots", 0)),
            residual=None if residual is None else float(residual),
        )


def _pair(value: object) -> Point:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"expected two numbers, got {value!r}")
    x, y = (float(v) for v in value)
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"expected finite numbers, got {value!r}")
    return (x, y)


# --- Targets and the fit ----------------------------------------------


@dataclass(frozen=True)
class Target:
    label: str
    # Normalized full-screen coordinates, as the cursor is.
    position: Point
    # The repeat shot from another distance, which only the parallax
    # term needs.
    optional: bool = False


OverlayArea = tuple[tuple[int, int], tuple[int, int, int, int]]


def targets(overlay: OverlayArea | None = None) -> tuple[Target, ...]:
    """The targets to shoot, in order.

    With the overlay running (`(screen_px, area_px)`), targets it can
    draw: its area's corners inset toward the centre, then the centre.
    Without it nothing can be drawn, so the display's own corners, which
    a player can always see.
    """
    if overlay is None:
        corners = (
            Target("top-left corner of the screen", (0.0, 0.0)),
            Target("top-right corner of the screen", (1.0, 0.0)),
            Target("bottom-right corner of the screen", (1.0, 1.0)),
            Target("bottom-left corner of the screen", (0.0, 1.0)),
        )
        again = Target(
            "top-left corner again, from a different distance",
            (0.0, 0.0),
            optional=True,
        )
        return (*corners, again)

    (screen_w, screen_h), (area_x, area_y, area_w, area_h) = overlay

    def at(fx: float, fy: float) -> Point:
        return ((area_x + fx * area_w) / screen_w, (area_y + fy * area_h) / screen_h)

    near, far = OVERLAY_TARGET_INSET, 1.0 - OVERLAY_TARGET_INSET
    return (
        Target("top-left target", at(near, near)),
        Target("top-right target", at(far, near)),
        Target("bottom-right target", at(far, far)),
        Target("bottom-left target", at(near, far)),
        Target("centre target", at(0.5, 0.5)),
        Target(
            "centre target again, from a different distance",
            at(0.5, 0.5),
            optional=True,
        ),
    )


@dataclass(frozen=True)
class Shot:
    target: Target
    frame: SightFrame

    @property
    def target_mm(self) -> Point:
        # Through the shot's own frame's screen size, so a marker-source
        # switch mid-run cannot mix two units.
        width, height = self.frame.screen_size_mm
        return (self.target.position[0] * width, self.target.position[1] * height)


def fit(shots: Sequence[Shot]) -> Zero:
    """The correction that best puts each shot on its target.

    Per axis, one equation per shot: `size*offset + k*parallax = p - c`,
    with `p` the target seen in the shot's image. Parallax is solved for
    only when the shots' scales `k` span `PARALLAX_MIN_SPREAD`; otherwise
    the offset alone takes the whole error, which is exact at the
    distance the shots were taken from.
    """
    if not shots:
        raise ValueError("zeroing needs at least one shot")

    rows = []
    for shot in shots:
        target_px = shot.frame.to_image(shot.target_mm)
        cx, cy = shot.frame.centre_px
        width, height = shot.frame.image_size_px
        rows.append(
            (
                width,
                height,
                shot.frame.scale(shot.target_mm),
                target_px[0] - cx,
                target_px[1] - cy,
            )
        )
    table = np.array(rows, dtype=np.float64)
    sizes_x, sizes_y, scales, errors_x, errors_y = table.T

    if len(shots) >= 2 and scales.max() >= PARALLAX_MIN_SPREAD * scales.min():
        (offset_x, parallax_x), *_ = np.linalg.lstsq(
            np.column_stack([sizes_x, scales]), errors_x, rcond=None
        )
        (offset_y, parallax_y), *_ = np.linalg.lstsq(
            np.column_stack([sizes_y, scales]), errors_y, rcond=None
        )
    else:
        offset_x = float(np.mean(errors_x / sizes_x))
        offset_y = float(np.mean(errors_y / sizes_y))
        parallax_x = parallax_y = 0.0

    zero = Zero(
        offset=(float(offset_x), float(offset_y)),
        parallax=(float(parallax_x), float(parallax_y)),
        shots=len(shots),
    )
    return replace(zero, residual=_residual(zero, shots))


def _residual(zero: Zero, shots: Sequence[Shot]) -> float:
    squares = []
    for shot in shots:
        aim_x, aim_y = zero.aim_mm(shot.frame)
        target_x, target_y = shot.target_mm
        screen_width = shot.frame.screen_size_mm[0]
        squares.append(
            ((aim_x - target_x) / screen_width) ** 2
            + ((aim_y - target_y) / screen_width) ** 2
        )
    return math.sqrt(sum(squares) / len(squares))


# --- Persistence --------------------------------------------------------


def client_key(client_id: object, client_kind: str | None) -> str:
    """Which stored zero a session uses.

    The `hello`'s `id` when it is a plain token -- it becomes a key in a
    file and a word in the log -- else the client kind, so a device that
    sends no id still keeps its zero, shared with others of its kind.
    """
    if isinstance(client_id, str) and _CLIENT_ID.fullmatch(client_id):
        return client_id
    return client_kind or UNIDENTIFIED_KEY


class ZeroingStore:
    """Every client's zero, in one small JSON file.

    Read once at startup and written whole on each change, atomically,
    so a crash mid-write leaves the previous file. A file that cannot be
    read is logged and treated as empty: a lost zero costs a minute of
    shooting, a server that will not start costs the evening. `path`
    None keeps everything in memory.
    """

    def __init__(self, path: Path | None = DEFAULT_ZEROING_PATH) -> None:
        self._path = path
        self._zeros: dict[str, Zero] = {}
        if path is not None and path.exists():
            try:
                clients = json.loads(path.read_text())["clients"]
                self._zeros = {
                    str(key): Zero.from_dict(value) for key, value in clients.items()
                }
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                logger.warning("ignoring unreadable zeroing file %s: %s", path, error)
                self._zeros = {}

    def get(self, key: str) -> Zero | None:
        return self._zeros.get(key)

    def put(self, key: str, zero: Zero) -> None:
        self._zeros[key] = zero
        self._save()

    def delete(self, key: str) -> bool:
        if self._zeros.pop(key, None) is None:
            return False
        self._save()
        return True

    def _save(self) -> None:
        if self._path is None:
            return
        payload = {
            "version": 1,
            "clients": {key: zero.as_dict() for key, zero in self._zeros.items()},
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(
                dir=self._path.parent, prefix=".zeroing-", suffix=".json"
            )
            with os.fdopen(handle, "w") as file:
                json.dump(payload, file, indent=2)
            os.replace(temporary, self._path)
        except OSError as error:
            # Kept in memory for this run either way.
            logger.warning("could not save zeroing to %s: %s", self._path, error)


# --- The flow -----------------------------------------------------------


class TargetDisplay(Protocol):
    """What can put a target on the screen: the marker source controller."""

    @property
    def overlay_area(self) -> OverlayArea | None: ...

    def show_target(self, position: Point | None) -> bool: ...


class ZeroingService:
    """Server-wide: the store, the screen, and who is zeroing.

    One run at a time, because the overlay can show one target and the
    player can shoot one. Touched only from the event loop.
    """

    def __init__(self, store: ZeroingStore, display: TargetDisplay | None = None):
        self.store = store
        self._display = display
        self._owner: object | None = None

    def begin(self, owner: object) -> tuple[Target, ...] | None:
        """This run's targets, or None if someone else is zeroing."""
        if self._owner is not None and self._owner is not owner:
            return None
        self._owner = owner
        area = None if self._display is None else self._display.overlay_area
        return targets(area)

    def show(self, owner: object, target: Target | None) -> None:
        # Only drawable targets are sent: the display's own corners need
        # no drawing, and a target at a corner would cover a tag.
        if self._owner is not owner or self._display is None:
            return
        drawn = self._display.overlay_area is not None
        self._display.show_target(target.position if target and drawn else None)

    def end(self, owner: object) -> None:
        if self._owner is not owner:
            return
        self.show(owner, None)
        self._owner = None


class SessionZeroing:
    """One session's zero, and its zeroing run while there is one.

    `apply` receives the zero the session's aim should use from now on,
    whenever it changes.
    """

    def __init__(
        self, service: ZeroingService, apply: Callable[[Zero | None], None]
    ) -> None:
        self._service = service
        self._apply = apply
        self._key = UNIDENTIFIED_KEY
        self.zero: Zero | None = service.store.get(self._key)
        self._apply(self.zero)
        self._targets: tuple[Target, ...] | None = None
        self._shots: list[Shot] = []
        self._message: str | None = None

    @property
    def active(self) -> bool:
        return self._targets is not None

    @property
    def target(self) -> Target | None:
        if self._targets is None or len(self._shots) >= len(self._targets):
            return None
        return self._targets[len(self._shots)]

    def identify(self, client_id: object, client_kind: str | None) -> None:
        key = client_key(client_id, client_kind)
        if key == self._key:
            return
        self._key = key
        self._set(self._service.store.get(key))

    def control(self, action: object) -> None:
        if action == "start":
            self._start()
        elif action == "finish":
            self._finish()
        elif action == "cancel":
            if self.active:
                self._end()
                self._message = "zeroing cancelled; the previous zero is kept"
        elif action == "reset":
            if self.active:
                self._end()
            self._service.store.delete(self._key)
            self._set(None)
            self._message = "zero cleared; aiming with the camera centre"

    def shoot(self, frame: SightFrame | None) -> None:
        """A trigger press during a run, with the frame it named."""
        target = self.target
        if target is None:
            return
        if frame is None:
            self._message = "missed: no markers in view for that shot; shoot again"
            return
        self._shots.append(Shot(target, frame))
        self._message = f"shot {len(self._shots)} recorded"
        if self.target is None:
            self._finish()
        else:
            self._service.show(self, self.target)

    def close(self) -> None:
        if self.active:
            self._end()

    def status(self) -> dict:
        target = self.target
        return {
            "active": self.active,
            "zeroed": self.zero is not None,
            "target": (
                None
                if target is None
                else {
                    "label": target.label,
                    "index": len(self._shots),
                    "count": len(self._targets),
                    "optional": target.optional,
                }
            ),
            "shots": len(self._shots),
            "residual": (
                None
                if self.zero is None or self.zero.residual is None
                else round(self.zero.residual, 5)
            ),
            "message": self._message,
        }

    def _start(self) -> None:
        if self.active:
            self._end()
        run = self._service.begin(self)
        if run is None:
            self._message = "another client is zeroing; try again when it is done"
            return
        self._targets = run
        self._shots = []
        self._message = None
        self._service.show(self, self.target)

    def _finish(self) -> None:
        if not self.active:
            return
        if not self._shots:
            self._message = "shoot at least one target before finishing"
            return
        zero = fit(self._shots)
        self._end()
        self._service.store.put(self._key, zero)
        self._set(zero)
        self._message = (
            f"zeroed from {zero.shots} shot(s), "
            f"residual {zero.residual * 100:.2f}% of screen width"
            + ("" if zero.parallax == (0.0, 0.0) else ", parallax fitted")
        )
        logger.info("%s zeroed: %s", self._key, zero.as_dict())

    def _end(self) -> None:
        self._targets = None
        self._shots = []
        self._service.end(self)

    def _set(self, zero: Zero | None) -> None:
        self.zero = zero
        self._apply(zero)
