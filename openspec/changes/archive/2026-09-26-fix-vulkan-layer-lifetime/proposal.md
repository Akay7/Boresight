## Why

The Vulkan present-overlay layer runs inside the game's own process, so
any memory-safety bug in it is a bug in the game. Reading
`native/vulkan_overlay/` turned up several: the startup-diagnostic
thread reads its `instance_data_t` after `vkDestroyInstance` has freed
it (DXVK/Proton and many engines create and immediately destroy a
probe `VkInstance` at startup, so this is the normal path, not an edge
case), the flag it reads is written from another thread with no
synchronization, several allocations are used unchecked, and the
`.bsov` reader accepts rectangles outside the canvas, which the layer
then turns into out-of-bounds `vkCmdCopyImage` regions. None of these
change what the layer is meant to do; they make it do it without
undefined behaviour.

## What Changes

- The startup-timeout diagnostic thread's lifetime is owned by its
  instance: `vkDestroyInstance` wakes it immediately and joins it
  before freeing the instance's state, so destroying an instance never
  waits out the timeout and never leaves a thread holding a dangling
  pointer. The "swapchain seen" flag becomes properly synchronized.
- Unchecked allocations on instance, device and swapchain creation are
  checked. The layer never crashes on allocation failure: instance and
  device creation fail cleanly with `VK_ERROR_OUT_OF_HOST_MEMORY`
  (tearing down the just-created downstream object), and swapchain
  creation succeeds with this layer's drawing disabled for that
  swapchain.
- `bsov_load` rejects canvases whose rectangles fall outside the
  canvas, are empty, or overflow; bounds `width`, `height` and
  `rect_count` before allocating; and checks the file is at least as
  large as its header claims before reading it. A rejected canvas
  follows the existing "could not read a valid marker canvas" path
  (log once, pass presents through unmodified).
- The Python reader (`canvas_format.unpack`) mirrors the same checks so
  the two readers agree on what a valid file is.
- A native test target (opt-in CMake option, run via `ctest`) covering
  `bsov_load` with malformed inputs and the startup watchdog's
  start/stop lifetime, runnable under ASan/UBSan and TSan.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `vulkan-present-overlay`: adds requirements that the layer stays
  memory-safe across rapid instance create/destroy and allocation
  failure, and that a malformed marker canvas is rejected rather than
  drawn. The capability is still defined by the unarchived
  `add-vulkan-present-overlay` change (no `openspec/specs/
  vulkan-present-overlay/` exists yet), so the delta is written as
  ADDED requirements against it; see design.md.

## Impact

- `native/vulkan_overlay/src/overlay_layer.c`: instance/device/swapchain
  lifetime and allocation handling.
- `native/vulkan_overlay/src/canvas_format.{c,h}`: stricter validation.
- New `native/vulkan_overlay/src/startup_watchdog.{c,h}` (the timeout
  thread, factored out so it can be tested without a Vulkan loader) and
  `native/vulkan_overlay/tests/`.
- `native/vulkan_overlay/CMakeLists.txt`: an opt-in
  `BORESIGHT_OVERLAY_BUILD_TESTS` option; the default build is unchanged.
- `src/boresight/overlay/canvas_format.py`: `unpack` validation only;
  `pack`/`write_file` output is byte-for-byte unchanged.
- No change to the launcher, environment variables, the `.bsov` wire
  format, or any Python behaviour outside `unpack`.
