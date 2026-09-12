## Context

`src/boresight/overlay/` today has one backend: a Qt window
(`qt_backend.py`) drawing the canvas `render.py`'s `render_overlay`
produces, gated by `backend.check_supported`/`require_toolkit`, which
raise `OverlayUnavailableError`/`OverlayDependencyError` with an
actionable message and a pointer at printed markers
(`PRINTED_MARKERS_HINT`). See proposal.md for why that backend cannot
reach an exclusive-fullscreen application no matter how it is flagged.

The repo is pure Python today (`pyproject.toml`, `uv`-managed); nothing
in the current toolchain compiles C or links against system libraries.
`render_overlay(screen_px, tag_px, inset_px)` returns a grayscale numpy
canvas plus a list of `(x, y, width, height)` rectangles — the only
parts of a frame actually drawn — and is already the shared source both
`qt_backend.py` and (per proposal) this new backend must agree with.

## Goals / Non-Goals

**Goals:**
- Get the marker patches into a game's presented frames from inside its
  own process, using the Vulkan loader's layer mechanism — the same
  extension point MangoHud, RenderDoc and Steam's overlay already use —
  rather than anything resembling code injection or memory patching.
- Keep the native component fully optional: absent, it must not affect
  building, installing, or running the rest of Boresight.
- Reuse `render_overlay`'s canvas and rectangles as the geometry
  contract, so the two backends can never disagree about where tags go.

**Non-Goals:**
- A rendering pipeline (shaders, descriptor sets, render passes). The
  patches are a fixed canvas blitted into fixed rectangles — a transfer
  operation, not a draw call.
- Supporting wined3d's OpenGL path, D3D12 titles specifically (already
  covered for free — VKD3D-Proton presents through the same
  `vkQueuePresentKHR` this layer hooks), or non-Proton/non-Vulkan
  titles. A title outside Vulkan presentation is explicitly the
  window-overlay/printed-marker case.
- System-wide (implicit) layer installation. Implicit layers run for
  every Vulkan process on the machine by default, which is a much wider
  blast radius than this feature needs or than a user modifying one
  game's launch options should have to accept.
- Bundling a Vulkan loader, headers, or build toolchain into Boresight's
  default install path.

## Decisions

**An explicit Vulkan layer, enabled per-launch, not an implicit one.**
The Vulkan loader distinguishes the two: an implicit layer manifest
(`.../implicit_layer.d/`) activates for every Vulkan instance created on
the system unless separately disabled; an explicit layer only activates
when named in `VK_INSTANCE_LAYERS`, which a user sets per-launch (a
Steam launch-option prefix, same shape as `MANGOHUD=1 %command%`).
`vulkan-present-overlay`'s own requirement — enabled explicitly, per
application — rules out the implicit path outright.

**Pure transfer, no graphics pipeline.** `render_overlay` already
reduces "what gets drawn" to a canvas plus a short list of rectangles.
The layer uploads that canvas once per swapchain (staging buffer →
device-local `VkImage`) and, per present, issues one `vkCmdCopyImage`
per rectangle from that image into the swapchain image, bracketed by
layout transitions (`PRESENT_SRC_KHR → TRANSFER_DST_OPTIMAL` and back).
No shader, pipeline, or render pass exists in this design at all.
Alternative considered: a full graphics pass (vertex/fragment shaders
sampling the canvas as a texture) — rejected as strictly more surface
area (pipeline cache, shader compilation, descriptor lifetime) for
output identical to a copy, since the patches are opaque and
axis-aligned.

**Hook `vkQueuePresentKHR` only; capture state through
`vkCreateInstance`/`vkCreateDevice`/`vkCreateSwapchainKHR`.** This is
the standard shape of a Vulkan layer: `vkCreateInstance` and
`vkCreateDevice` are intercepted not to change their behavior but to
read the next layer's `GetInstanceProcAddr`/`GetDeviceProcAddr` off the
`pNext` chain and build a per-instance/per-device dispatch table;
`vkCreateSwapchainKHR` is intercepted to learn each swapchain's images,
format and extent (needed for the "tracks the current swapchain"
requirement); `vkQueuePresentKHR` is the only call whose behavior this
design actually changes. Every other Vulkan call passes straight
through unmodified.

