"""Draw trigger.svg: the trigger button wired to an ESP32-CAM.

From the repository root:

    uv run --no-project --with schemdraw==0.23 \
        python firmware/boresight-cam/docs/trigger.py

Two wires and the button, nothing else: the firmware turns on GPIO13's
internal pull-up, so no resistor. The board is drawn by board.py, as in
the flashing diagram; what to do with the wiring is in the READMEs.
"""

from pathlib import Path

import schemdraw.elements as elm
from board import BLACK, GREEN, WIRE_WIDTH, esp32_cam, render, wire

LANE = 1.0  # out from the pin ends to the wires' turn
REACH = 2.4  # out from the pin ends to the button
OVERHANG = 0.8  # how far the button's ends stand past the two pins


def draw(d) -> None:
    a = esp32_cam(d)
    io13, gnd = a["A4"], a["A2"]
    lane, button = io13.x - LANE, io13.x - REACH
    top, bottom = io13.y + OVERHANG, gnd.y - OVERHANG

    # Out from each pin, then away from the other so the button stands
    # clear of the header, then across to its ends.
    wire(d, io13, (lane, io13.y), (lane, top), (button, top), color=GREEN)
    wire(d, gnd, (lane, gnd.y), (lane, bottom), (button, bottom), color=BLACK)
    d += (
        elm.Button()
        .at((button, top))
        .to((button, bottom))
        .linewidth(WIRE_WIDTH)
        .label("trigger\nbutton", loc="top", ofst=0.3)
    )


if __name__ == "__main__":
    render(draw, Path(__file__).with_suffix(".svg"))
