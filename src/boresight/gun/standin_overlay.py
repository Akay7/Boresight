"""A stand-in for the on-screen overlay, for `--emulate` and the tests.

`python -m boresight.gun.standin_overlay --screen WxH [overlay options]`
takes the overlay's own options, works out what the real overlay would
draw on a screen of that size with `qt_backend.plan_overlay` (the same
function), reports that geometry the same way, and then waits, as a
running overlay does, until it is stopped. It opens no window, so it runs
with no display.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence

SCREEN_DEFAULT = "1920x1080"


def parse_screen(text: str) -> tuple[int, int]:
    width, _, height = text.lower().partition("x")
    return int(width), int(height)


def main(argv: Sequence[str] | None = None) -> int:
    from boresight.overlay.layout import OverlayGeometryError
    from boresight.overlay.qt_backend import plan_overlay

    parser = argparse.ArgumentParser(prog="python -m boresight.gun.standin_overlay")
    parser.add_argument("--screen", type=parse_screen, default=SCREEN_DEFAULT)
    parser.add_argument("--display", default=None)
    parser.add_argument("--extra-margin-px", type=int, default=0)
    parser.add_argument("--picture-aspect", default=None)
    parser.add_argument("--commands", action="store_true")
    args = parser.parse_args(argv)

    screen = args.screen
    margin = args.extra_margin_px
    if args.picture_aspect:
        area = (0, 0, *screen)
    else:
        area = (margin, margin, screen[0] - 2 * margin, screen[1] - 2 * margin)
    try:
        plan = plan_overlay(
            screen,
            area,
            picture_aspect=args.picture_aspect,
            margin_px=margin if args.picture_aspect else 0,
        )
    except OverlayGeometryError as error:
        print(f"\n{error}\n", file=sys.stderr)
        return 2
    plan.emit(screen)
    print(f"stand-in overlay on {screen[0]}x{screen[1]}", file=sys.stderr, flush=True)
    while True:
        time.sleep(3600)


def launcher_for(screen_px: tuple[int, int]):
    """A `MarkerSourceController` launcher that starts this stand-in in
    place of the real overlay, with the same options."""
    import subprocess

    def launch(command: list[str], **kwargs):
        options = command[command.index("boresight.overlay") + 1 :]
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "boresight.gun.standin_overlay",
                f"--screen={screen_px[0]}x{screen_px[1]}",
                *options,
            ],
            **kwargs,
        )

    return launch


if __name__ == "__main__":
    raise SystemExit(main())
