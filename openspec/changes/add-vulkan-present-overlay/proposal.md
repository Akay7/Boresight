## Why

`marker-overlay`'s window-based overlay is invisible against a game
running exclusive fullscreen: verified on Blue Estate (Unreal Engine 3
over Proton/DXVK, `Fullscreen=True` in its engine config) that the
overlay window is correctly topmost in the compositor's own stacking
order (`_NET_WM_STATE_ABOVE`, last in `_NET_CLIENT_LIST_STACKING`) and
still does not appear on screen, because exclusive fullscreen page-flips
the game's swapchain straight to the display and bypasses compositing
entirely — there is no window stack for an overlay window to win a place
in. No amount of window-manager hinting fixes this; it needs to draw
somewhere compositing cannot skip. That place is inside the game's own
swapchain, which is exactly how MangoHud, RTSS and the Steam overlay
already solve the identical problem for FPS counters: a Vulkan layer
that hooks the present call from inside the game's process.

## What Changes

- Add a Vulkan implicit-loader-chain layer (a C shared library) that
  hooks `vkQueuePresentKHR` inside a game's own process and copies the
  same marker canvas `render_overlay` already produces
  (`src/boresight/overlay/render.py`) into the presented swapchain
  image's marker rectangles, before the real present call runs.
- The layer is a pure blit: the canvas is uploaded once per swapchain as
  a `VkImage`, and each present does a plain `vkCmdCopyImage` per
  rectangle — no shader, no pipeline, no render pass, matching the
  existing overlay's "draw only the patches, touch nothing else" model.
- Activated per-launch as an explicit layer (`VK_INSTANCE_LAYERS` +
  `VK_LAYER_PATH`, e.g. as a Steam launch-option prefix), never
  installed system-wide as an implicit layer.
- Covers any title presenting through real Vulkan calls, which includes
  DXVK/VKD3D-Proton-translated D3D9/11/12 titles as well as native
  Vulkan ones. **Explicitly out of scope for this change**: titles
  presenting through wined3d's GL path or any non-Vulkan swapchain, the
  on-screen trigger button (unaffected — it already lives on the phone,
  not this overlay), and system-wide/implicit layer installation.
- A new, optional native component alongside the existing pure-Python
  package (mirrors how the Qt overlay is already an opt-in extra):
  building or installing it is never required for the rest of Boresight
  to work, and its absence fails the same actionable-message way
  `overlay/backend.py` already fails for a missing Qt install or an
  unsupported platform, pointing back at the Qt overlay or printed
  markers.

## Capabilities

### New Capabilities
- `vulkan-present-overlay`: drawing the marker patches inside a game's
  own Vulkan presentation path via a loader layer, so they appear over
  content a window-based overlay cannot reach (exclusive fullscreen),
  including the layer's availability checks and fallback messaging when
  a title does not present through Vulkan.

### Modified Capabilities
(none — `marker-overlay` describes the window-based overlay as-is and
keeps every existing requirement; this change adds a sibling backend
rather than changing it. The shared canvas/rectangle computation
`marker-overlay` already specifies is reused, not altered.)

## Impact

- New native component (proposed under `native/vulkan_overlay/` or
  similar, finalized in design.md): C source, Vulkan layer manifest
  JSON, and a CMake/meson build, kept out of the default `uv sync` /
  `pip install` path.
- `src/boresight/overlay/render.py`: no code change, but its canvas +
  rectangle output becomes a contract consumed by a second backend
  (Python and native), so any change there now has two consumers.
- No change to `server.py`, the wire protocol, `pipeline.py`, or the
  phone client — this only replaces how marker patches reach the
  screen in the exclusive-fullscreen case, nothing about aim solving or
  the trigger.
- Packaging/docs: README gains a new section alongside "Marker overlay"
  and "Printed markers" describing when to reach for this backend, how
  to build it, and its per-title Vulkan-presentation requirement.
