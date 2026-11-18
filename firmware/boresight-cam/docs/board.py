"""The ESP32-CAM as the wiring diagrams draw it, shared by flashing.py and
trigger.py.

The board is one box with its two 8-pin header rows down its two sides,
seen from the front (the camera side) with the SD-card slot at the top,
as in Random Nerd Tutorials' pinout: 5V and 3V3 face each other at the
top. The rows' order is the one AI-Thinker's schematic gives headers P2
and P1. Its pins' anchors are A1-A8 up the left row and B1-B8 up the
right, counted from the bottom.
"""

from itertools import pairwise
from pathlib import Path

import schemdraw
import schemdraw.elements as elm

CAM_SPACING = 0.7
LEAD = 0.5
WIRE_WIDTH = 3

RED = "#d62728"
BLACK = "#222222"
YELLOW = "#e0b000"
GREEN = "#2ca02c"
BLUE = "#1f77b4"
GREY = "#999999"

# The board's rows, each listed from the bottom up.
LEFT_ROW = ["IO4", "IO2", "IO14", "IO15", "IO13", "IO12", "GND", "5V"]
RIGHT_ROW = ["GND", "U0T", "U0R", "VCC", "GND", "IO0", "IO16", "3V3"]


def esp32_cam(drawing) -> dict:
    """Add the board at the origin; returns its pins' absolute anchors."""
    cam = elm.Ic(
        pins=[
            elm.IcPin(name=n, side="left", slot=f"{i + 1}/8", anchorname=f"A{i + 1}")
            for i, n in enumerate(LEFT_ROW)
        ]
        + [
            elm.IcPin(name=n, side="right", slot=f"{i + 1}/8", anchorname=f"B{i + 1}")
            for i, n in enumerate(RIGHT_ROW)
        ],
        size=(5.0, 8 * CAM_SPACING + 0.5),
        leadlen=LEAD,
    ).at((0, 0))
    cam.label("ESP32-CAM\nAI-Thinker\n\nfront view,\nSD slot\nat the top", loc="center")
    drawing += cam
    return cam.absanchors


def left(anchors: dict, name: str):
    """The left row's pin called `name`."""
    return anchors[f"A{LEFT_ROW.index(name) + 1}"]


def right(anchors: dict, name: str, nth: int = 0):
    """The right row's pin called `name`, the `nth` from the bottom (it
    has two GNDs)."""
    slots = [i for i, pin in enumerate(RIGHT_ROW) if pin == name]
    return anchors[f"B{slots[nth] + 1}"]


def wire(drawing, *points, color) -> None:
    """A wire through `points`, in straight segments."""
    for start, end in pairwise(points):
        drawing += elm.Line().at(start).to(end).color(color).linewidth(WIRE_WIDTH)


def render(draw, path: Path) -> None:
    """Draw to the SVG at `path`, white behind it."""
    schemdraw.use("svg")
    with schemdraw.Drawing(file=str(path), show=False) as d:
        # White, not transparent: GitHub's dark theme would hide black lines.
        d.config(fontsize=12, font="Arial", bgcolor="white", lw=1.5)
        draw(d)
    # schemdraw leaves the last line open; the end-of-file hook would
    # otherwise rewrite the file after every run.
    text = path.read_text()
    if not text.endswith("\n"):
        path.write_text(text + "\n")
