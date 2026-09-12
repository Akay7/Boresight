## Context

README has carried this idea in Future work since the beginning:

> **On-screen markers.** Render the tags as a thin border overlay
> instead of printing them. They become emissive, so the exposure
> problem disappears, and their positions are known exactly in screen
> pixels, so calibration disappears too.

What makes it worth building now is that everything downstream exists:
`marker_map.py` defines the layout shape, `pipeline.py` consumes it, and
`solve.py` does not care where the numbers came from. The overlay is a
new *producer* plugging into a socket that is already there.

The requirement to support X11, Wayland and Windows is what shapes every
decision below. The three do not agree on how a window is placed above
others, and they do not agree on how a window declines input.

## Goals / Non-Goals

**Goals:**

- Tags on the screen that the camera can read and the mouse cannot hit.
- One code path for X11 and Windows; Wayland handled where the
  compositor permits it and reported honestly where it does not.
- The renderer and the solver structurally incapable of disagreeing
  about where a tag is.
- A default install that gains no graphical dependency.

**Non-Goals:**

- macOS. No hardware to verify it on, and an unverified backend is
  worse than an absent one.
- Drawing into a game's own render loop (shader injection, emulator
  patch). It would solve the fullscreen-exclusive limitation below, and
  it is a different project.
- Any change to detection, solving or the pipeline.
- Replacing printed markers. They keep working; this is a second source.

## Decisions

### Qt (PySide6) as the primary backend, covering X11 and Windows

`Qt.WindowTransparentForInput` is the whole feature in one flag, and it
maps to the correct platform primitive on both targets: an empty XShape
*input* region on X11, and `WS_EX_TRANSPARENT` on Windows. Combined with
`FramelessWindowHint | WindowStaysOnTopHint` and
`WA_TranslucentBackground`, one widget covers two of the three
platforms.

*Alternative rejected — `python-xlib` directly:* about a megabyte
against Qt's hundred-plus, and for an X11-only project it would be the
better answer. It cannot reach Windows at all, which the brief requires.

*Alternative rejected — a web overlay in a borderless browser window:*
no browser exposes click-through to page content.

### Qt is an optional dependency group, not a core one

`[project.optional-dependencies] overlay = [...]`, installed with
`uv sync --extra overlay`.

*Why it matters here specifically:* this project already went out of its
way to stay headless — `opencv-python-headless` is chosen precisely to
avoid dragging in a GUI stack. Putting Qt in the core dependencies would
undo that for every user of the server, most of whom will run printed
markers. Someone who wants an overlay can afford to ask for it.

Missing dependencies are reported as "install the overlay group", not as
an `ImportError` traceback.

### Wayland is conditional, and says so

Wayland deliberately denies ordinary clients the ability to place
themselves above other windows — that is a design position, not a gap.
The sanctioned route is the `wlr-layer-shell` protocol, which KWin and
the wlroots compositors implement and **GNOME's Mutter does not**.

So: the input-transparency half works everywhere on Wayland
(`wl_surface.set_input_region` with an empty region, which is what Qt's
flag becomes). The always-on-top half works only where layer-shell
exists.

The overlay therefore probes at startup and, where it cannot get a layer
surface, **exits with an explanation naming printed markers** rather
than showing a window. The failure this avoids is the ugly one: a
surface that renders but sits in the normal stacking order and takes
input, which would eat the gun's own clicks and look like a Boresight
bug rather than a compositor limitation.

*Why not silently fall back to XWayland:* it often would work, and it
would also silently change the coordinate space and the input path under
the user. An explicit message is more useful than a fallback nobody
knows happened.

### The layout is a pure function, not a file or a message

    overlay_layout(screen_px, tag_px, inset_px) -> MarkerMap

The overlay draws from it. The pipeline solves against it. Both call it;
nothing is written, sent, or transcribed.

*Why this over writing a `markers.toml`:* a file introduces a moment
where the drawn layout and the solved layout can differ — the overlay
restarts on a different monitor, the file is stale, two processes race.
The spec requirement that they "cannot disagree" is only actually true
if there is one computation. This makes the guarantee structural rather
than procedural.

### Units: pixels converted by one uniform scale

