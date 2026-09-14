"""Activating the Vulkan present-overlay layer for one game launch.

The layer itself (`native/vulkan_overlay/`) is a C shared library the
Vulkan loader loads into the *game's* process -- nothing in this module
runs there. What runs here, in Boresight's own process, is everything
that has to happen before that: deciding whether this backend can work
at all, writing the marker canvas the layer will read
(`canvas_format.py`), and setting the three environment variables that
turn the layer on for exactly one launch:

    VK_INSTANCE_LAYERS=VK_LAYER_boresight_overlay
    VK_LAYER_PATH=<directory holding the built .so + its manifest>
    BORESIGHT_OVERLAY_CANVAS=<path to the .bsov file written below>

That structure is deliberate, not incidental: it is what makes "enabled
explicitly, per application" true. Nothing this module does writes to
`~/.local/share/vulkan/implicit_layer.d` or any other system-wide
location -- an application that does not have these three variables set
in its own environment sees no marker patches, regardless of whether
this backend has ever been built or used on the machine.

Two checks matter before spending any of that on a real game, mirroring
`backend.check_supported`'s "explanation, not a traceback" pattern:

  - is there a Vulkan loader on this system at all (the "missing
    Vulkan loader" requirement)?
  - has the native layer actually been built (a separate, optional
    step -- see native/vulkan_overlay/README.md -- from installing the
    Python package)?

Neither failure means the application doesn't present via Vulkan; that
third case is a *per-title* diagnostic the layer itself detects from
inside the game's process (its own startup timeout, see
overlay_layer.c), because only being inside that process can tell.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from boresight.overlay.backend import PRINTED_MARKERS_HINT, OverlayUnavailableError
from boresight.overlay.canvas_format import write_file
from boresight.overlay.render import render_overlay

LAYER_NAME = "VK_LAYER_boresight_overlay"
LIBRARY_FILENAME = "libboresight_overlay.so"
MANIFEST_FILENAME = "VkLayer_boresight_overlay.json"

BUILD_HINT = (
    "Build it with:\n"
    "  cmake -S native/vulkan_overlay -B native/vulkan_overlay/build\n"
    "  cmake --build native/vulkan_overlay/build\n"
    "See native/vulkan_overlay/README.md for details."
)


def _candidate_layer_dirs() -> list[Path]:
    """Where a built layer might live, in lookup order.

    An env var override always wins -- the packaged case, where the
    layer was built somewhere outside any source checkout at all. The
    default is the sibling `native/vulkan_overlay/build/` a development
    checkout builds into; it is not assumed to exist, only tried.
    """
    candidates = []
    override = os.environ.get("BORESIGHT_OVERLAY_LAYER_DIR")
    if override:
        candidates.append(Path(override))

    # src/boresight/overlay/vulkan_backend.py -> repo root is 4 parents up.
    repo_root = Path(__file__).resolve().parents[3]
    candidates.append(repo_root / "native" / "vulkan_overlay" / "build")
    return candidates


def find_layer_dir() -> Path:
    """The directory holding the built `.so` and its manifest.

    Raises `OverlayUnavailableError` -- same shape as a missing Qt
    install -- if none of the candidate locations has both files. This
    is a build step, not a `pip install`, so the message points at
    `native/vulkan_overlay/README.md` rather than an extras group.
    """
    tried = []
    for directory in _candidate_layer_dirs():
        tried.append(str(directory))
        if (directory / LIBRARY_FILENAME).is_file() and (
            directory / MANIFEST_FILENAME
        ).is_file():
            return directory

    raise OverlayUnavailableError(
        "the Vulkan present-overlay layer has not been built. Looked in: "
        f"{', '.join(tried)}.\n{BUILD_HINT}\n{PRINTED_MARKERS_HINT}"
    )


def find_vulkan_loader() -> None:
    """Raise `OverlayUnavailableError` if no Vulkan loader is installed.

    Checked independently of `find_layer_dir`: a machine can have the
    layer built (it only needs headers, fetched at build time -- see
    the CMakeLists.txt comment) but no Vulkan *runtime* installed at
    all, which is the "no compatible Vulkan loader" scenario the spec
    names explicitly. Loading the real runtime name (the versioned
    SONAME on Linux, not a `-dev`-package-only unversioned symlink)
    is what every Vulkan application actually does at startup, so it is
    the honest thing to probe here rather than checking for a build-time
    header.
    """
    if sys.platform == "win32":
        library_names = ["vulkan-1.dll"]
    elif sys.platform == "darwin":
        library_names = ["libvulkan.dylib", "libMoltenVK.dylib"]
    else:
        library_names = ["libvulkan.so.1", "libvulkan.so"]

    for name in library_names:
        try:
            ctypes.CDLL(name)
            return
        except OSError:
            continue

    raise OverlayUnavailableError(
        "no compatible Vulkan loader was found on this system "
        f"(looked for {', '.join(library_names)}). Install your "
        f"platform's Vulkan runtime, or use the window overlay or "
        f"printed markers instead. {PRINTED_MARKERS_HINT}"
    )


def check_supported() -> Path:
    """Raise `OverlayUnavailableError` if this backend cannot run here.

    Returns the layer directory on success, so a caller that already
    did the check doesn't have to look it up twice.
    """
    find_vulkan_loader()
    return find_layer_dir()


def write_canvas(
    path: Path,
    screen_px: tuple[int, int],
    tag_px: int | None = None,
    inset_px: int | None = None,
) -> None:
    """Render the marker layout for `screen_px` and write it as `.bsov`.

    Uses the exact same `render_overlay` the Qt backend calls in-process
    -- see `tests/test_overlay_vulkan_geometry.py` for the test that
    keeps the two backends unable to disagree about where tags go.
    """
    canvas, rectangles = render_overlay(screen_px, tag_px, inset_px)
    write_file(path, canvas, rectangles)


def default_canvas_path(screen_px: tuple[int, int]) -> Path:
    width, height = screen_px
    return Path(tempfile.gettempdir()) / f"boresight-overlay-{width}x{height}.bsov"


def launch_env(
    base_env: dict[str, str], layer_dir: Path, canvas_path: Path
) -> dict[str, str]:
    """`base_env` plus the three variables that activate the layer.

    Returns a new dict; never mutates `base_env` or `os.environ`. That
    matters for the "enabled explicitly, per application" requirement:
    the only process that ever sees these variables is the one this
    dict is handed to when launching the game, not this process itself
    or any other one already running.
    """
    env = dict(base_env)
    existing_layers = env.get("VK_INSTANCE_LAYERS")
    env["VK_INSTANCE_LAYERS"] = (
        f"{existing_layers}:{LAYER_NAME}" if existing_layers else LAYER_NAME
    )
    existing_layer_path = env.get("VK_LAYER_PATH")
    layer_dir_str = str(layer_dir)
    env["VK_LAYER_PATH"] = (
        f"{existing_layer_path}{os.pathsep}{layer_dir_str}"
        if existing_layer_path
        else layer_dir_str
    )
    env["BORESIGHT_OVERLAY_CANVAS"] = str(canvas_path)
    return env


def _parse_screen(value: str) -> tuple[int, int]:
    try:
        width_str, height_str = value.lower().split("x", 1)
        return int(width_str), int(height_str)
    except ValueError as exc:
        raise SystemExit(f"--screen must look like 1920x1080, got {value!r}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m boresight.overlay.vulkan_backend",
        description=(
            "Draw the marker patches inside a Vulkan-presenting game's own "
            "frames -- reaches exclusive fullscreen, which the window "
            "overlay cannot. See native/vulkan_overlay/README.md."
        ),
    )
    parser.add_argument(
        "--screen",
        required=True,
        type=_parse_screen,
        metavar="WIDTHxHEIGHT",
        help="the resolution the game will present at, e.g. 1920x1080",
    )
    parser.add_argument("--tag-px", type=int, default=None)
    parser.add_argument("--inset-px", type=int, default=None)
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="the game command to launch, e.g. -- %%command%% in Steam",
    )
    args = parser.parse_args(argv)

    try:
        layer_dir = check_supported()
    except OverlayUnavailableError as error:
        print(f"\n{error}\n", file=sys.stderr)
        return 2

    canvas_path = default_canvas_path(args.screen)
    write_canvas(canvas_path, args.screen, args.tag_px, args.inset_px)

    command = args.command
    if command and command[0] == "--":
        command = command[1:]

    if not command:
        print(
            f"Canvas written to {canvas_path}. Layer directory: {layer_dir}.\n"
            "No command given -- pass one after `--` to launch it with the "
            "overlay active, e.g.:\n"
            "  python -m boresight.overlay.vulkan_backend "
            f"--screen {args.screen[0]}x{args.screen[1]} -- %command%",
            file=sys.stderr,
        )
        return 0

    env = launch_env(dict(os.environ), layer_dir, canvas_path)
    os.execvpe(command[0], command, env)  # noqa: S606 - the whole point


if __name__ == "__main__":
    raise SystemExit(main())
