## Context

`qt_backend.py`'s `run()` computes the overlay's usable area from
`screen.availableGeometry()` — Qt's own panel-avoidance, already
correct on at least one real multi-monitor setup this project has been
tested on (a KDE panel on the primary/laptop display was detected and
reported: "46px reserved by desktop panels"). On a second monitor in
that same setup, `availableGeometry()` reported zero reservation despite
a visible taskbar there. Traced directly: XWayland's `_NET_WORKAREA`
(what Qt's XCB platform plugin reads) is a single rectangle for the
whole virtual desktop per the EWMH spec, not one per monitor. Where that
one rectangle's reserved band happens not to overlap a given monitor's
own bounds, every screen outside that band reports zero reservation,
regardless of what is actually drawn there.

See proposal.md for the concrete evidence (the server's own overlay
startup log line for the affected monitor).

## Goals / Non-Goals

**Goals:**
- Let a user correct for a monitor Qt under-reports, without touching
  code, on the exact setup that surfaces the problem.
- Change nothing about today's behavior when the value is left unset.

**Non-Goals:**
- Detecting this situation automatically. There is no general,
  reliable way to know a monitor has an undetected panel from inside
  the overlay process — the whole problem is that the environment's own
  reporting mechanism (EWMH `_NET_WORKAREA`) does not carry that
  information per-monitor. A per-monitor query would need a
  non-X11/EWMH source (e.g. a native Wayland output-management
  protocol), which is a materially bigger change than this one and not
  attempted here.
- Reworking the overlay to run natively on Wayland instead of forced
  XWayland (`_force_xwayland_on_wayland` exists for
  `WindowTransparentForInput` to work at all, from an earlier change) —
  out of scope; this fix works within that existing constraint.

## Decisions

**A single scalar margin, subtracted from all four sides of the
already-detected available area.** Not a per-edge value: the concrete
problem observed is a monitor-specific miss, not an edge-specific one,
and a single number is what `--tag-px`/`--inset-px` already look like
on the same command line. Applied as
`available.adjusted(margin, margin, -margin, -margin)` in Qt's own
`QRect` semantics, after `screen.availableGeometry()` and before
`area_px` is derived from it — so it composes with whatever Qt already
found rather than replacing it, and a correctly-detected monitor (the
laptop panel case) can be left at zero and keeps working exactly as
before.

**Zero by default, and folded into the existing `reserved` bookkeeping
rather than reported separately.** `_start_screen_markers`'s log line
already computes `reserved` from the gap between `screen_px` and
`area_px`; a manual margin shrinks `area_px` the same way an
auto-detected one does, so it shows up in that same number with no
separate accounting needed. A caller reading the log cannot tell
"Qt found this" from "a human corrected for this," which is fine here —
either way it is the reservation actually in effect.

**Threaded through the same path `--display` already uses, and given
its own server-level flag.** `--display` exists as a
`MarkerSourceController`/`create_app` parameter but was never wired to
`server.py`'s own CLI — an existing gap, not something this change
expands scope to fix. `extra_margin_px` gets the treatment `--display`
should probably also have: a real CLI flag on `python -m
boresight.server`, since the whole point of this change is for someone
running the real server (not just the standalone overlay script) to be
able to set it.

**A runtime route, not just a startup flag — because dialing this in is
inherently iterative.** The margin exists to compensate for something
the operator can only judge by eye (does the tag now clear the
taskbar?), and a CLI flag means restart-edit-restart per guess. `POST
/markers/overlay-margin` sets `MarkerSourceController`'s
`_overlay_extra_margin_px` and, if on-screen markers are currently
active, restarts the overlay through the same `_start_screen_markers()`
path `select()` already uses — same error handling
(`MarkerSourceError` → 409, printed markers stay active), same
"switch reaches an already-streaming phone" property, for free. Setting
it while printed markers are active just updates the value for next
time on-screen markers are selected — no need to require a source
switch first.

**Server-wide, not per-connection.** Matches how the marker source
itself works: one `MarkerSourceController` per server process, not one
per phone session. Two phones adjusting it would race the same way two
phones switching marker source already can, which is an accepted,
pre-existing property of that design, not something new here.

**A stepper on the phone, not a text field.** The existing marker
source and debug controls are tap targets, not text input, and a phone
keyboard is a worse way to enter a number you are choosing by looking
at the screen rather than typing a known value. `−`/`+` buttons move
the value by a fixed step and re-send it immediately, mirroring
`selectMarkerSource`'s pattern (disable during the request, restore
after) exactly.

## Risks / Trade-offs

- **A margin large enough to exceed the available area produces a
  degenerate (zero or negative) usable rectangle.** → Not specially
  guarded here: `overlay_layout`'s existing `OverlayGeometryError` for
  tags that do not fit the display already covers "the usable area is
  too small," and a margin this wrong is a configuration mistake to
  correct, not a case to silently recover from.
- **One number for all four sides cannot express "only the bottom is
  wrong."** → Accepted; the observed problem is monitor-level under-
  detection, not a documented case of needing different margins per
  edge, and a single knob is simpler to reason about and to test.
- **Restarting the overlay on every margin change means a brief gap in
  on-screen markers while the operator is actively dialing it in.** →
  Accepted: it is the same gap a manual source switch already causes,
  bounded by `GEOMETRY_TIMEOUT_S`, and dialing in a margin is a one-time
  setup step, not something done mid-game.
