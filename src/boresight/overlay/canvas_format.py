"""The `.bsov` canvas handoff format.

`render_overlay` returns a numpy canvas and a Python list of
rectangles -- exactly what the Qt backend consumes directly, in-process.
The Vulkan present-overlay layer runs as C code inside a different
process (the game's), so those two have to cross a process boundary
through a file instead, in a format each side reads unambiguously.
That format is `.bsov`, and this module is one of its two
implementations -- the other is
`native/vulkan_overlay/src/canvas_format.h`'s reader, which this
module's docstring and `tests/test_overlay_vulkan_canvas.py` keep
honest against.

Layout, little-endian throughout (the only endianness either side runs
on):

    header   4s   magic       b"BSOV"
             I    version     1
             I    width       canvas width, pixels
             I    height      canvas height, pixels
             I    rect_count  number of rectangles that follow
             I    reserved    0

    rects    rect_count * (I x, I y, I w, I h)

    pixels   width * height bytes, row-major, one grayscale byte per
             pixel -- exactly `render_overlay`'s canvas, `tobytes()`'d
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

MAGIC = b"BSOV"
VERSION = 1

_HEADER = struct.Struct("<4sIIIII")
_RECT = struct.Struct("<IIII")

# Sanity bounds, mirroring BSOV_MAX_DIMENSION / BSOV_MAX_RECTS in
# canvas_format.h -- the layer rejects anything outside them, so this
# reader does too, keeping the two in agreement on what a valid file is.
MAX_DIMENSION = 16384
MAX_RECTS = 4096


def pack(canvas: np.ndarray, rectangles: list[tuple[int, int, int, int]]) -> bytes:
    """Serialize a rendered canvas + rectangles to the `.bsov` wire format."""
    height, width = canvas.shape
    header = _HEADER.pack(MAGIC, VERSION, width, height, len(rectangles), 0)
    rects = b"".join(_RECT.pack(*rect) for rect in rectangles)
    pixels = np.ascontiguousarray(canvas, dtype=np.uint8).tobytes()
    return header + rects + pixels


def unpack(data: bytes) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    """The inverse of `pack`, with the same validation as the C reader.

    Exists for tests and introspection -- the layer itself has its own
    C reader, `bsov_load`, and never goes through this function. It
    rejects exactly what `bsov_load` rejects: width/height outside
    `1..MAX_DIMENSION`, more than `MAX_RECTS` rectangles, data shorter
    than the header declares, and any rectangle that is empty or not
    entirely inside the canvas. `pack` itself stays permissive.
    """
    if len(data) < _HEADER.size:
        raise ValueError("truncated .bsov data: shorter than the header")

    magic, version, width, height, rect_count, _reserved = _HEADER.unpack_from(data)
    if magic != MAGIC:
        raise ValueError(f"not a .bsov canvas: bad magic {magic!r}")
    if version != VERSION:
        raise ValueError(f"unsupported .bsov version {version}")

    if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
        raise ValueError(f"invalid .bsov canvas size {width}x{height}")
    if rect_count > MAX_RECTS:
        raise ValueError(f"too many .bsov rectangles: {rect_count}")

    offset = _HEADER.size
    if len(data) < offset + rect_count * _RECT.size:
        raise ValueError("truncated .bsov data: fewer rectangles than rect_count")
    rectangles: list[tuple[int, int, int, int]] = []
    for _ in range(rect_count):
        x, y, w, h = _RECT.unpack_from(data, offset)
        # Python ints don't overflow, so `x + w` here is exactly the
        # overflow-free comparison the C side does by subtraction.
        if w == 0 or h == 0 or x + w > width or y + h > height:
            raise ValueError(
                f"invalid .bsov rectangle {(x, y, w, h)} for a {width}x{height} canvas"
            )
        rectangles.append((x, y, w, h))
        offset += _RECT.size

    pixel_count = width * height
    pixels = data[offset : offset + pixel_count]
    if len(pixels) != pixel_count:
        raise ValueError("truncated .bsov data: fewer pixels than width*height")
    canvas = np.frombuffer(pixels, dtype=np.uint8).reshape((height, width))
    return canvas, rectangles


def write_file(
    path: Path, canvas: np.ndarray, rectangles: list[tuple[int, int, int, int]]
) -> None:
    """Write `canvas`/`rectangles` to `path` in the `.bsov` format."""
    path.write_bytes(pack(canvas, rectangles))
