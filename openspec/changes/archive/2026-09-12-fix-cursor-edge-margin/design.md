## Context

`cursor-injection`'s `UinputCursorBackend` device is deliberately tagged
`ID_INPUT_TOUCHSCREEN` (verified against a live X11 session in that
capability's original design, and reconfirmed in `add-trigger-click`):
it's the one capability combination among those tested (touchscreen,
mouse, tablet) that gets libinput to place the core pointer directly
at the reported coordinate instead of running it through relative
acceleration. `aim-pipeline` separately clamps the emitted position
into `[0.0, 1.0]` before it reaches that device — both defensively
(the solved aim point can legitimately be off-panel) and, more subtly,
whenever the real solve just happens to land at or very near the
panel's physical edge, which is unremarkable since the markers that
make solving possible sit at the bezel.

The interaction between these two facts is the bug: several desktop
environments bind an action to a pointer reaching the literal screen
edge or corner (KDE's Electric Borders, touch edge-swipe gestures like
Overview/Show Desktop), and our touchscreen-tagged device reaching
exactly `x=0`/`x=width-1` (etc.) is indistinguishable, from the
window manager's point of view, from a user's finger doing the same
thing on a real touchscreen. Observed effect: windows minimizing or
rearranging themselves during ordinary use, with no code-level error
to point at.

## Goals / Non-Goals

**Goals:**
- The cursor device never reports the literal edge coordinate, in
  either axis, regardless of whether the position came from the
  defensive off-panel clamp or a genuine near-edge solve.
- The change is invisible to normal aiming — the margin is small
  enough that it doesn't cost usable aim range in any way a player
  would notice.

**Non-Goals:**
- Disabling or reconfiguring desktop-environment edge gestures.
  Environment-specific (KDE here), not something the project can rely
  on being present to configure, and orthogonal to what this pipeline
  controls.
- Distinguishing which desktop environment or gesture is actually
  responsible. Not knowable in general, and unnecessary — never
  emitting the literal edge coordinate sidesteps every variant of this
  class of interference at once.
- A configurable margin. Nothing today needs the number to vary; a
  constant is the smallest thing that fixes the problem.

## Decisions

**`EDGE_MARGIN = 0.01` (1% of the panel), applied inside
`_clamp_unit`, not as a separate step.** `_clamp_unit` is already the
single place both the defensive off-panel case and a legitimate
near-edge solve funnel through before reaching the backend, so
narrowing its bounds from `[0.0, 1.0]` to `[EDGE_MARGIN, 1.0 -
EDGE_MARGIN]` covers both without adding a second code path. 1% keeps
the change well clear of typical edge-gesture activation zones (KDE's
Electric Borders are pixel-exact at the literal edge; touch edge-swipe
recognition in other environments commonly uses a wider band, on the
order of tens of pixels) while being small against the panel: about
19px on a 1920px-wide display, 11px on 1080px-tall — smaller than the
~18mm real-world accuracy figure README already documents for an
aim point inside the marker hull.

**Fixed fraction of the panel, not a fixed pixel count.** The pipeline
works in normalized `[0, 1]` coordinates throughout and has no view of
the actual device pixel resolution (that mapping happens later, in
`inject.py`'s `ABS_MAX` conversion) — a fixed pixel margin would need
plumbing resolution into a module that currently has no reason to know
it. A fixed fraction degrades gracefully across panel sizes without
that plumbing.

## Risks / Trade-offs

[The outermost 1% of each axis is no longer reachable at the exact
edge] → Accepted; imperceptible in play, and still well within the
accuracy already documented for a solve that has the aim point inside
the visible markers' hull.

[A different desktop environment could bind edge gestures to a wider
activation band than 1%, reintroducing the same symptom] → No general
fix exists without knowing the environment; 1% is chosen to clear the
one case actually observed (KDE) with margin to spare. If a wider band
turns out to be needed for another environment, `EDGE_MARGIN` is a
single constant to change.

## Migration Plan

Additive/corrective only — no wire format, API, or dependency changes.
Existing recordings/fixtures that assert an exact `(0.0, 1.0)`-style
clamped position are updated to expect `(EDGE_MARGIN, 1.0 -
EDGE_MARGIN)` instead.
