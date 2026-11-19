"""The bill of materials: what to print and what to buy for a configuration,
and every lead to make."""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass

from boresight_case import wiring
from boresight_case.assembly import Assembly
from boresight_case.vendor import CONSUMABLES, VENDOR


@dataclass(frozen=True)
class Line:
    kind: str  # "print", "buy", "lead" or "consumable"
    name: str
    count: int
    spec: str


def lines(a: Assembly) -> list[Line]:
    first = {}
    for p in a.printed.values():
        first.setdefault(p.part, p)
    counts = a.part_counts()
    out = [
        Line(
            "print",
            part,
            counts[part],
            f"{p.material}, {p.perimeters} perimeters, {p.infill}% infill",
        )
        for part, p in first.items()
    ]
    bought = Counter(b.key for b in a.bought)
    for key in sorted(bought):
        out.append(Line("buy", key, bought[key], VENDOR[key].spec))
    for lead in wiring.leads(a.config):
        out.append(
            Line(
                "lead",
                lead.name,
                1,
                f"{lead.plug} to {lead.socket}, {lead.length} mm: "
                + "; ".join(lead.pins),
            )
        )
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


def bolts(a: Assembly) -> Counter:
    """Every M3 bolt and screw in the gun, by key."""
    return Counter(b.key for b in a.bought if b.key.startswith("m3x"))


def teardown_bolts(a: Assembly) -> Counter:
    """The bolts a full teardown undoes, by key: the budget's."""
    return Counter(b.key for b in a.bought if b.teardown)


def markdown(a: Assembly) -> str:
    cfg = a.config
    rows = lines(a)
    barrels = ("no barrel (compact)", "one barrel", "two barrels (long)")[cfg.barrels]
    out = [
        f"# Bill of materials: {cfg.name}",
        "",
        f"Board {cfg.board} (camera {cfg.camera}), {barrels}, "
        f"power drawer {cfg.power}, "
        f"trigger {cfg.mechanism} with {cfg.trigger}, feedback {cfg.feedback}, "
        f"{'Start and Select buttons, ' if cfg.buttons else ''}style {cfg.style}. "
        "Part files are under `parts/` at the top of the output (STL; 3MF "
        "beside each). Printed for a "
        f"{' x '.join(f'{v:g}' for v in cfg.printer.volume)} mm bed, clearance "
        f"{cfg.printer.clearance:g} mm.",
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
    out += ["", "## Leads", ""]
    out += wiring.markdown_table(cfg)
    out += [""]
    out += [f"Plus: {r.spec}." for r in rows if r.kind == "consumable"]
    teardown = teardown_bolts(a)
    out += [
        "",
        f"A full teardown undoes {sum(teardown.values())} bolts with the 2.5 mm hex "
        f"key: {teardown.get('m3x50', 0)} M3 x 50 through-bolts and "
        f"{teardown.get('m3x12', 0)} M3 x 12 (the trigger's). The drawer's "
        "thumbscrew turns by hand.",
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
