"""`python -m boresight.overlay` -- draw the markers on the screen."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from boresight.overlay.backend import OverlayUnavailableError


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m boresight.overlay",
        description=(
            "Draw ArUco markers over the current display. The overlay is "
            "transparent to mouse and keyboard, so everything beneath it "
            "keeps working -- including the clicks Boresight injects."
        ),
        epilog=(
            "Note: no overlay can draw above a fullscreen-exclusive "
            "application, on any platform. Run emulators borderless-windowed."
        ),
    )
    parser.add_argument(
        "--display",
        type=int,
        default=None,
        help="display index (default: the primary display)",
    )
    parser.add_argument(
        "--tag-px",
        type=int,
        default=None,
        help="tag edge in pixels (default: derived from the display width)",
    )
    parser.add_argument(
        "--inset-px",
        type=int,
        default=None,
        help="gap from the display edge (default: the tag's quiet margin)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="report the geometry that would be used, then exit without "
        "drawing anything",
    )
    parser.add_argument(
        "--extra-margin-px",
        type=int,
        default=0,
        help="shrink the auto-detected available area by this much on "
        "every side, on top of whatever the desktop's own panels "
        "already reserve. For a display whose panel reservation isn't "
        "detected automatically (default: 0, no change)",
    )
    args = parser.parse_args(argv)

    from boresight.overlay import qt_backend

    try:
        return qt_backend.run(
            args.display,
            args.tag_px,
            args.inset_px,
            report_only=args.report_only,
            extra_margin_px=args.extra_margin_px,
        )
    except OverlayUnavailableError as error:
        # Includes the missing-dependency case, which subclasses this.
        # Both are explanations rather than tracebacks: neither means
        # the installation is broken.
        print(f"\n{error}\n", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
