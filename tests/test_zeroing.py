"""Zeroing against a synthetic pinhole camera with a misaligned barrel.

The camera is exact; the barrel is tilted relative to it and offset
beside it. A "shot" is a pose whose barrel hits a known point, and the
test is whether the correction fitted from a few such shots puts the
aim where the barrel hits from poses it never saw.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from boresight.zeroing import (
    PARALLAX_MIN_SPREAD,
    UNIDENTIFIED_KEY,
    SessionZeroing,
    Shot,
    SightFrame,
    Target,
    Zero,
    ZeroingService,
    ZeroingStore,
    client_key,
    fit,
    targets,
)

SCREEN_MM = (1000.0, 560.0)
IMAGE_PX = (1280, 720)
FOCAL_PX = 1000.0


class Gun:
    """A camera plus a barrel `tilt_deg` off its axis and `offset_mm` beside it."""

    def __init__(self, tilt_deg=(0.0, 0.0), offset_mm=(0.0, 0.0)) -> None:
        direction = np.array(
            [
                math.tan(math.radians(tilt_deg[0])),
                math.tan(math.radians(tilt_deg[1])),
                1,
            ]
        )
        self.direction = direction / np.linalg.norm(direction)
        self.offset = np.array([offset_mm[0], offset_mm[1], 0.0])

    def pose(
        self, position_mm, looking_at_mm
    ) -> tuple[SightFrame, tuple[float, float]]:
        """The frame from `position_mm`, camera axis on `looking_at_mm`,
        and where the barrel hits the screen from there."""
        centre = np.array(position_mm, dtype=np.float64)
        forward = np.array([*looking_at_mm, 0.0]) - centre
        forward /= np.linalg.norm(forward)
        right = np.cross([0.0, 1.0, 0.0], forward)
        right /= np.linalg.norm(right)
        down = np.cross(forward, right)
        rotation = np.array([right, down, forward])

        intrinsics = np.array(
            [[FOCAL_PX, 0, IMAGE_PX[0] / 2], [0, FOCAL_PX, IMAGE_PX[1] / 2], [0, 0, 1]]
        )
        homography = intrinsics @ np.column_stack(
            [rotation[:, 0], rotation[:, 1], -rotation @ centre]
        )

        origin = centre + rotation.T @ self.offset
        direction = rotation.T @ self.direction
        reach = -origin[2] / direction[2]
        hit = origin + reach * direction
        frame = SightFrame(homography / homography[2, 2], IMAGE_PX, SCREEN_MM)
        return frame, (float(hit[0]), float(hit[1]))


def _shot(gun: Gun, distance_mm: float, aim_mm) -> Shot:
    frame, hit = gun.pose((aim_mm[0], aim_mm[1], -distance_mm), aim_mm)
    target = Target("t", (hit[0] / SCREEN_MM[0], hit[1] / SCREEN_MM[1]))
    return Shot(target, frame)


CORNERS = [(150, 85), (850, 85), (850, 475), (150, 475), (500, 280)]


def _worst_error(gun: Gun, zero: Zero | None) -> float:
    """Largest miss, in mm, over poses the fit never saw."""
    worst = 0.0
    for position, look in [
        ((200, 100, -1200), (300, 200)),
        ((900, 500, -3500), (700, 300)),
        ((-400, 280, -2500), (450, 250)),
        ((500, 0, -1600), (800, 450)),
    ]:
        frame, hit = gun.pose(position, look)
        aim = frame.to_screen(frame.centre_px) if zero is None else zero.aim_mm(frame)
        worst = max(worst, math.dist(aim, hit))
    return worst


def test_no_correction_aims_with_the_image_centre() -> None:
    frame, _ = Gun().pose((300, 200, -2000), (400, 250))

    assert Zero().aim_mm(frame) == pytest.approx(frame.to_screen(frame.centre_px))
    assert frame.to_screen(frame.centre_px) == pytest.approx((400, 250))


def test_scale_is_focal_over_distance_for_a_square_view() -> None:
    frame, _ = Gun().pose((500, 280, -2000), (500, 280))

    assert frame.scale((500, 280)) == pytest.approx(FOCAL_PX / 2000 * SCREEN_MM[0])


def test_a_tilt_zeroed_at_one_distance_holds_at_others() -> None:
    gun = Gun(tilt_deg=(1.5, -1.0))
    zero = fit([_shot(gun, 2000, aim) for aim in CORNERS])

    assert zero.parallax == (0.0, 0.0)
    assert _worst_error(gun, None) > 30.0
    assert _worst_error(gun, zero) < 2.0
    assert zero.residual < 0.002


def test_parallax_is_fitted_from_two_distances() -> None:
    gun = Gun(tilt_deg=(1.0, 0.5), offset_mm=(0.0, 40.0))
    shots = [_shot(gun, 2000, aim) for aim in CORNERS]
    shots.append(_shot(gun, 1200, CORNERS[-1]))

    zero = fit(shots)

    assert zero.parallax[0] == pytest.approx(0.0, abs=0.002)
    assert zero.parallax[1] * SCREEN_MM[0] == pytest.approx(40.0, rel=0.1)
    assert _worst_error(gun, zero) < 3.0


def test_parallax_left_unfitted_costs_little_at_the_zeroing_distance() -> None:
    gun = Gun(offset_mm=(0.0, 40.0))
    zero = fit([_shot(gun, 2000, aim) for aim in CORNERS])

    frame, hit = gun.pose((500, 280, -2000), (500, 280))
    assert zero.parallax == (0.0, 0.0)
    assert math.dist(zero.aim_mm(frame), hit) < 1.0


def test_one_shot_is_enough_for_an_offset() -> None:
    gun = Gun(tilt_deg=(2.0, 0.0))
    zero = fit([_shot(gun, 2000, (500, 280))])

    assert zero.shots == 1
    assert zero.offset[0] * IMAGE_PX[0] == pytest.approx(
        FOCAL_PX * math.tan(math.radians(2.0)), rel=0.01
    )


def test_fitting_nothing_is_an_error() -> None:
    with pytest.raises(ValueError):
        fit([])


def test_the_parallax_spread_threshold_is_meaningful() -> None:
    assert 1.1 < PARALLAX_MIN_SPREAD < 2.0


# --- Targets ------------------------------------------------------------


def test_without_the_overlay_the_targets_are_the_display_corners() -> None:
    shown = targets(None)

    assert [t.position for t in shown[:4]] == [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert shown[-1].optional and not any(t.optional for t in shown[:-1])


def test_overlay_targets_sit_inside_its_area() -> None:
    screen, area = (1920, 1080), (0, 0, 1920, 1034)
    shown = targets((screen, area))

    assert len(shown) == 6 and shown[-1].optional
    for target in shown:
        x, y = target.position
        assert 0.1 < x < 0.9
        assert 0.1 < y * 1080 / 1034 < 0.9
    assert shown[4].position == pytest.approx((0.5, 517 / 1080))


# --- Storage ------------------------------------------------------------


def test_client_key_prefers_a_plain_id() -> None:
    assert client_key("a1B2-c_3", "phone") == "a1B2-c_3"
    assert client_key("../etc/passwd", "phone") == "phone"
    assert client_key("x" * 65, "phone") == "phone"
    assert client_key(42, None) == UNIDENTIFIED_KEY


def test_the_store_round_trips(tmp_path) -> None:
    path = tmp_path / "state" / "zeroing.json"
    zero = Zero(offset=(0.01, -0.02), parallax=(0.0, 0.04), shots=5, residual=0.001)

    ZeroingStore(path).put("phone-1", zero)

    assert ZeroingStore(path).get("phone-1") == zero
    assert json.loads(path.read_text())["version"] == 1


def test_the_store_deletes(tmp_path) -> None:
    path = tmp_path / "zeroing.json"
    store = ZeroingStore(path)
    store.put("a", Zero(offset=(0.1, 0.0)))

    assert store.delete("a") is True
    assert store.delete("a") is False
    assert ZeroingStore(path).get("a") is None


@pytest.mark.parametrize("content", ["not json", "[]", '{"clients": {"a": 3}}'])
def test_an_unreadable_store_is_empty(tmp_path, content) -> None:
    path = tmp_path / "zeroing.json"
    path.write_text(content)

    assert ZeroingStore(path).get("a") is None


# --- The flow -------------------------------------------------------------


class FakeDisplay:
    def __init__(self, overlay=None) -> None:
        self.overlay_area = overlay
        self.shown: list = []

    def show_target(self, position) -> bool:
        self.shown.append(position)
        return True


def _session(service: ZeroingService) -> tuple[SessionZeroing, list]:
    applied: list = []
    return SessionZeroing(service, applied.append), applied


def _frame() -> SightFrame:
    frame, _ = Gun(tilt_deg=(1.0, 0.0)).pose((500, 280, -2000), (500, 280))
    return frame


def test_a_run_walks_the_targets_and_saves_a_zero() -> None:
    display = FakeDisplay(((1920, 1080), (0, 0, 1920, 1080)))
    service = ZeroingService(ZeroingStore(None), display)
    session, applied = _session(service)
    session.identify("phone-1", "phone")

    session.control("start")
    assert session.status()["target"]["index"] == 0
    assert display.shown[-1] == pytest.approx((0.15, 0.15))

    session.shoot(None)
    assert session.status()["shots"] == 0
    assert "missed" in session.status()["message"]

    for _ in range(6):
        session.shoot(_frame())

    status = session.status()
    assert status["active"] is False and status["zeroed"] is True
    assert status["residual"] is not None
    assert display.shown[-1] is None
    assert applied[-1] == service.store.get("phone-1")
    assert applied[-1].shots == 6


def test_the_display_corners_are_not_drawn() -> None:
    display = FakeDisplay(None)
    session, _ = _session(ZeroingService(ZeroingStore(None), display))

    session.control("start")

    assert display.shown == [None]


def test_only_one_session_zeroes_at_a_time() -> None:
    service = ZeroingService(ZeroingStore(None), FakeDisplay())
    first, _ = _session(service)
    second, _ = _session(service)

    first.control("start")
    second.control("start")

    assert first.active and not second.active
    assert "another client" in second.status()["message"]

    first.close()
    second.control("start")
    assert second.active


def test_finishing_needs_a_shot() -> None:
    session, applied = _session(ZeroingService(ZeroingStore(None)))
    session.control("start")

    session.control("finish")

    assert session.active and applied == [None]
    assert "at least one" in session.status()["message"]


def test_finishing_early_fits_what_there_is() -> None:
    session, applied = _session(ZeroingService(ZeroingStore(None)))
    session.control("start")
    session.shoot(_frame())

    session.control("finish")

    assert not session.active and applied[-1].shots == 1


def test_cancel_keeps_the_previous_zero() -> None:
    store = ZeroingStore(None)
    old = Zero(offset=(0.02, 0.0))
    store.put(UNIDENTIFIED_KEY, old)
    session, applied = _session(ZeroingService(store))
    assert applied == [old]

    session.control("start")
    session.shoot(_frame())
    session.control("cancel")

    assert session.zero == old and store.get(UNIDENTIFIED_KEY) == old


def test_reset_forgets_the_zero() -> None:
    store = ZeroingStore(None)
    store.put("p", Zero(offset=(0.02, 0.0)))
    session, applied = _session(ZeroingService(store))
    session.identify("p", "phone")

    session.control("reset")

    assert applied[-1] is None and store.get("p") is None
    assert session.status()["zeroed"] is False


def test_identifying_loads_that_clients_zero() -> None:
    store = ZeroingStore(None)
    store.put("esp32-cam", Zero(offset=(0.0, 0.03)))
    session, applied = _session(ZeroingService(store))

    session.identify(None, "esp32-cam")

    assert applied[-1] == Zero(offset=(0.0, 0.03))
