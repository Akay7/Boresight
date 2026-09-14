# Vulkan present overlay

A Vulkan explicit layer that draws Boresight's marker patches into a
game's own presented frames, from inside the game's own process. It
exists for exactly one case the window-based overlay
(`python -m boresight.overlay`) cannot reach: a title running exclusive
fullscreen, where compositing is bypassed entirely and there is no
window stack for an overlay window to sit above. See
`openspec/changes/add-vulkan-present-overlay/` (proposal, design, spec)
for the full rationale and decisions this implementation follows.

This directory is entirely optional. Nothing in the default
`uv sync` / `pip install boresight` path references it, the same way
the Qt overlay is gated behind the `overlay` extra rather than a core
dependency.

## Building

Requires a C compiler, CMake, and Threads (pthreads). Vulkan headers
are fetched automatically if a system Vulkan SDK (`vulkan-devel` or
equivalent) isn't installed -- see `CMakeLists.txt`'s comment for why a
Vulkan layer needs headers but not the loader library itself.

```sh
cmake -S native/vulkan_overlay -B native/vulkan_overlay/build
cmake --build native/vulkan_overlay/build
```

This produces `native/vulkan_overlay/build/libboresight_overlay.so`
and copies `VkLayer_boresight_overlay.json` next to it. The manifest's
`library_path` is relative (`./libboresight_overlay.so`), so no install
step is needed -- pointing `VK_LAYER_PATH` at that build directory is
enough for the loader to find both.

Verify the manifest is discoverable:

```sh
VK_LAYER_PATH=native/vulkan_overlay/build vulkaninfo | grep boresight
```

## Using it

Activation is always per-launch (an explicit layer), never system-wide.
`boresight.overlay.vulkan_backend` is the thin wrapper that does the
three things a launch needs -- checks a Vulkan loader and a built layer
are both present, writes the marker canvas for your display resolution,
and execs your game with the right environment set:

```sh
uv run python -m boresight.overlay.vulkan_backend --screen 1920x1080
```

That form (bare `uv run`) is only for trying it from a terminal inside
this checkout. **In Steam's launch options, use the venv's `python` by
its full path instead:**

```sh
/path/to/Boresight/.venv/bin/python -m boresight.overlay.vulkan_backend \
    --screen 1920x1080 -- %command%
```

`%command%` is Steam's own placeholder. This distinction matters
because Steam runs launch options from the *game's* install directory,
in a plain environment with no `uv`/venv context at all -- `uv run`
there has no project to resolve and fails with `ModuleNotFoundError: No
module named 'boresight'` -- and since that failure happens before this
wrapper ever gets to exec the game (`%command%` is everything after
`--`, only reached once the wrapper's own `import boresight` succeeds),
the game doesn't launch at all, which is easy to mistake for a broken
launch option rather than a missing venv. `uv run --project
/path/to/Boresight python -m ...` is an equivalent fix if you'd rather
keep using `uv run`.

Without a trailing command, it just checks availability and writes the
canvas, printing the equivalent manual environment variables:

```
VK_INSTANCE_LAYERS=VK_LAYER_boresight_overlay
VK_LAYER_PATH=<this build directory>
BORESIGHT_OVERLAY_CANVAS=<path to the .bsov file just written>
```

If the game does not present through Vulkan (wined3d's OpenGL path, or
DX9/11/12 without DXVK/VKD3D-Proton) or reaches its render loop slower
than `BORESIGHT_OVERLAY_STARTUP_TIMEOUT_MS` (default 5000), the layer
logs an actionable message to stderr naming the window overlay and
printed markers as alternatives, rather than silently drawing nothing.

### Resolution changes

The canvas is generated for one specific resolution, matching
`render_overlay`'s layout at that size. If a game recreates its
swapchain at a *different* resolution than the canvas was generated
for (a mode switch, not just minimizing/restoring at the same size),
the layer logs it and skips drawing for that swapchain rather than
positioning patches for the wrong size -- see design.md's amendment on
this. Relaunch after changing resolution so a fresh canvas is written.

## Manual verification

A minimal Vulkan sample (`vkcube`, from `vulkan-tools`) is enough to
exercise every code path without a real game:

```sh
# Loader calls into the layer at all (a log line on load):
VK_LAYER_PATH=native/vulkan_overlay/build \
VK_INSTANCE_LAYERS=VK_LAYER_boresight_overlay \
vkcube --c 60

# With a canvas configured, the patches actually appear:
uv run python -m boresight.overlay.vulkan_backend --screen 640x480
VK_LAYER_PATH=native/vulkan_overlay/build \
VK_INSTANCE_LAYERS=VK_LAYER_boresight_overlay \
BORESIGHT_OVERLAY_CANVAS=/tmp/boresight-overlay-640x480.bsov \
vkcube --width 640 --height 480
```

Stack `VK_LAYER_KHRONOS_validation` underneath during development, if
it's installed (`vulkan-validationlayers` or the LunarG Vulkan SDK):

```sh
VK_LAYER_PATH=native/vulkan_overlay/build:/usr/share/vulkan/explicit_layer.d \
VK_INSTANCE_LAYERS=VK_LAYER_boresight_overlay:VK_LAYER_KHRONOS_validation \
BORESIGHT_OVERLAY_CANVAS=/tmp/boresight-overlay-640x480.bsov \
vkcube --width 640 --height 480
```

`VK_LAYER_PATH` replaces the loader's default explicit-layer search
path rather than adding to it, hence listing both directories above.
Redirect through `stdbuf -oL -eL` (or run in a real terminal) if
capturing output to a file or pipe -- a validation message printed just
before a hard failure can otherwise sit lost in a stdio buffer that
never gets flushed.

This is not a nicety: two real bugs in this layer were only ever
visible with validation stacked in (a missing loader-data stamp on
self-allocated command buffers, and a swapchain image usage flag this
layer must add itself) -- see design.md's "Amendments" section for
both. Confirming a clean run this way is worth doing before trusting
any change to `overlay_layer.c` beyond what a plain `vkcube` run alone
can catch.
