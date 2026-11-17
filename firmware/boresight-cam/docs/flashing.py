"""Draw flashing.svg: an ESP32-CAM wired to a USB-serial adapter.

From the repository root:

    uv run --no-project --with schemdraw==0.23 \
        python firmware/boresight-cam/docs/flashing.py

The board is one box with its two 8-pin header rows down its two sides,
camera end up, as it lies on the bench. Each row is in the order
AI-Thinker's datasheet gives it, from the end nearest the 5V pin.
"""

from pathlib import Path

import schemdraw
import schemdraw.elements as elm

CAM_SPACING = 0.7
ADAPTER_SPACING = 1.1
LEAD = 0.5
WIRE_WIDTH = 3

RED = "#d62728"
BLACK = "#222222"
YELLOW = "#e0b000"
GREEN = "#2ca02c"
BLUE = "#1f77b4"
GREY = "#999999"

# The board's rows, each listed from the bottom up.
LEFT_ROW = ["5V", "GND", "IO12", "IO13", "IO15", "IO14", "IO2", "IO4"]
RIGHT_ROW = ["GND", "U0T", "U0R", "VCC", "GND", "IO0", "IO16", "3V3"]
# The adapter's pins along its top edge, left to right: ordered so that
# no two wires cross on their way round the board.
ADAPTER = ["GND", "5V", "3V3", "BOOT", "EN", "RX", "TX"]
UNUSED = {"3V3", "BOOT", "EN"}
# What to do with the wiring is in the READMEs, next to the picture.


def route(drawing, start, level, lane, end, color) -> None:
    """Up from an adapter pin to `level`, across to `lane`, up to the
    board pin's height, then in to the pin."""
    corner = (lane, level)
    drawing += elm.Wire("|-").at(start).to(corner).color(color).linewidth(WIRE_WIDTH)
    drawing += elm.Wire("|-").at(corner).to(end).color(color).linewidth(WIRE_WIDTH)


def draw(path: Path) -> None:
    schemdraw.use("svg")
    with schemdraw.Drawing(file=str(path), show=False) as d:
        # White, not transparent: GitHub's dark theme would hide black lines.
        d.config(fontsize=12, font="Arial", bgcolor="white", lw=1.5)

        cam = elm.Ic(
            pins=[
                elm.IcPin(
                    name=n, side="left", slot=f"{i + 1}/8", anchorname=f"A{i + 1}"
                )
                for i, n in enumerate(LEFT_ROW)
            ]
            + [
                elm.IcPin(
                    name=n, side="right", slot=f"{i + 1}/8", anchorname=f"B{i + 1}"
                )
                for i, n in enumerate(RIGHT_ROW)
            ],
            size=(5.0, 8 * CAM_SPACING + 0.5),
            leadlen=LEAD,
        ).at((0, 0))
        cam.label("ESP32-CAM\nAI-Thinker\n\ncamera end up", loc="center")
        d += cam
        a = cam.absanchors

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
            .anchor("GND")
        )
        adapter.label(
            "USB-serial adapter\n3.3 V logic\nUSB to the PC",
            loc="center",
            ofst=(0, -0.5),
        )
        d += adapter
        p = adapter.absanchors

        pin_top = p["GND"].y
        low, high = pin_top + 0.7, pin_top + 1.3
        left_out, left_in = a["A1"].x - 1.0, a["A1"].x - 0.5
        right_in, right_out = a["B1"].x + 0.5, a["B1"].x + 1.0

        # Outer wire on the lower level, inner on the higher: none cross.
        # TX and RX cross over: the adapter's TX is the board's receive line.
        route(d, p["GND"], low, left_out, a["A2"], BLACK)
        route(d, p["5V"], high, left_in, a["A1"], RED)
        route(d, p["RX"], high, right_in, a["B2"], GREEN)
        route(d, p["TX"], low, right_out, a["B3"], YELLOW)

        d += (
            elm.Arc2(k=-0.8)
            .at(a["B5"])
            .to(a["B6"])
            .color(BLUE)
            .linewidth(WIRE_WIDTH)
            .label("jumper,\nflashing only", loc="bot", ofst=0.35, color=BLUE)
        )


def main() -> None:
    path = Path(__file__).with_suffix(".svg")
    draw(path)
    # schemdraw leaves the last line open; the end-of-file hook would
    # otherwise rewrite the file after every run.
    text = path.read_text()
    if not text.endswith("\n"):
        path.write_text(text + "\n")


if __name__ == "__main__":
    main()