**The present hook submits its own command buffer ahead of the real
present, chained through semaphores — it does not touch the
application's own command buffers.** Order of operations inside the
hook, for each swapchain in `pPresentInfo`:
1. Record (or reuse, if geometry hasn't changed) a command buffer that
   transitions each marker rectangle to `TRANSFER_DST_OPTIMAL`, copies
   from the uploaded canvas image, and transitions back to
   `PRESENT_SRC_KHR`.
2. Submit it on the same queue, waiting on the application's own
   `pWaitSemaphores` and signaling a layer-owned semaphore.
3. Call the real `vkQueuePresentKHR`, substituting that layer-owned
   semaphore as the sole wait semaphore, `pSwapchains` /
   `pImageIndices` unchanged.

   This ordering is what "presented frames remain valid" and "leaves
   the application's rendering untouched outside the rectangles" both
   rest on: the copy only ever runs after the application's own
   rendering has finished (per its wait semaphores) and produces a
   layout the presentation engine already expects.

**Failure is a startup-time diagnostic, not a per-frame one.** Whether
the target presents through Vulkan at all is knowable as soon as
`vkCreateInstance`/`vkCreateSwapchainKHR` either do or don't get called
through this layer within a short startup window; a title that never
creates a Vulkan swapchain (wined3d/GL path, or a title that hasn't
reached its render loop yet) is reported once, the same
`OverlayUnavailableError`-shaped message
(`overlay/backend.py`'s existing pattern) naming the window overlay and
printed markers, rather than leaving the operator to conclude "nothing
happened" on their own frame after frame.

**New component lives outside `src/boresight/`, e.g.
`native/vulkan_overlay/`, with its own CMake/meson build.** Keeping it
out of the Python package's own tree keeps `uv sync`/`pip install`
untouched — no C toolchain becomes a transitive requirement of
installing Boresight — mirroring how the Qt overlay is already gated
behind an `[overlay]` extra rather than a core dependency. The exact
build system (CMake vs. meson) and directory name are implementation
detail for tasks.md to settle, not a spec-level concern.

## Risks / Trade-offs

- **A bug in the present hook can crash or corrupt the host game**,
  since the layer runs inside the game's own process and address space
  — a materially higher blast radius than the Qt overlay, whose worst
  failure mode is its own window misbehaving. → Mitigated by the design
  itself: no application command buffers or resources are touched, only
  a self-contained command buffer against a self-contained image;
  validated first against Vulkan's own validation layers
  (`VK_LAYER_KHRONOS_validation`) stacked underneath this one during
  development, before manual verification against a real game.
- **DXVK/VKD3D-Proton version drift could change assumptions this
  design leans on** (e.g., how many swapchains a title creates, whether
  it recreates one on every resize vs. reusing it) — the requirement
  "tracks the current swapchain" is the guard for this, but the
  implementation should degrade to the startup-diagnostic failure mode
  rather than drawing into a stale or wrong image if state ever
  disagrees with reality.
- **Only covers the Vulkan-presenting subset of games** — accepted per
  proposal.md's explicit scope; the window overlay and printed markers
  remain the answer for anything else, and the startup diagnostic is
  what tells an operator which case they're in.
- **A second geometry consumer for `render_overlay` raises the cost of
  changing it** — any future change to canvas/rectangle shape now needs
  checking against both a Python (Qt) and a C (Vulkan layer) consumer.
  Accepted: the alternative (each backend computing its own layout) is
  exactly what `marker-overlay`'s "drawn and solved layout are the same
  layout" requirement exists to prevent.

## Open Questions

- Exact on-disk location and build system for the native component
  (`native/vulkan_overlay/` + CMake vs. meson, or elsewhere) — narrow
  enough to settle in tasks.md without touching the spec or this
  design's decisions.
