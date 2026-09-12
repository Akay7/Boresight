## Context

`solve.py` defines the aim point as the image centre pushed through the
inverse homography. Every number the system reports downstream — the
normalized position, the hull flag, the emitted cursor — descends from
that one pixel, and that pixel is currently unmarked on the only screen
the operator is looking at while holding the gun. The phone shows the
preview and a column of numbers; it does not show where in that preview
the numbers came from.

The result is that a mis-aimed cursor has at least four
indistinguishable causes: the camera is not pointed where the operator
thinks, the layout in `markers.toml` does not match the physical tags,
the homography is fitted from markers that do not enclose the aim point
(already flagged, but only as a boolean), or the normalize-and-clamp
step in `pipeline.py` disagrees with the solve. Nothing on the phone
separates them.

This is a debug view spanning three modules — the pipeline computes the
geometry, `video-ingest`'s telemetry carries it, the client draws it —
which is why it gets a design doc despite adding no new subsystem.

## Goals / Non-Goals

**Goals:**
- Mark the aim pixel on the preview, unconditionally and without server
  involvement, so "where is the camera pointing" has an answer even
  when nothing solves and even when the connection is down.
- Make the mouse-versus-camera comparison mechanical rather than
  eyeballed: draw the *emitted* cursor position back in image space and
  let the operator see whether it coincides with the reticle.
- Make a wrong homography visibly wrong, by drawing the screen
  rectangle it predicts over the live image of the actual screen.
- Attribute a bad frame to its cause: which tags were seen, which of
  them the layout knows about, how well the fit reprojects.
- Cost nothing when it is off — no extra bytes on the wire, no extra
  work in `process_frame`.

**Non-Goals:**
- Changing what is solved or emitted. The debug path reads the
  homography `solve.py` already returns and feeds nothing back.
- Frame-accurate registration of the overlay against the live video.
  See the staleness decision below; this deliberately draws the newest
  geometry over the current image and says so.
- Drawing anything on the PC's marker overlay (`overlay/`). The
  question is what the camera sees, and the camera is the phone's.
- A recorded/exportable debug trace, or an on-PC debug window. Both are
  separate features; this one is what the person holding the gun can
  see while holding it.
- Undistortion. Marker corners and the projected rectangle are drawn in
  the same distorted image space the detector reported them in, which
  is the space the comparison has to happen in anyway.

## Decisions

**The reticle is drawn by the client alone, at the geometric centre of
the preview element, and never from server data.** The aim point is the
image centre by construction, so the centre of the element showing that
image *is* the aim point — no coordinate transport, no scaling, no
round trip. `object-fit: contain` letterboxes the video but preserves
its centre at the element's centre, so this holds at any aspect ratio.
Making the reticle server-driven was considered and rejected: it would
go blank on exactly the frames (no markers, connection dropped, solve
failed) where the operator most needs to know where they are pointing,
and it would introduce a way for the mark to be *wrong* about a fact
that is definitionally true.

**The overlay draws the emitted cursor position, not the solved aim
point.** Pushing `aim_point_mm` back through the same homography it
came from is an algebraic identity: it returns the image centre and
proves nothing. The value worth drawing is the number that actually
left the pipeline — `FrameResult.position`, after division by
`screen_size_mm`, after `_clamp_unit`'s edge margin, after rounding for
the wire — multiplied back up to millimetres and pushed through the
homography into image pixels. That path can disagree with the reticle,
and when it does, the disagreement is precisely the bug: an axis
convention, a screen size that does not match the panel, a clamp
firing when it should not. This is the one drawing that answers the
question the change exists for, and it is only meaningful because it is
computed the long way round.

**Debug geometry travels in image pixels alongside the decoded image
size, not normalized to [0, 1].** Normalizing would make the client's
scaling trivial and would hide the thing most worth catching: the
server decoding a different resolution than the camera granted.
`phone-client` already requires reporting the granted resolution
because browsers silently substitute one; sending `image_px` lets the
client put the server's view of the frame next to the camera's and make
a mismatch visible instead of silently rescaling it away.

**Debug output is opt-in per frame in the pipeline, per session on the
wire, and absent — not null — when off.** `process_frame` gains a
keyword-only `debug: bool = False` and `FrameResult` gains
`debug: FrameDebug | None`. A per-call parameter rather than a
constructor flag because `MarkerSourceController` hands the *same*
`AimPipeline` to every session: a constructor flag would make one
phone's debug toggle change what another phone's frames compute, which
is the kind of shared hidden state `pipeline.py`'s "stateless by
construction" docstring exists to rule out. On the wire, a session
sends `{"type": "debug", "enabled": true}` and `as_message` starts
including the extra keys; until then the payload is byte-for-byte what
it is today. Omitting rather than nulling means a client that never
asked cannot half-render an empty overlay, and keeps the default
20-messages-per-second telemetry as small as it is now — the geometry
is a few hundred bytes per frame, which is not fatal but is not
something the non-debugging default should pay for.

**Debug geometry is produced for unsolvable frames too.** A frame with
detections that failed to solve is the case that most needs explaining,
and `FrameResult` already carries counts for it. `FrameDebug` therefore
always carries the detections and the image size, and carries the
screen rectangle, the cursor point and the reprojection error only when
there was a homography to compute them from. `NO_MARKERS` produces a
`FrameDebug` with an empty marker list rather than `None`, so the
client can distinguish "nothing was seen" from "debug is off".

