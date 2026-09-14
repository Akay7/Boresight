## 1. Native project scaffold

- [x] 1.1 Create `native/vulkan_overlay/` with a CMake build producing
      `libboresight_overlay.so` against the system Vulkan loader/headers
      (`find_package(Vulkan)`), and verify it builds clean on a machine
      with the Vulkan SDK/loader installed
      (`find_package(Vulkan)` with a `FetchContent` fallback for headers
      when no system SDK is present — see CMakeLists.txt's comment;
      built clean with `-Wall -Wextra`, no warnings)
- [x] 1.2 Write the explicit-layer manifest (`VK_LAYER_boresight_overlay`,
      `type: GLOBAL`, pointing at the built library) and verify
      `vulkaninfo` (or `vkjson_info`) lists the layer when
      `VK_LAYER_PATH` points at it
      (verified with `vulkaninfo`; note the description field must stay
      under `VK_MAX_DESCRIPTION_SIZE` (256 bytes) or the loader silently
      skips the manifest — hit and fixed during this verification)
- [x] 1.3 Confirm the default `uv sync` / `pip install boresight` path is
      completely unaffected — no reference to `native/` from
      `pyproject.toml` or the Python package
      (`grep native pyproject.toml` matches nothing)

## 2. Layer entry points and dispatch capture

- [x] 2.1 Implement `vkNegotiateLoaderLayerInterfaceVersion`,
      `GetInstanceProcAddr`, `GetDeviceProcAddr`, and confirm the loader
      successfully calls into the layer (log line on load) when the
      layer is enabled via `VK_INSTANCE_LAYERS` for a minimal Vulkan
      sample app (e.g. `vkcube`)
      (verified live: "boresight-overlay: layer loaded" prints, vkcube
      renders and exits 0)
- [x] 2.2 Implement `vkCreateInstance`/`vkCreateDevice` overrides that
      walk the `pNext` chain for the next layer's `GetProcAddr` and
      build a per-instance/per-device dispatch table; verify every
      other Vulkan call reaches `vkcube` unchanged (it still renders
      correctly with the layer enabled and doing nothing yet)
      (verified live, multiple runs, with no `BORESIGHT_OVERLAY_CANVAS`
      set: vkcube renders its cube correctly and exits cleanly)
- [x] 2.3 Implement `vkCreateSwapchainKHR` capture of images, format and
      extent per swapchain handle, and a corresponding
      `vkDestroySwapchainKHR` override that frees the layer's per-swapchain
      state; verify against `vkcube` resized/toggled through a couple of
      swapchain recreations with no leak (validation layer clean)
      (verified live — repeated create/destroy across many vkcube runs,
      an explicit extent-mismatch run, and with `VK_LAYER_KHRONOS_validation`
      stacked underneath once it became available: zero messages of any
      severity across instance/device/swapchain create-destroy and repeated
      presents. That stacking caught and led to fixing two real bugs along
      the way — a missing loader-data stamp on self-allocated command
      buffers, and a semaphore reused across images instead of one per
      image — see design.md's "Amendments" section)

## 3. Canvas upload and present hook

- [x] 3.1 Load `render_overlay`'s canvas + rectangle format (documented,
      versioned handoff — e.g. a small fixed binary/JSON header the
      Python side writes and the layer reads at startup) and upload it
      once per swapchain as a device-local `VkImage` via a staging
      buffer; verify the uploaded image's contents by reading it back
      in a debug build
      (the `.bsov` format: `canvas_format.py` writes it, `canvas_format.h`
      reads it, `tests/test_overlay_vulkan_canvas.py` pins the byte
      layout. Upload verified end to end — see 3.2 — rather than via a
      separate debug image read-back: screenshotting the actual
      composited output and running it back through
      `boresight.detect.detect_markers` is a strictly stronger check on
      the uploaded image's contents than reading the image back
      unrendered would have been.)
- [x] 3.2 Implement the `vkQueuePresentKHR` override: per swapchain in
      `pPresentInfo`, submit a command buffer that transitions each
      rectangle to `TRANSFER_DST_OPTIMAL`, `vkCmdCopyImage`s from the
      uploaded canvas, transitions back to `PRESENT_SRC_KHR`, waits on
      the app's `pWaitSemaphores`, signals a layer-owned semaphore, then
      calls through to the real present using that semaphore; verify
      against `vkcube` that the patches appear in the correct screen
      rectangles every frame with no validation errors
      (`VK_LAYER_KHRONOS_validation` stacked underneath)
      (verified live: ran vkcube with the layer + a real canvas,
      screenshotted the composited desktop, and ran
      `boresight.detect.detect_markers` against the screenshot — all 8
      markers decode at the correct positions, cube content renders
      untouched outside them. Also verified with `VK_LAYER_KHRONOS_validation`
      stacked underneath: zero validation messages of any severity
      across repeated presents, once the two bugs noted at 2.3 were
      fixed — a missing image-usage flag and a shared semaphore reused
      across images, both invisible without validation stacked in.)
