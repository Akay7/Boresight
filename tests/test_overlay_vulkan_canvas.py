"""The `.bsov` canvas format, byte for byte.

`canvas_format.py`'s docstring and `native/vulkan_overlay/src/
canvas_format.h`'s are two descriptions of the same wire format --
this test is what actually holds them to it, by checking the Python
writer's output against the layout the C header documents rather than
just against Python's own `unpack`.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from boresight.overlay import canvas_format


def test_pack_starts_with_the_documented_header() -> None:
    canvas = np.zeros((2, 3), dtype=np.uint8)
    data = canvas_format.pack(canvas, [(0, 0, 1, 1)])

    magic, version, width, height, rect_count, reserved = struct.unpack_from(
        "<4sIIIII", data
    )
    assert magic == b"BSOV"
    assert version == 1
    assert (width, height) == (3, 2)
    assert rect_count == 1
    assert reserved == 0


def test_pack_places_rectangles_right_after_the_header() -> None:
    canvas = np.zeros((4, 4), dtype=np.uint8)
    rectangles = [(1, 2, 3, 4), (5, 6, 7, 8)]
    data = canvas_format.pack(canvas, rectangles)

    header_size = struct.calcsize("<4sIIIII")
    first_rect = struct.unpack_from("<IIII", data, header_size)
    second_rect = struct.unpack_from("<IIII", data, header_size + 16)
    assert first_rect == rectangles[0]
    assert second_rect == rectangles[1]


def test_pack_places_pixels_after_the_rectangles_row_major() -> None:
    canvas = np.array([[0, 255], [255, 0]], dtype=np.uint8)
    data = canvas_format.pack(canvas, [])

    header_size = struct.calcsize("<4sIIIII")
    pixels = data[header_size:]
    assert pixels == bytes([0, 255, 255, 0])


def test_total_size_matches_header_plus_rects_plus_pixels() -> None:
    canvas = np.zeros((10, 20), dtype=np.uint8)
    rectangles = [(0, 0, 5, 5)] * 3
    data = canvas_format.pack(canvas, rectangles)

    header_size = struct.calcsize("<4sIIIII")
    expected = header_size + len(rectangles) * 16 + 10 * 20
    assert len(data) == expected


# --- Round-tripping (Python's own reader, for introspection/tests) ---


def test_unpack_is_the_inverse_of_pack() -> None:
    canvas = np.arange(12, dtype=np.uint8).reshape(3, 4)
    rectangles = [(0, 0, 2, 2), (2, 2, 2, 1)]

    restored_canvas, restored_rects = canvas_format.unpack(
        canvas_format.pack(canvas, rectangles)
    )

    assert np.array_equal(restored_canvas, canvas)
    assert restored_rects == rectangles


def test_write_file_round_trips_through_disk(tmp_path) -> None:
    canvas = np.full((5, 5), 255, dtype=np.uint8)
    rectangles = [(1, 1, 2, 2)]
    path = tmp_path / "canvas.bsov"

    canvas_format.write_file(path, canvas, rectangles)
    restored_canvas, restored_rects = canvas_format.unpack(path.read_bytes())

    assert np.array_equal(restored_canvas, canvas)
    assert restored_rects == rectangles


# --- Rejects what it should ------------------------------------------


def test_unpack_rejects_bad_magic() -> None:
    canvas = np.zeros((2, 2), dtype=np.uint8)
    data = bytearray(canvas_format.pack(canvas, []))
    data[0:4] = b"NOPE"

    with pytest.raises(ValueError, match="magic"):
        canvas_format.unpack(bytes(data))


def test_unpack_rejects_a_future_version() -> None:
    canvas = np.zeros((2, 2), dtype=np.uint8)
    data = bytearray(canvas_format.pack(canvas, []))
    struct.pack_into("<I", data, 4, 99)

    with pytest.raises(ValueError, match="version"):
        canvas_format.unpack(bytes(data))


def test_unpack_rejects_truncated_pixel_data() -> None:
    canvas = np.zeros((4, 4), dtype=np.uint8)
    data = canvas_format.pack(canvas, [])[:-4]

    with pytest.raises(ValueError, match="truncated"):
        canvas_format.unpack(data)


# --- Matches the real render_overlay output ---------------------------


def test_a_real_render_overlay_canvas_round_trips() -> None:
    """The format this module writes is what the layer will actually be
    handed in practice -- not a synthetic array."""
    from boresight.overlay.render import render_overlay

    canvas, rectangles = render_overlay((1920, 1080))

    restored_canvas, restored_rects = canvas_format.unpack(
        canvas_format.pack(canvas, rectangles)
    )

    assert np.array_equal(restored_canvas, canvas)
    assert restored_rects == rectangles
