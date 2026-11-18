"""Draw flashing.svg: an ESP32-CAM wired to a USB-serial adapter.

From the repository root:

    uv run --no-project --with schemdraw==0.23 \
        python firmware/boresight-cam/docs/flashing.py

The board is drawn by board.py, as in the other wiring diagram.
"""

from pathlib import Path

import schemdraw.elements as elm
from board import (
    BLACK,
    BLUE,
    GREEN,
    GREY,
    LEAD,
    RED,
    WIRE_WIDTH,
    YELLOW,
    esp32_cam,
    left,
    render,
    right,
)

ADAPTER_SPACING = 1.1
# The adapter's pins along its top edge, left to right: ordered so that
# no two wires cross on their way round the board.
ADAPTER = ["5V", "GND", "3V3", "BOOT", "EN", "RX", "TX"]
UNUSED = {"3V3", "BOOT", "EN"}
# What to do with the wiring is in the READMEs, next to the picture.


def route(drawing, start, level, lane, end, color) -> None:
    """Up from an adapter pin to `level`, across to `lane`, up to the
    board pin's height, then in to the pin."""
    corner = (lane, level)
    drawing += elm.Wire("|-").at(start).to(corner).color(color).linewidth(WIRE_WIDTH)
    drawing += elm.Wire("|-").at(corner).to(end).color(color).linewidth(WIRE_WIDTH)


def draw(d) -> None:
    a = esp32_cam(d)

    # Centred under the board, its pin ends 2.6 below the board's.
    centre = (a["A1"].x + a["B1"].x) / 2
    first_pin = (centre - 3 * ADAPTER_SPACING, a["A1"].y - 0.5 - 2.6)
    adapter = (
        elm.Ic(
            pins=[
                elm.IcPin(
                    name=n,
                    side="top",
                    slot=f"{i + 1}/7",
                    anchorname=n,
                    color=GREY if n in UNUSED else None,
                )
                for i, n in enumerate(ADAPTER)
            ],
            size=(7 * ADAPTER_SPACING + 0.4, 2.6),
            leadlen=LEAD,
        )
        .at(first_pin)
        .anchor("5V")
    )
    adapter.label(
        "USB-serial adapter\n3.3 V logic\nUSB to the PC",
        loc="center",
        ofst=(0, -0.5),
    )
    d += adapter
    p = adapter.absanchors

    pin_top = p["5V"].y
    low, high = pin_top + 0.7, pin_top + 1.3
    left_out, left_in = a["A1"].x - 1.0, a["A1"].x - 0.5
    right_in, right_out = a["B1"].x + 0.5, a["B1"].x + 1.0

    # Outer wire on the lower level, inner on the higher: none cross.
    # TX and RX cross over: the adapter's TX is the board's receive line.
    route(d, p["5V"], low, left_out, left(a, "5V"), RED)
    route(d, p["GND"], high, left_in, left(a, "GND"), BLACK)
    route(d, p["RX"], high, right_in, right(a, "U0T"), GREEN)
    route(d, p["TX"], low, right_out, right(a, "U0R"), YELLOW)

    d += (
        elm.Arc2(k=-0.8)
        .at(right(a, "GND", 1))
        .to(right(a, "IO0"))
        .color(BLUE)
        .linewidth(WIRE_WIDTH)
        .label("jumper,\nflashing only", loc="bot", ofst=0.35, color=BLUE)
    )


if __name__ == "__main__":
    render(draw, Path(__file__).with_suffix(".svg"))
