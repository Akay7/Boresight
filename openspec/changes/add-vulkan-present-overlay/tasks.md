## 1. Native project scaffold

- [ ] 1.1 Create `native/vulkan_overlay/` with a CMake build producing
      `libboresight_overlay.so` against the system Vulkan loader/headers
      (`find_package(Vulkan)`), and verify it builds clean on a machine
      with the Vulkan SDK/loader installed
- [ ] 1.2 Write the explicit-layer manifest (`VK_LAYER_boresight_overlay`,
      `type: GLOBAL`, pointing at the built library) and verify
      `vulkaninfo` (or `vkjson_info`) lists the layer when
      `VK_LAYER_PATH` points at it
- [ ] 1.3 Confirm the default `uv sync` / `pip install boresight` path is
      completely unaffected — no reference to `native/` from
      `pyproject.toml` or the Python package

## 2. Layer entry points and dispatch capture

- [ ] 2.1 Implement `vkNegotiateLoaderLayerInterfaceVersion`,
      `GetInstanceProcAddr`, `GetDeviceProcAddr`, and confirm the loader
      successfully calls into the layer (log line on load) when the
      layer is enabled via `VK_INSTANCE_LAYERS` for a minimal Vulkan
      sample app (e.g. `vkcube`)
- [ ] 2.2 Implement `vkCreateInstance`/`vkCreateDevice` overrides that
      walk the `pNext` chain for the next layer's `GetProcAddr` and
      build a per-instance/per-device dispatch table; verify every
      other Vulkan call reaches `vkcube` unchanged (it still renders
      correctly with the layer enabled and doing nothing yet)
- [ ] 2.3 Implement `vkCreateSwapchainKHR` capture of images, format and
      extent per swapchain handle, and a corresponding
      `vkDestroySwapchainKHR` override that frees the layer's per-swapchain
      state; verify against `vkcube` resized/toggled through a couple of
      swapchain recreations with no leak (validation layer clean)

## 3. Canvas upload and present hook

- [ ] 3.1 Load `render_overlay`'s canvas + rectangle format (documented,
      versioned handoff — e.g. a small fixed binary/JSON header the
      Python side writes and the layer reads at startup) and upload it
      once per swapchain as a device-local `VkImage` via a staging
      buffer; verify the uploaded image's contents by reading it back
      in a debug build
- [ ] 3.2 Implement the `vkQueuePresentKHR` override: per swapchain in
      `pPresentInfo`, submit a command buffer that transitions each
      rectangle to `TRANSFER_DST_OPTIMAL`, `vkCmdCopyImage`s from the
      uploaded canvas, transitions back to `PRESENT_SRC_KHR`, waits on
      the app's `pWaitSemaphores`, signals a layer-owned semaphore, then
      calls through to the real present using that semaphore; verify
      against `vkcube` that the patches appear in the correct screen
      rectangles every frame with no validation errors
      (`VK_LAYER_KHRONOS_validation` stacked underneath)
- [ ] 3.3 Verify the "presented frames remain valid" requirement
      directly: force the copy step to fail/skip in a debug build and
      confirm the frame still presents (no hang, no validation error,
      no crash)
- [ ] 3.4 Verify the "tracks the current swapchain" requirement: resize
      `vkcube`'s window (or toggle its fullscreen resolution) and
      confirm the marker rectangles reposition to match the new extent
      within the next few frames, not the previous one

## 4. Availability and diagnostics

- [ ] 4.1 Implement a startup timeout: if no `vkCreateSwapchainKHR` call
      reaches the layer within a short window after `vkCreateInstance`,
      emit the actionable "this application does not present via
      Vulkan — try the window overlay or printed markers" message (to
      stderr, matching `overlay/backend.py`'s existing message shape)
- [ ] 4.2 Verify the "missing Vulkan loader" path separately: attempting
      to enable the layer where no Vulkan loader is installed produces
      the same actionable message from whatever entry point starts this
      backend (a thin Python or shell wrapper, per design), not a raw
      loader error
- [ ] 4.3 Verify the "enabled explicitly, per application" requirement:
      with the layer built and its manifest present on the system but
      *not* named in `VK_INSTANCE_LAYERS`, confirm an unrelated Vulkan
      application shows no marker patches

## 5. Integration with the shared layout

- [ ] 5.1 Add (or confirm/extend) a `render_overlay` output mode that
      writes its canvas + rectangles in the format task 3.1 reads, and
      a test asserting that format matches what the layer's loader
      expects byte-for-byte for a known `(screen_px, tag_px, inset_px)`
      input
- [ ] 5.2 Add a test comparing this backend's rectangle geometry against
      `qt_backend.py`'s for the same inputs, asserting they're identical
      (guards the "same layout as the window overlay" requirement as
      the shared computation evolves)

## 6. Manual verification

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

- [ ] 7.1 Document this backend in README alongside "Marker overlay" and
      "Printed markers": when to reach for it, how to build it, its
      per-title Vulkan-presentation requirement, and the
      `VK_INSTANCE_LAYERS`/`VK_LAYER_PATH` launch-option activation
- [ ] 7.2 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format
      --check` and `uv run pre-commit run --all-files` clean (Python
      side unaffected)
- [ ] 7.3 Run `openspec validate add-vulkan-present-overlay --strict`
