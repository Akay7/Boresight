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


def pack(canvas: np.ndarray, rectangles: list[tuple[int, int, int, int]]) -> bytes:
    """Serialize a rendered canvas + rectangles to the `.bsov` wire format."""
    height, width = canvas.shape
    header = _HEADER.pack(MAGIC, VERSION, width, height, len(rectangles), 0)
    rects = b"".join(_RECT.pack(*rect) for rect in rectangles)
    pixels = np.ascontiguousarray(canvas, dtype=np.uint8).tobytes()
    return header + rects + pixels


def unpack(data: bytes) -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    """The inverse of `pack`.

    Exists for tests and introspection -- the layer itself has its own
    C reader, `bsov_load`, and never goes through this function.
    """
    if len(data) < _HEADER.size:
        raise ValueError("truncated .bsov data: shorter than the header")

    magic, version, width, height, rect_count, _reserved = _HEADER.unpack_from(data)
    if magic != MAGIC:
        raise ValueError(f"not a .bsov canvas: bad magic {magic!r}")
    if version != VERSION:
        raise ValueError(f"unsupported .bsov version {version}")

    offset = _HEADER.size
    rectangles: list[tuple[int, int, int, int]] = []
    for _ in range(rect_count):
        rectangles.append(_RECT.unpack_from(data, offset))
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
