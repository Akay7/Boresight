"""`boresight-case`: build a configuration, the fit coupon, or check a skin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from boresight_case import catalog
from boresight_case.config import Config, ConfigError, load


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="boresight-case",
        description="Generate the printable Boresight gun case.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser(
        "build",
        help="build one configuration, or every shipped one",
        description="Write every part's STL and 3MF, STEP files, the skin "
        "interface, the bill of materials and an exploded view. With --all, "
        "a parts library: each distinct part once, and each configuration's "
        "bill of materials and drawing.",
    )
    which = b.add_mutually_exclusive_group(required=True)
    which.add_argument("config", nargs="?", type=Path, help="a configuration TOML file")
    which.add_argument(
        "--all", action="store_true", help="every valid shipped configuration"
    )
    which.add_argument(
        "--shipped",
        metavar="NAME",
        help="one shipped configuration by name (see `boresight-case list`)",
    )
    b.add_argument("--out", type=Path, default=Path("dist"), help="output directory")
    b.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be built without modelling anything",
    )

    c = sub.add_parser(
        "coupon",
        help="build the fit-test coupon",
        description="Write the fit coupon: the joint, a nut trap, a peg, the "
        "drawer latch and the MX cut-out at labelled clearances.",
    )
    c.add_argument(
        "config", nargs="?", type=Path, help="printer settings from this file"
    )
    c.add_argument("--out", type=Path, default=Path("dist"), help="output directory")

    ls = sub.add_parser("list", help="list the shipped configurations by name")
    ls.add_argument("--json", action="store_true", help="as a JSON array")

    s = sub.add_parser(
        "check-skin",
        help="check third-party skin parts against the skin interface",
        description="Check STL or 3MF cover parts: core envelope, keep-out "
        "zones, the bolt holes and their flanges, print bed.",
    )
    s.add_argument("config", type=Path, help="the configuration the skin is for")
    s.add_argument("parts", nargs="+", type=Path, help="STL or 3MF files")
    s.add_argument(
        "--metal",
        action="store_true",
        help="the parts are metal or metal-filled: keep them out of the antenna zones",
    )
    return p


def _describe(cfg: Config) -> str:
    lines = [
        f"{cfg.name}:",
        f"  board {cfg.board} (camera {cfg.camera}), barrels {cfg.barrels}, "
        f"power {cfg.power}, trigger {cfg.mechanism} with {cfg.trigger}, "
        f"feedback {cfg.feedback}, buttons {'yes' if cfg.buttons else 'no'}, "
        f"style {cfg.style}",
    ]
    counts = catalog.part_counts(cfg)
    lines += [f"  {name}" + (f" x {n}" if n > 1 else "") for name, n in counts.items()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except ConfigError as e:
        print(f"boresight-case: {e}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    from boresight_case.config import shipped_configurations

    if args.command == "list":
        names = [cfg.name for cfg in shipped_configurations()]
        if args.json:
            import json

            print(json.dumps(names))
        else:
            print("\n".join(names))
        return 0
    if args.command == "build":
        if args.all:
            configs = shipped_configurations()
        elif args.shipped:
            by_name = {cfg.name: cfg for cfg in shipped_configurations()}
            if args.shipped not in by_name:
                raise ConfigError(
                    f"no shipped configuration {args.shipped!r}; "
                    "`boresight-case list` names them"
                )
            configs = [by_name[args.shipped]]
        else:
            configs = [load(args.config)]
        if args.dry_run:
            print("\n".join(_describe(cfg) for cfg in configs))
            return 0
        from boresight_case import export

        if args.all:
            # Every configuration shares most of its parts: one library.
            out = export.build_library(
                configs, args.out, progress=lambda cfg: print(f"built {cfg.name}")
            )
            print(f"parts library -> {out}")
            return 0
        for cfg in configs:
            out = export.build_configuration(cfg, args.out / cfg.name)
            print(f"built {cfg.name} -> {out}")
        return 0
    if args.command == "coupon":
        from boresight_case.coupon import build_coupon

        cfg = load(args.config) if args.config else Config()
        print(f"built coupon -> {build_coupon(cfg.printer, args.out)}")
        return 0
    if args.command == "check-skin":
        from boresight_case.skin_check import check_skin_files

        cfg = load(args.config)
        report = check_skin_files(cfg, args.parts, metal=args.metal)
        print(report.text())
        return 0 if report.ok else 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
