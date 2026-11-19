"""The wiring table: every lead, where it runs, its plugs and its pins.

Every module meets the hub by one lead with a JST-XH plug at the hub's end.
The ESP32-CAM's leads push onto its own header pins; the Pi's onto its
header's odd pins and into its power port. The table is data: the bill of
materials prints it, the README quotes it, and the tests check it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from boresight_case.config import Config
from boresight_case.vendor import PI_SIGNAL_PINS, esp32_plug_pins

# A lead is cut to its path's length plus this, for the bends at its ends,
# then rounded up to the next 5 mm.
SLACK = 4.0
SHORT_LEADS = ("battery lead", "trigger lead", "feedback lead")
SHORT_MAX = 60.0  # mm: the battery, trigger and feedback leads


@dataclass(frozen=True)
class Lead:
    name: str
    module: str  # the module it belongs to, which it comes out of
    to: str
    plug: str  # at the module's end
    socket: str  # at the hub's end
    pins: tuple[str, ...]  # what each way carries, in order
    path: float  # its route through the gun, in mm

    @property
    def length(self) -> int:
        """The length to cut it to."""
        return int(math.ceil((self.path + SLACK) / 5.0) * 5)


FEEDBACK_PINS = {
    "esp32-cam": {
        "vibration": ("5V", "GND", "IO12 (drive)", "nc"),
        "solenoid": ("cells, switched and fused", "GND", "IO12 (drive)", "nc"),
        "lra": ("3V3", "GND", "IO14 (SDA)", "IO15 (SCL)"),
    },
    "pi-zero-2w": {
        "vibration": ("5V", "GND", "GPIO22 (drive, pin 15)", "nc"),
        "solenoid": (
            "cells, switched and fused",
            "GND",
            "GPIO22 (drive, pin 15)",
            "nc",
        ),
        "lra": ("3V3 (pin 1)", "GND", "SDA (pin 3)", "SCL (pin 5)"),
    },
}


def leads(cfg: Config) -> list[Lead]:
    """Every lead of `cfg`."""
    from boresight_case.assembly import lead_paths, path_length

    paths = {name: path_length(pts) for name, pts in lead_paths(cfg).items()}
    out = [
        Lead(
            "battery lead",
            "grip",
            "hub battery socket",
            "two spring contacts",
            "JST-XH 2",
            ("+ (cells)", "- (cells)"),
            paths["battery lead"],
        ),
        Lead(
            "trigger lead",
            "trigger",
            "hub trigger socket",
            "soldered to the switch",
            "JST-XH 2",
            ("switch", "GND"),
            paths["trigger lead"],
        ),
    ]
    if cfg.feedback != "none":
        out.append(
            Lead(
                "feedback lead",
                f"feedback ({cfg.feedback})",
                "hub feedback socket",
                "soldered to the driver",
                "JST-XH 4",
                FEEDBACK_PINS[cfg.board][cfg.feedback],
                paths["feedback lead"],
            )
        )
    if cfg.buttons:
        out.append(
            Lead(
                "buttons lead",
                "buttons",
                "hub buttons socket",
                "soldered to the buttons",
                "JST-XH 3",
                ("GPIO4 (Start, pin 7)", "GPIO10 (Select, pin 19)", "GND"),
                paths["buttons lead"],
            )
        )
    if cfg.board == "esp32-cam":
        out.append(
            Lead(
                "board lead",
                "nose",
                "hub esp32-cam socket",
                "Dupont 1x6 on header row +1, pins 1-6",
                "JST-XH 6",
                esp32_plug_pins("hub"),
                paths["board lead"],
            )
        )
        out.append(
            Lead(
                "debug lead",
                "nose",
                "the debug board",
                "Dupont 1x6 on header row -1, pins 3-8",
                "soldered to the debug board",
                tuple(
                    f"{p} -> {d}"
                    for p, d in zip(
                        esp32_plug_pins("debug"),
                        (
                            "BOOT",
                            "GND",
                            "nc (VCC is an output)",
                            "socket RX",
                            "socket TX",
                            "socket GND",
                        ),
                        strict=True,
                    )
                ),
                25.0,
            )
        )
    else:
        out.append(
            Lead(
                "Pi signal lead",
                "sled",
                "hub pi signal socket",
                "Dupont 1x10 on the header's odd pins 1-19",
                "JST-XH 10",
                tuple(f"pin {n}: {s}" for n, s in PI_SIGNAL_PINS.items()),
                paths["Pi signal lead"],
            )
        )
        out.append(
            Lead(
                "Pi power lead",
                "sled",
                "hub pi power socket",
                "right-angle micro-USB into the PWR port",
                "JST-XH 2",
                ("5V", "GND"),
                paths["Pi power lead"],
            )
        )
    return out


def markdown_table(cfg: Config) -> list[str]:
    rows = [
        "| Lead | From | To | Plug | At the hub | Ways | Cut to |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for lead in leads(cfg):
        rows.append(
            f"| {lead.name} | {lead.module} | {lead.to} | {lead.plug} | "
            f"{lead.socket} | "
            f"{'; '.join(lead.pins)} | {lead.length} mm |"
        )
    return rows