**A stale overlay is never drawn.** When a frame does not solve, the
quad and cursor point are absent and the client clears them rather than
leaving the previous frame's shapes on screen. Drawing last-known
geometry over a live image would produce a confident, wrong picture —
the exact failure this change exists to eliminate.

**The overlay is not synchronised to the video; it is labelled
instead.** The geometry describes a frame captured one round trip ago,
so during a sweep the drawing trails the image beneath it. The
alternative — retaining recent captures on the phone keyed by the
timestamp it already stamps on each frame, and drawing the overlay over
the matching still — is correct and was rejected: it converts a live
viewfinder into a stuttering one and holds frames in memory on a
device already encoding JPEGs at 20 fps. Instead the client draws the
newest geometry over the live image and shows its age from the
already-echoed `client_ms`, and the on-screen copy tells the operator
to judge alignment while holding still. The reticle, being static, is
unaffected either way.

**Reprojection error is reported as a number, never as a substitute for
the hull flag.** It is nearly free — `solve.py` already computes it —
and it answers "is this fit self-consistent". It does not answer "is
this aim point accurate", and `SolveResult`'s own docstring explains
why: a single marker gives four points and an exact fit, so the error
is ~0 precisely when the aim point is worst. The panel therefore shows
it *next to* the existing extrapolated flag, with the flag keeping
primacy.

**Marker quads are stroked, not filled, and coloured by whether the
layout maps them.** The overlay's entire job is to be compared against
the image underneath it, so nothing may obscure that image. Mapped
tags, ignored tags, the screen rectangle and the cursor point use the
palette already defined in `index.html`'s `:root`
(`--ok`/`--warn`/`--bad`/`--dim`), so the drawing reads the same way as
the numbers beside it. An ignored tag drawn in the warning colour with
its ID visible is the fastest possible answer to "why is marker 5 not
helping" — it is being seen and skipped, not missed.

**The overlay is a `<canvas>` positioned over the `<video>`, redrawn on
telemetry arrival.** Sized to the element's box times
`devicePixelRatio`, with the video's letterboxed content rect computed
from `videoWidth`/`videoHeight` against the element size — the same fit
`object-fit: contain` performs, recomputed because the browser does not
expose it. Redrawing on each telemetry message rather than on a
`requestAnimationFrame` loop bounds the work by the frame rate that
already exists and keeps the canvas idle when nothing is arriving.

**The toggle is a `pick`-style button pair in the existing panel, and
its state is re-sent on connect.** It mirrors the marker-source control
already there (`aria-pressed`, same styling), so the page gains no new
interaction vocabulary. Sending the current state when the socket opens
means the setting survives a reconnect, rather than silently reverting
to off on a link that just dropped — which is when debugging is most
likely to be in progress.

## Risks / Trade-offs

[The overlay trails the live image by one round trip, so a moving
camera shows geometry that does not line up with what is beneath it,
which could be read as a solve error] → Not hidden: the client shows
the geometry's age and states that alignment is judged while stationary.
The reticle, which is the primary answer to "where am I pointing", is
static and unaffected.

[Debug telemetry adds a few hundred bytes per frame at 20 fps on the
same Wi-Fi already carrying JPEGs the other way] → Gated off by
default and toggled per session, so a normal session pays nothing.

[Per-frame canvas drawing on a phone competes with JPEG encoding for
the same main thread] → Bounded: drawing happens once per telemetry
message, over a preview capped at 34vh, for a few dozen stroked
segments. If it does cost measurably, the toggle already exists and the
capture loop's existing skip-rather-than-queue policy absorbs it
without producing a backlog.

[Adding a debug parameter to `process_frame` risks the debug path
diverging from the solving path, so the overlay could confirm geometry
the emitted cursor never used] → The debug values are derived from the
same `SolveResult` and the same `FrameResult.position` the emission
used, inside the same call, after emission. Nothing is recomputed and
no second solve exists to drift.

[The screen rectangle is only as truthful as `screen_size_mm` in the
layout, so a mis-measured panel draws a rectangle that is wrong in a
way the operator may attribute to the solve] → This is a feature of the
drawing, not a defect: a rectangle that is consistently too large or
too small against the real panel *is* the readout for a wrong
`screen_size_mm`, and it is currently invisible. Called out in the
spec's scenarios so the reading is documented.

[A camera whose granted resolution differs from what the server decodes
would misplace every drawn shape] → The image size is sent and shown
next to the granted camera resolution rather than assumed equal, so the
mismatch surfaces as a stated disagreement instead of a silent offset.

## Migration Plan

Additive throughout. No existing requirement changes shape: the
pipeline's default `debug=False` leaves `process_frame`'s signature
compatible and its output identical, telemetry is unchanged for any
session that does not opt in, and a server predating this change simply
ignores an unrecognised `debug` control message the way `_handle_control`
already ignores everything it does not match. Rolling back is deleting
the overlay; nothing depends on it.

## Open Questions

- Should the toggle persist across page loads (`localStorage`) rather
  than only across reconnects? Left to implementation — it is a
  one-line addition either way and does not affect the wire or the
  spec.
