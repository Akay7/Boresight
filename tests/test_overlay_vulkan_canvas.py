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


@pytest.mark.parametrize(
    "rect",
    [
        (4, 0, 2, 1),  # past the right edge
        (0, 4, 1, 2),  # past the bottom edge
        (0, 0, 0, 1),  # empty
        (0, 0, 1, 0),  # empty
        (-1, 0, 2, 2),  # negative origin, which the u32 field cannot hold
    ],
)
def test_write_file_refuses_a_rectangle_the_layer_would_reject(tmp_path, rect) -> None:
    canvas = np.zeros((5, 5), dtype=np.uint8)
    path = tmp_path / "canvas.bsov"

    with pytest.raises(ValueError, match="rectangle"):
        canvas_format.write_file(path, canvas, [(0, 0, 5, 5), rect])

    assert not path.exists()


def test_write_file_accepts_a_rectangle_touching_the_far_edges(tmp_path) -> None:
    canvas = np.zeros((5, 5), dtype=np.uint8)
    path = tmp_path / "canvas.bsov"

    canvas_format.write_file(path, canvas, [(3, 4, 2, 1)])

    assert canvas_format.unpack(path.read_bytes())[1] == [(3, 4, 2, 1)]


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


@pytest.mark.parametrize(
    "rect",
    [
        (3, 0, 2, 1),  # past the right edge
        (0, 3, 1, 2),  # past the bottom edge
        (0xFFFFFFFF, 0, 2, 1),  # x + w wraps in 32-bit arithmetic
        (0, 0, 0, 1),  # empty
        (0, 0, 1, 0),  # empty
    ],
)
def test_unpack_rejects_a_rectangle_outside_the_canvas(rect) -> None:
    canvas = np.zeros((4, 4), dtype=np.uint8)
    data = canvas_format.pack(canvas, [(0, 0, 4, 4), rect])

    with pytest.raises(ValueError, match="rectangle"):
        canvas_format.unpack(data)


def test_unpack_accepts_a_rectangle_touching_the_far_edges() -> None:
    canvas = np.zeros((4, 4), dtype=np.uint8)
    _canvas, rects = canvas_format.unpack(canvas_format.pack(canvas, [(2, 3, 2, 1)]))
    assert rects == [(2, 3, 2, 1)]


def test_unpack_rejects_truncated_rectangles() -> None:
    canvas = np.zeros((2, 2), dtype=np.uint8)
    data = canvas_format.pack(canvas, [(0, 0, 1, 1), (1, 1, 1, 1)])
    header_size = struct.calcsize("<4sIIIII")

    with pytest.raises(ValueError, match="truncated"):
        canvas_format.unpack(data[: header_size + 20])


def test_unpack_rejects_an_oversized_rect_count() -> None:
    canvas = np.zeros((2, 2), dtype=np.uint8)
    data = bytearray(canvas_format.pack(canvas, []))
    struct.pack_into("<I", data, 16, canvas_format.MAX_RECTS + 1)

    with pytest.raises(ValueError, match="rectangles"):
        canvas_format.unpack(bytes(data))


@pytest.mark.parametrize(
    "size",
    [
        (0, 2),
        (2, 0),
        (canvas_format.MAX_DIMENSION + 1, 1),
        (0xFFFFFFFF, 0xFFFFFFFF),
    ],
)
def test_unpack_rejects_an_out_of_range_canvas_size(size) -> None:
    canvas = np.zeros((2, 2), dtype=np.uint8)
    data = bytearray(canvas_format.pack(canvas, []))
    struct.pack_into("<II", data, 8, *size)

    with pytest.raises(ValueError, match="size"):
        canvas_format.unpack(bytes(data))


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