Marker coordinates are nominally millimetres. The overlay knows pixels.
It converts with a single scale factor applied to both axes.

The scale does not have to be correct, and this is worth being explicit
about. The pipeline's output is `aim_mm / screen_mm`; if every marker
position and the screen size are all `pixels × k`, then `k` cancels
exactly. What must *not* happen is a different scale per axis, which
would distort the aspect ratio and bend the homography — so the scale is
uniform by construction rather than read from a display's reported
physical dimensions, which are frequently wrong or absent in EDID.

### Tags get an opaque quiet-zone patch, not alpha compositing

Each tag is drawn on a solid patch extending beyond it on all sides,
rather than blended over the pixels below.

*Why:* the detector finds tags by thresholding and contour-following. A
tag composited over bright game content has no reliable edge, and busy
content beside a tag manufactures false quad candidates. The patch costs
a few percent of screen area — which README already predicted — and buys
detection that does not depend on what is being played.

### Placement: inset from the screen edges, not on the bezel

Tags sit just inside the display's own edges. That is what "on top of
the existing picture" means, and it has a side benefit worth recording:
the close-range dropout measured on the printed layout — zero markers
detected below 1400mm, because bezel tags fall outside the frustum —
largely disappears, because the tags are now inside the panel rather
than around it.

Tag size follows README's sizing table rather than taste: roughly 3px
per bit cell, 6 cells across including the quiet border, so a tag has to
survive minification to about 20px in the camera image at playing
distance. The default is derived from that and is configurable.

### Overlay runs as its own process

It owns a GUI event loop; the server owns an async I/O loop. Rather than
marry them, the overlay is launched separately and the server is told
which layout to use. Since the layout is a pure function of
configuration, the two need no channel between them.

## Risks / Trade-offs

**An overlay cannot draw above a fullscreen-exclusive application** →
Not mitigable at this layer, on any of the three platforms. Emulators
must run borderless-windowed. It is the same constraint README already
records for synthetic input reaching fullscreen-exclusive titles, and it
belongs in the same paragraph.

The obvious counter-example is worth answering, because it looks like a
refutation and is not: FPS counters *do* draw over exclusive fullscreen.
They manage it by not being overlays at all. RTSS, the Steam and Discord
overlays, and MangoHud run **inside the game's process** and hook the
presentation call — `IDXGISwapChain::Present`, `glXSwapBuffers`,
`vkQueuePresentKHR` — drawing into the back buffer before it is handed
to the display. By the time the frame is presented it already contains
the counter, so there is nothing for a compositor to stack. MangoHud
does it as a Vulkan implicit layer, which is a documented extension
point rather than a hack; the Windows tools do it by DLL injection.

That approach would also make the Wayland limitation below disappear,
since a swapchain-composited marker never needs a surface the compositor
has to place. It was considered and left out for three reasons: a
software-rendered or SDL-blitting emulator presents no swapchain to
hook, it requires launching the game *through* the layer rather than
running a tool beside it, and on Windows it means injection — which is
precisely what anti-cheat is built to detect. Irrelevant for Mesen and
MAME, but it makes the Windows story much uglier than the Linux one.

Since every target emulator runs borderless-windowed happily, the
overlay window ships first. A graphics-API layer is the second backend
to build if the limitation turns out to bite in practice.

**Qt is by far the largest dependency in the project** → Confined to an
optional group, so it is opt-in and a default install is unchanged.

**Wayland support is partial and depends on the compositor** → Handled
by refusing to start with an explanation rather than degrading quietly.
The user's own session is X11, so the primary path is the well-supported
one; Wayland is the migration risk rather than today's problem.

**Tags occlude a few percent of the picture** → Inherent to the
approach and predicted in README. The mitigation is that they are small
and at the edges. Anyone who objects can keep using paper, which is why
the two sources stay alternatives.

**Screen content could still produce false detections near a tag** →
The quiet-zone patch is the defence, and it is the reason for drawing
opaquely rather than compositing. Unquantified until it meets a real
camera, like everything else in the project so far.

**None of this is verified on Windows** → No Windows machine in the
loop. The Qt flag is documented to map to `WS_EX_TRANSPARENT`, but that
is a claim from documentation, not a measurement, and the tasks say so.