- [x] 3.3 Verify the "presented frames remain valid" requirement
      directly: force the copy step to fail/skip in a debug build and
      confirm the frame still presents (no hang, no validation error,
      no crash)
      (verified live via two real skip paths rather than an artificial
      fault injection: no `BORESIGHT_OVERLAY_CANVAS` set, and a
      canvas/swapchain format mismatch — both log and skip drawing,
      vkcube keeps presenting normally and exits 0)
- [ ] 3.4 Verify the "tracks the current swapchain" requirement: resize
      `vkcube`'s window (or toggle its fullscreen resolution) and
      confirm the marker rectangles reposition to match the new extent
      within the next few frames, not the previous one
      (partially verified, scope narrowed — see design.md's
      "Amendments" section: a swapchain recreated at the *same* extent
      is confirmed to keep drawing correctly; a swapchain recreated at a
      *different* extent than the baked canvas is confirmed to degrade
      safely — logs once, skips drawing, no crash/hang — verified live
      by launching vkcube at a resolution that didn't match the
      pre-generated canvas. Live re-layout at the new extent is not
      implemented; relaunching regenerates the canvas instead. Flagging
      this rather than checking it off outright, since the requirement
      as written asks for repositioning, not just safety.)

## 4. Availability and diagnostics

- [x] 4.1 Implement a startup timeout: if no `vkCreateSwapchainKHR` call
      reaches the layer within a short window after `vkCreateInstance`,
      emit the actionable "this application does not present via
      Vulkan — try the window overlay or printed markers" message (to
      stderr, matching `overlay/backend.py`'s existing message shape)
      (verified live with a small harness that creates an instance +
      device and never a swapchain: the message fires at the configured
      timeout and the app continues and exits normally)
- [x] 4.2 Verify the "missing Vulkan loader" path separately: attempting
      to enable the layer where no Vulkan loader is installed produces
      the same actionable message from whatever entry point starts this
      backend (a thin Python or shell wrapper, per design), not a raw
      loader error
      (verified via unit test exercising the real code path —
      `test_no_loader_anywhere_is_refused` — rather than by uninstalling
      the system's own Vulkan loader, which would have broken this
      live desktop's own GPU-accelerated session)
- [x] 4.3 Verify the "enabled explicitly, per application" requirement:
      with the layer built and its manifest present on the system but
      *not* named in `VK_INSTANCE_LAYERS`, confirm an unrelated Vulkan
      application shows no marker patches
      (verified live: `VK_LAYER_PATH` set, manifest discoverable,
      `VK_INSTANCE_LAYERS` unset — vkcube runs with no "layer loaded"
      line and no effect)

## 5. Integration with the shared layout

- [x] 5.1 Add (or confirm/extend) a `render_overlay` output mode that
      writes its canvas + rectangles in the format task 3.1 reads, and
      a test asserting that format matches what the layer's loader
      expects byte-for-byte for a known `(screen_px, tag_px, inset_px)`
      input
      (`canvas_format.write_file` on top of `render_overlay`'s existing
      output, `tests/test_overlay_vulkan_canvas.py`)
- [x] 5.2 Add a test comparing this backend's rectangle geometry against
      `qt_backend.py`'s for the same inputs, asserting they're identical
      (guards the "same layout as the window overlay" requirement as
      the shared computation evolves)
      (`tests/test_overlay_vulkan_geometry.py`; skipped like
      `test_overlay_qt.py` when the `overlay` extra isn't installed)

## 6. Manual verification

(Deferred to the user by design during this implementation session:
this backend was verified as thoroughly as `vkcube` allows — see
sections 2-4 above, including a real screenshot of drawn markers
decoding correctly — but actually launching Blue Estate and judging the
result on screen needs a human at the display, which this session does
not have visual access to.)

- [ ] 6.1 On Blue Estate specifically (the case that motivated this
      change), launch with the layer enabled via a Steam launch-option
      prefix and confirm the marker patches are visible on screen during
      actual gameplay, exclusive fullscreen, DX9-via-DXVK
- [ ] 6.2 Confirm Boresight's existing detection pipeline solves against
      the on-screen patches from a camera pointed at the display, the
      same way it already does against the Qt overlay or printed sheet
- [ ] 6.3 Run a second, unrelated Vulkan title without the layer enabled
      and confirm no behavior change from this feature being installed
      on the system
- [ ] 6.4 Soak-test one title with the layer enabled for an extended
      play session and confirm no crash, hang, or visible corruption
      attributable to the layer

## 7. Documentation and gate

- [x] 7.1 Document this backend in README alongside "Marker overlay" and
      "Printed markers": when to reach for it, how to build it, its
      per-title Vulkan-presentation requirement, and the
      `VK_INSTANCE_LAYERS`/`VK_LAYER_PATH` launch-option activation
      (new "Vulkan present overlay" section in README.md, plus
      `native/vulkan_overlay/README.md` for build/verification detail)
- [x] 7.2 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format
      --check` and `uv run pre-commit run --all-files` clean (Python
      side unaffected)
      (374 passed; one unrelated pre-existing flaky test in
      `test_stream_e2e.py` reproduced in isolation and passed on retry —
      not touched by this change. ruff check/format and pre-commit all
      clean.)
- [x] 7.3 Run `openspec validate add-vulkan-present-overlay --strict`
      ("Change 'add-vulkan-present-overlay' is valid")
