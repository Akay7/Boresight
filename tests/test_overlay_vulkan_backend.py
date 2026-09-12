"""Whether this machine can host the Vulkan present-overlay backend.

Mirrors `test_overlay_backend.py`'s shape: check the refusal path
without needing a real build or a real loader, by pointing the lookup
functions at fixtures instead of the real filesystem/library search.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from boresight.overlay import vulkan_backend
from boresight.overlay.backend import OverlayUnavailableError

# --- Layer directory discovery ----------------------------------------


def test_a_missing_build_is_refused(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("BORESIGHT_OVERLAY_LAYER_DIR", raising=False)
    monkeypatch.setattr(
        vulkan_backend, "_candidate_layer_dirs", lambda: [tmp_path / "nowhere"]
    )

    with pytest.raises(OverlayUnavailableError) as caught:
        vulkan_backend.find_layer_dir()

    message = str(caught.value)
    assert "not been built" in message
    assert "cmake" in message.lower()
    assert "printed markers" in message.lower()


def test_a_built_layer_is_found(tmp_path, monkeypatch) -> None:
    (tmp_path / vulkan_backend.LIBRARY_FILENAME).write_bytes(b"")
    (tmp_path / vulkan_backend.MANIFEST_FILENAME).write_bytes(b"{}")
    monkeypatch.setattr(vulkan_backend, "_candidate_layer_dirs", lambda: [tmp_path])

    assert vulkan_backend.find_layer_dir() == tmp_path


def test_the_env_var_override_is_tried(tmp_path, monkeypatch) -> None:
    (tmp_path / vulkan_backend.LIBRARY_FILENAME).write_bytes(b"")
    (tmp_path / vulkan_backend.MANIFEST_FILENAME).write_bytes(b"{}")
    monkeypatch.setenv("BORESIGHT_OVERLAY_LAYER_DIR", str(tmp_path))

    assert vulkan_backend.find_layer_dir() == tmp_path


def test_a_directory_with_only_the_library_is_not_enough(tmp_path, monkeypatch) -> None:
    """Half a build (or a stale manifest left behind) is still "not
    built" -- both files matter."""
    (tmp_path / vulkan_backend.LIBRARY_FILENAME).write_bytes(b"")
    monkeypatch.setattr(vulkan_backend, "_candidate_layer_dirs", lambda: [tmp_path])

    with pytest.raises(OverlayUnavailableError):
        vulkan_backend.find_layer_dir()


# --- Vulkan loader detection --------------------------------------------


def test_no_loader_anywhere_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(vulkan_backend.sys, "platform", "linux")

    def always_fails(_name):
        raise OSError("not found")

    monkeypatch.setattr(vulkan_backend.ctypes, "CDLL", always_fails)

    with pytest.raises(OverlayUnavailableError) as caught:
        vulkan_backend.find_vulkan_loader()

    message = str(caught.value).lower()
    assert "vulkan loader" in message
    assert "printed markers" in message


def test_a_loader_found_on_the_second_name_is_accepted(monkeypatch) -> None:
    monkeypatch.setattr(vulkan_backend.sys, "platform", "linux")

    calls = []

    def cdll(name):
        calls.append(name)
        if name == "libvulkan.so.1":
            raise OSError("nope")
        return object()

    monkeypatch.setattr(vulkan_backend.ctypes, "CDLL", cdll)

    vulkan_backend.find_vulkan_loader()  # must not raise

    assert calls == ["libvulkan.so.1", "libvulkan.so"]


# --- Canvas writing -----------------------------------------------------


def test_write_canvas_matches_render_overlay(tmp_path) -> None:
    from boresight.overlay.canvas_format import unpack
    from boresight.overlay.render import render_overlay

    screen = (1920, 1080)
    expected_canvas, expected_rects = render_overlay(screen)

    path = tmp_path / "canvas.bsov"
    vulkan_backend.write_canvas(path, screen)
    canvas, rects = unpack(path.read_bytes())

    assert np.array_equal(canvas, expected_canvas)
    assert rects == expected_rects


def test_default_canvas_path_is_keyed_by_resolution() -> None:
    a = vulkan_backend.default_canvas_path((1920, 1080))
    b = vulkan_backend.default_canvas_path((1280, 720))

    assert a != b
    assert "1920x1080" in a.name
    assert "1280x720" in b.name


# --- launch_env: the "enabled explicitly" mechanism ----------------------


def test_launch_env_sets_the_three_activation_variables(tmp_path) -> None:
    layer_dir = tmp_path / "build"
    canvas_path = tmp_path / "canvas.bsov"

    env = vulkan_backend.launch_env({}, layer_dir, canvas_path)

    assert env["VK_INSTANCE_LAYERS"] == vulkan_backend.LAYER_NAME
    assert env["VK_LAYER_PATH"] == str(layer_dir)
    assert env["BORESIGHT_OVERLAY_CANVAS"] == str(canvas_path)


def test_launch_env_does_not_mutate_the_base_environment(tmp_path) -> None:
    """The "enabled explicitly, per application" requirement rests on
    this: activating the layer for one launch must never leak into the
    environment of the process doing the launching, or any other."""
    base = dict(os.environ)
    original = dict(base)

    vulkan_backend.launch_env(base, tmp_path, tmp_path / "canvas.bsov")

    assert base == original
    assert "VK_INSTANCE_LAYERS" not in os.environ


def test_launch_env_appends_to_an_existing_layer_list(tmp_path) -> None:
    env = vulkan_backend.launch_env(
        {"VK_INSTANCE_LAYERS": "VK_LAYER_KHRONOS_validation"},
        tmp_path,
        tmp_path / "c.bsov",
    )

    assert env["VK_INSTANCE_LAYERS"] == (
        f"VK_LAYER_KHRONOS_validation:{vulkan_backend.LAYER_NAME}"
    )


def test_launch_env_appends_to_an_existing_layer_path(tmp_path) -> None:
    env = vulkan_backend.launch_env(
        {"VK_LAYER_PATH": "/some/other/dir"}, tmp_path, tmp_path / "c.bsov"
    )

    assert env["VK_LAYER_PATH"] == f"/some/other/dir{os.pathsep}{tmp_path}"


# --- The entry point -----------------------------------------------------


def test_the_entry_point_reports_rather_than_traces(monkeypatch, capsys) -> None:
    def refuse():
        raise OverlayUnavailableError("nope, and printed markers still work")

    monkeypatch.setattr(vulkan_backend, "check_supported", refuse)

    assert vulkan_backend.main(["--screen", "1920x1080"]) == 2
    assert "printed markers" in capsys.readouterr().err


def test_bad_screen_syntax_is_rejected() -> None:
    with pytest.raises(SystemExit):
        vulkan_backend.main(["--screen", "not-a-resolution"])
