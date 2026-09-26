"""LensModel point mapping and the calibration store."""

import json

import numpy as np
import pytest
from lens_render import CAMERA_MATRIX, DIST_COEFFS, IMAGE_SIZE

from boresight.lens import LensModel, LensStore, lens_key


def _lens(rms: float = 0.3) -> LensModel:
    return LensModel(CAMERA_MATRIX, DIST_COEFFS, IMAGE_SIZE, rms_px=rms, views=20)


def _grid() -> np.ndarray:
    xs, ys = np.meshgrid(np.linspace(0, 639, 9), np.linspace(0, 479, 7))
    return np.stack([xs.ravel(), ys.ravel()], axis=1)


def test_distort_then_undistort_is_identity() -> None:
    lens = _lens()
    points = _grid()
    round_trip = lens.undistort_points(lens.distort_points(points))
    assert np.abs(round_trip - points).max() < 0.01


def test_undistort_moves_edge_points_not_the_principal_point() -> None:
    lens = _lens()
    principal = (CAMERA_MATRIX[0, 2], CAMERA_MATRIX[1, 2])
    assert np.allclose(lens.undistort_point(principal), principal, atol=1e-6)
    # Barrel distortion pulls the frame corner inwards; undistorting it
    # pushes it well back out.
    corner = lens.undistort_point((0.0, 0.0))
    assert corner[0] < -10 and corner[1] < -10


def test_shape_is_preserved() -> None:
    lens = _lens()
    corners = _grid()[:4].reshape(4, 2).astype(np.float32)
    assert lens.undistort_points(corners).shape == (4, 2)


def test_key_includes_client_camera_and_size() -> None:
    assert lens_key("phone", "back", (1280, 720)) == "phone|back|1280x720"
    assert lens_key(None, None, (640, 480)) == "unidentified||640x480"


def test_store_persists_across_instances(tmp_path) -> None:
    path = tmp_path / "lenses.json"
    key = lens_key("phone", "back", IMAGE_SIZE)
    LensStore(path).put(key, _lens(0.42))

    reloaded = LensStore(path).get(key)
    assert reloaded is not None
    assert np.allclose(reloaded.camera_matrix, CAMERA_MATRIX)
    assert np.allclose(reloaded.dist_coeffs, DIST_COEFFS)
    assert reloaded.image_size == IMAGE_SIZE
    assert reloaded.rms_px == pytest.approx(0.42)


def test_store_lookup_is_exact_resolution(tmp_path) -> None:
    store = LensStore(tmp_path / "lenses.json")
    store.put(lens_key("phone", "back", (640, 480)), _lens())
    assert store.get(lens_key("phone", "back", (1280, 960))) is None
    assert store.get(lens_key("phone", "front", (640, 480))) is None


def test_put_replaces_same_key(tmp_path) -> None:
    store = LensStore(tmp_path / "lenses.json")
    key = lens_key("esp32-cam", None, (1024, 768))
    store.put(key, _lens(0.9))
    store.put(key, _lens(0.4))
    assert [entry["rms_px"] for entry in store.listing()] == [0.4]


@pytest.mark.parametrize(
    "content", ["not json", "[]", json.dumps({"k": {"camera_matrix": [1]}})]
)
def test_corrupt_store_is_empty_with_a_warning(tmp_path, caplog, content) -> None:
    path = tmp_path / "lenses.json"
    path.write_text(content)
    store = LensStore(path)
    assert store.listing() == []
    assert "ignoring lens calibrations" in caplog.text


def test_missing_store_is_empty(tmp_path) -> None:
    assert LensStore(tmp_path / "absent" / "lenses.json").listing() == []
