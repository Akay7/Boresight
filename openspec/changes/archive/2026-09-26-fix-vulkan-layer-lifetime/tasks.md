## 1. Startup watchdog lifetime

- [x] 1.1 Add `src/startup_watchdog.{c,h}`: start (condvar on `CLOCK_MONOTONIC`, timed wait loop on `stop`/`seen`), mark-swapchain-seen (under the mutex, wakes the thread), stop (signal + join, safe if never started); verify it builds with `-Wall -Wextra` warning-free
- [x] 1.2 Embed the watchdog in `instance_data_t`, start it in `boresight_CreateInstance` (log and continue if `pthread_create` fails), stop+join it in `boresight_DestroyInstance` before `free`, and route `swapchain_seen` through it; verify the old `volatile int` and `pthread_detach` are gone (`grep`)
- [x] 1.3 Add `tests/test_startup_watchdog.c` (create/stop churn with a 5 s timeout finishing in well under a second, fires exactly once when no swapchain, never fires once marked seen, stop after fire) and verify it passes under `address,undefined` and under `thread` sanitizers

## 2. Allocation failures and device/swapchain teardown

- [x] 2.1 `boresight_CreateInstance`: on `calloc` failure destroy the downstream instance and return `VK_ERROR_OUT_OF_HOST_MEMORY`; verify by reading the path and a clean build
- [x] 2.2 `boresight_CreateDevice`: same for `device_data_t`; tolerate a missing `instance_data_t` and a failed queue-family array allocation by disabling drawing; verify by reading the path and a clean build
- [x] 2.3 `boresight_CreateSwapchainKHR`: tolerate missing instance data and failed `swapchain_state_t`/images allocation or `vkGetSwapchainImagesKHR` failure by leaving the swapchain untracked; verify by reading the path and a clean build
- [x] 2.4 `try_setup_overlay`: fail (not crash) if `vkCmdCopyBufferToImage` can't be resolved; verify by a clean build
- [x] 2.5 `boresight_DestroyDevice`: tear down any still-registered swapchain state before destroying the device; verify by a clean build and the lavapipe probe in 4.3

## 3. Canvas validation

- [x] 3.1 `canvas_format.{c,h}`: add `BSOV_MAX_DIMENSION` (16384) / `BSOV_MAX_RECTS` (4096), check file size against the declared sizes before allocating, and reject empty/out-of-bounds/overflowing rects; verify with 3.3
- [x] 3.2 `canvas_format.py`: mirror the limits and checks in `unpack` (`ValueError`), leaving `pack` byte-for-byte unchanged; verify with `uv run pytest -q tests/test_overlay_vulkan_canvas.py` plus new rejection tests there
- [x] 3.3 Add `tests/test_canvas_format.c` (valid file, rect past right/bottom edge, `x + w` overflow, zero-size rect, truncated rects, truncated pixels, huge `rect_count`, oversize dimensions, trailing bytes tolerated, optional path argument to load an external file) and verify it passes under `address,undefined`
- [x] 3.4 Verify a canvas written by the Python writer for 1920x1080 loads through the C test binary's external-path mode

## 4. Build wiring and verification

- [x] 4.1 CMake: `BORESIGHT_OVERLAY_BUILD_TESTS` (default OFF) with `ctest` targets, `BORESIGHT_OVERLAY_SANITIZE` string option; verify the default configure/build is unchanged and warning-free
- [x] 4.2 README: document the test option and sanitizer runs; verify the commands in it work as written
- [x] 4.3 If a Vulkan loader + ICD is available, run a probe that creates/destroys instances rapidly (and a device) with the layer enabled and a short timeout; verify no crash, prompt exit, and no diagnostic for destroyed instances
- [x] 4.5 Fix the exported-GetProcAddr self-reference found by 4.3 (static implementations + hidden visibility, see design.md amendment); verify with `nm -D` (three exports only) and a clean re-run of the 4.3 probe
- [x] 4.4 Run `uv run pytest -q tests/test_overlay_vulkan_backend.py tests/test_overlay_vulkan_canvas.py tests/test_overlay_vulkan_geometry.py`, then the full suite and `uv run ruff check .`; verify all pass
