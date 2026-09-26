## Context

Three unrelated fixes share this change because each is small. See
proposal.md for why each matters. Only the third needed investigation
before deciding what to change. This document mostly records that
investigation.

### What the layer already guaranteed (audit of item 3)

The question was whether any marker rectangle the Vulkan layer copies
can fall outside the swapchain image, and whether any pixel offset can
fall outside the canvas buffer. Reading the code as of 47ec230:

1. **Rectangles against the canvas.** `bsov_load`
   (`native/vulkan_overlay/src/canvas_format.c`) rejects the whole file
   unless every rect satisfies `rect_is_valid(rect, header.width,
   header.height)`: `w > 0`, `h > 0`, `w <= width`, `h <= height`,
   `x <= width - w`, `y <= height - h`. These are subtractions after
   bounding, so nothing can wrap. `test_canvas_format.c` already covers
   the right edge, the bottom edge, origin outside, `x + w` / `y + h`
   overflow, and empty rects.
2. **Canvas against the swapchain.** `try_setup_overlay`
   (`overlay_layer.c`) refuses the canvas unless `canvas.width ==
   sc->extent.width && canvas.height == sc->extent.height`, and logs
   both sizes. So a canvas larger than the swapchain was already
   rejected, and so was a smaller one.
3. **Pixel buffer.** `bsov_load` checks the file size against
   `header + rects + width*height` before allocating, then reads exactly
   `width*height` bytes into a buffer of that size. The layer expands
   `pixel_count = width*height` texels into a buffer of `pixel_count*4`
   bytes. `BSOV_MAX_DIMENSION` = 16384 keeps that product far below
   `SIZE_MAX`. The staging buffer, the canvas `VkImage` and the
   `vkCmdCopyBufferToImage` region all use the full canvas size. No
   per-rect CPU pixel offset is ever computed, so there is no offset
   that could leave the buffer.
4. **Copy regions.** Each rect becomes one `VkImageCopy` with the same
   `srcOffset`/`dstOffset` = `(x, y)` and `extent` = `(w, h)`, from the
   canvas image (size = canvas) into the swapchain image (size = extent).
   Given (1) and (2), every region is inside both images. The
   `(int32_t)` casts are safe because `x <= 16384`.
5. **Python writer.** `canvas_format.unpack` applies the same rect
   checks as the C reader. `pack`/`write_file` validate nothing, but
   their only production caller, `vulkan_backend.write_canvas`, passes
   `render_overlay`'s output. That output is clamped to the canvas
   (`patch_x = max(0, …)`, `patch_right = min(width, …)`).

**Conclusion:** no out-of-bounds copy was reachable. The guarantee was
real, but it held only because checks in two files combined, and one of
them (the extent comparison) lives in a `static` function inside the
layer. No test can reach that function without a Vulkan device. A future
edit to either side could break the guarantee without any test failing.

## Goals / Non-Goals

**Goals:**
- Make "every copy region is inside the swapchain image" a single
  predicate that the layer calls and a unit test pins.
- Have the Python writer fail loudly on a rect the layer would reject.
- Fix the `file:` empty-path check and the stale doc pointer.

**Non-Goals:**
- Clamping rectangles to the swapchain. A canvas for the wrong size is
  a stale layout, and the existing spec already says the layer must not
  draw a stale layout, so it is rejected instead. Clamping would draw
  markers in the wrong place, and the solver would trust them.
- Changing the `.bsov` format or `pack`'s permissiveness. Tests rely on
  `pack` to build malformed files.

## Decisions

- **`bsov_fits_extent(canvas, width, height)` in `canvas_format.c`.**
  It returns 1 only if the canvas has pixels, its size equals the
  extent, and every rect passes `rect_is_valid` against the *extent*.
  The last check is redundant after `bsov_load`, and that is on
  purpose: the predicate states the property the copy loop needs in
  terms of the image it writes into, so it stays correct even for a
  canvas that did not come from `bsov_load`. It sits beside
  `rect_is_valid` so both checks share one overflow-safe comparison.
  The test binary already compiles `canvas_format.c` without Vulkan
  headers. *Alternative:* a test harness around `overlay_layer.c` with
  a fake dispatch table. That is far more code, and it would test the
  fake more than the layer.
- **The layer keeps its specific log line for a size mismatch** and
  adds a generic one for the (currently unreachable) case where the
  size matches but a rect does not fit.
- **`write_file` validates, `pack` does not.** Validation reuses the
  same rect rule as `unpack` (one private helper), so the Python reader
  and writer cannot disagree.
- **Empty `file:` path.** The code now tests the raw string after
  `file:` (whitespace stripped) instead of `Path(...)`. The message is
  the one requested: `file: needs a path, e.g. file:markers.toml, or
  use plain 'file' for the default`.
- **uinput message.** It names the README section by its visible text
  ("`/dev/uinput` permission", under "Running the server") rather than
  by an anchor link. Other work is editing README.md in parallel, and
  a heading slug is more likely to drift than the paragraph's name.

## Risks / Trade-offs

- [The README paragraph is renamed later] → The message names the
  README and the udev rule, so it still tells the reader what to look
  for.
- [`write_file` now raises where it silently wrote before] → The only
  production input (`render_overlay`) is clamped to the canvas, and the
  existing real-render round-trip test covers it.
