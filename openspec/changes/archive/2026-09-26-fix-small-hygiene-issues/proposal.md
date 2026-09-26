## Why

Three small rough edges, each cheap to fix and each misleading when hit:
`--markers file:` with nothing after the colon fails with a bare
`IsADirectoryError: '.'` instead of the layout-source error that was
meant to catch it; the uinput permission error sends people to "the
change's setup notes", which do not exist for a user; and the Vulkan
layer's guarantee that it only copies inside the swapchain image rests
on two checks in two files whose combination nothing pins.

## What Changes

- `resolve_layout("file:")` (and so `marker_map_factory`) raises
  `LayoutSourceError` with a message naming both valid forms, instead of
  trying to load the current directory as a TOML file. The existing
  empty-path guard tested `Path("")`, which is `Path(".")` and truthy,
  so it never fired.
- The `/dev/uinput` permission error in `inject.py` points at the
  README's "`/dev/uinput` permission" paragraph under "Running the
  server", which carries the udev rule.
- The Vulkan layer checks a loaded canvas against the swapchain extent
  through one tested predicate, `bsov_fits_extent`, in
  `canvas_format.c`: the canvas must be exactly the extent and every
  rectangle must lie inside the extent. Only then does the layer record
  copy regions. The existing behavior already rejected a mismatched
  size. The new predicate also re-checks each rectangle against the
  extent itself, so the guarantee no longer depends on `bsov_load`
  having run first.
- The Python writer's `write_file` refuses to write a canvas the layer
  would reject (an empty rectangle or one outside the canvas), so the
  mistake shows up in Boresight rather than as a line in the game's
  log. `pack` stays permissive for tests.

## Capabilities

### New Capabilities

### Modified Capabilities
- `vulkan-present-overlay`: adds the requirement that marker patches are
  only ever copied inside the swapchain image, and that a canvas whose
  size differs from the swapchain is not drawn.
- `marker-overlay`: the layout-source requirement gains a scenario for
  a `file:` source with no path.

## Impact

- `src/boresight/layout_source.py`, `src/boresight/inject.py` (message
  text only), `src/boresight/overlay/canvas_format.py`.
- `native/vulkan_overlay/src/canvas_format.{h,c}`,
  `native/vulkan_overlay/src/overlay_layer.c`,
  `native/vulkan_overlay/tests/test_canvas_format.c`.
- Tests: `tests/test_layout_source.py`,
  `tests/test_overlay_vulkan_canvas.py`.
- No new dependencies. No wire-format change.
