"""The bill of materials: what to print and what to buy for a configuration."""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass

from boresight_case.assembly import Assembly
from boresight_case.vendor import CONSUMABLES, VENDOR


@dataclass(frozen=True)
class Line:
    kind: str  # "print", "buy" or "consumable"
    name: str
    count: int
    spec: str


def lines(a: Assembly) -> list[Line]:
    out = [
        Line(
            "print",
            p.name,
            p.count,
            f"{p.material}, {p.perimeters} perimeters, {p.infill}% infill",
        )
        for p in a.printed.values()
    ]
    counts = Counter(b.key for b in a.bought)
    for key in sorted(counts):
        out.append(Line("buy", key, counts[key], VENDOR[key].spec))
    cfg = a.config
    consumables = ["hookup-wire"]
    if cfg.board == "pi-zero-2w":
        consumables.append("pi-ribbon")
    elif cfg.power == "usb":
        consumables.append("usb-tether-esp32")
    out += [Line("consumable", c, 1, CONSUMABLES[c]) for c in consumables]
    return out


def part_file(name: str) -> str:
    """Where a printed part's file is, from the output's root."""
    return f"parts/{name}.stl"


def screws(a: Assembly) -> Counter:
    """Every M3 screw in the gun, by key."""
    return Counter(b.key for b in a.bought if b.key.startswith("m3x"))


def teardown_screws(a: Assembly) -> Counter:
    """The screws a full teardown undoes, by key: the budget's."""
    return Counter(b.key for b in a.bought if b.teardown)


def markdown(a: Assembly) -> str:
    cfg = a.config
    rows = lines(a)
    out = [
        f"# Bill of materials: {cfg.name}",
        "",
        f"Board {cfg.board} (camera {cfg.camera}), power drawer {cfg.power}, "
        f"trigger {cfg.mechanism} with {cfg.trigger}, style {cfg.style}. "
        "Part files are under `parts/` at the top of the output (STL; 3MF "
        "beside each). Printed for a "
        f"{' x '.join(f'{v:g}' for v in cfg.printer.volume)} mm bed, clearance "
        f"{cfg.printer.clearance:g} mm, {cfg.printer.fastener}s.",
        "",
        "## Print",
        "",
        "| Part | File | Count | Material and settings |",
        "| --- | --- | --- | --- |",
    ]
    out += [
        f"| `{r.name}` | `{part_file(r.name)}` | {r.count} | {r.spec} |"
        for r in rows
        if r.kind == "print"
    ]
    out += ["", "## Buy", "", "| Part | Count | What |", "| --- | --- | --- |"]
    out += [f"| `{r.name}` | {r.count} | {r.spec} |" for r in rows if r.kind == "buy"]
    out += [""]
    out += [f"Plus: {r.spec}." for r in rows if r.kind == "consumable"]
    total = sum(screws(a).values())
    teardown = sum(teardown_screws(a).values())
    out += [
        "",
        f"{total} screws in all, M3 socket-head; a full teardown undoes {teardown} "
        "of them with the 2.5 mm hex key.",
    ]
    return "\n".join(out) + "\n"


def csv_text(a: Assembly) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["kind", "part", "file", "count", "specification"])
    for r in lines(a):
        w.writerow(
            [
                r.kind,
                r.name,
                part_file(r.name) if r.kind == "print" else "",
                r.count,
                r.spec,
            ]
        )
    return buf.getvalue()
