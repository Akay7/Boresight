## Context

`solve.py` fits a homography from screen-plane marker corners to image
points, inverts it, and pushes the image centre through. Its correctness
has only ever been checked with nearly the whole marker layout visible
(the pure-geometry, single-image, degraded-image, and video fixtures all
run 7-8 of 8 markers). Partial visibility is not an edge case for this
project — it is the normal condition close to the screen, off-axis, or
mid-swing, and README's edge-midpoint markers exist specifically because
of it.

Measurement (see proposal.md for the tables) established three things
that shape this design:

1. Accuracy tracks the geometry of the correspondences relative to the
   aim point, not the number of markers. Two markers on opposite sides
   of the panel beat two markers sharing an edge by ~20x.
2. Reprojection error cannot detect the failure. With a single marker
   the fit is exact (0.000px) and the aim point is 162mm wrong. It is
   not merely uninformative, it is anti-correlated.
3. Below ~1.8m at 45° FOV, aiming at screen centre, no bezel markers are
   in frame at all, so no amount of solver work helps.

## Goals / Non-Goals

**Goals:**
- Give callers a signal that actually separates trustworthy solves from
  extrapolated guesses, computed from the correspondence geometry.
- Cover partial visibility explicitly, as its own test deck, including
  the ill-conditioned case rather than only the flattering one.
- Keep the full-visibility deck as the statement of best-case accuracy,
  with tolerances tight enough to catch regressions there.
- Exercise partial visibility through real rendered frames where markers
  actually leave the camera's view, not only by subsetting detections.
- Record the working-distance floor so it is a known constraint rather
  than a surprise during hardware bring-up.

**Non-Goals:**
- Fixing sparse-marker accuracy. The right fix is `solvePnP` against a
  marker of known physical size using calibrated intrinsics, which
  turns a 4-point extrapolation into a metric pose estimate. Camera
  intrinsic calibration is an unbuilt README milestone; attempting this
  now would mean inventing a calibration to test against.
- Deciding policy for low-confidence solves (reject? hold last good
  pose? decay?). README's Dropout note says hold-and-decay, but the
  consumer that would implement it does not exist. Report, don't
  enforce.
- Temporal fallback across frames (using the previous frame's pose when
  this frame is poorly conditioned) — that is filtering, a separate
  unbuilt milestone.
- Changing the marker layout or adding README's suggested "second inner
  ring" for close play. That is a physical-design change and should be
  driven by real hardware, not by a synthetic fixture.

## Decisions

**Conditioning signal: convex-hull containment of the aim point, not a
condition number.** The failure mode is specifically extrapolation
beyond the fitted points, so measure that directly: build the convex
hull of the screen-plane correspondence points, and report whether the
aim point is inside it, its signed distance to the hull boundary in mm,
and the hull's extent. `cv2.pointPolygonTest` gives containment and
signed distance in one call.
Alternatives considered: the homography's condition number (real, but
opaque to interpret and does not directly express "the answer is
outside the region I have evidence for"); reprojection error (measured
above to be anti-correlated with accuracy here); marker count (shown to
be the wrong variable).

**Report as data on `SolveResult`, additively.** New fields alongside
the existing `aim_point_mm` / `homography` / `reprojection_errors_px`.
No change to `solve()`'s signature and no new exception, so existing
callers and the three existing test files are unaffected. The already-
specified `InsufficientCorrespondencesError` for fewer than four
correspondences stays exactly as is — that is a "cannot solve" case,
distinct from "solved, but do not trust it much".

**Two decks, split by what they are evidence for, not by fixture.**
The full-visibility deck asserts the system's best-case accuracy with
tight tolerances. The partial-visibility deck asserts three separate
things: a well-conditioned subset stays accurate, an ill-conditioned
subset is *flagged* (not required to be accurate — it cannot be), and
the zero/insufficient case raises rather than returning nonsense. This
keeps the ill-conditioned case honest: the assertion is about the
warning, not about an accuracy the geometry cannot deliver.

**Partial visibility produced two ways, deliberately.** Subsetting
detections from existing full-visibility frames gives controlled,
deterministic coverage of specific geometries (opposite-edge vs
same-edge vs single marker) that would be fiddly to hit exactly with a
camera path. A separately rendered close-range sequence gives the real
thing: markers outside the frustum, larger and more perspective-
distorted markers, and detection failure as part of the loop. Neither
alone covers the case — subsetting cannot prove the detector behaves at
close range, and a rendered path cannot cheaply hit chosen degenerate
configurations.

**Close-range fixture reuses `blender_video_scene.py` unchanged.** Only
the camera keyframes and output directory differ, so the scene, ground
truth derivation, and degradation model stay shared. A second thin
generator module rather than a second scene script.

## Risks / Trade-offs

[A hull-containment flag invites callers to treat it as a boolean
"valid/invalid" when accuracy actually degrades continuously] → Report
the signed distance and hull extent alongside the boolean so a consumer
can set its own threshold; document that the boolean is the coarse
summary of a continuous quantity.

[The ill-conditioned assertions could ossify current bad behaviour --
if a future `solvePnP` path makes single-marker solves accurate, tests
asserting "this is flagged" would still pass but would be measuring the
wrong thing] → Assert the flag, and additionally assert the error is
*large* only as a documented observation with a generous bound, so the
tests fail loudly and visibly if sparse accuracy ever improves
dramatically, prompting a revisit rather than silently passing.

[Adding fields to `SolveResult` grows the API before there is a consumer
to validate the shape against] → Kept to plain data with no behaviour,
derived entirely from inputs `solve()` already has; if the shape is
wrong it costs a rename, not a redesign.

[The close-range fixture adds more checked-in binary] → Reuse the
existing JPEG encoding and keep the sequence short; it only has to
demonstrate marker loss, not a long trajectory. Budget it against the
2.5MB the video fixture already costs.

## Migration Plan

Additive throughout. `SolveResult` gains fields; nothing is removed or
renamed, so the existing suite should keep passing untouched at every
step. Order: conditioning fields and their unit-level tests first
(pure geometry, no fixture needed), then regroup the existing e2e tests
into the full-visibility deck, then the subsetting partial deck against
the existing fixture, then the close-range rendered fixture and its
tests last, since it is the only step that needs Blender.

## Open Questions

- Exact hull-distance threshold, if any, that should back the boolean —
  pick from measurement against both decks rather than guessing, and if
  no clean separation exists, report the continuous value and leave the
  boolean as strict containment.
- Whether the close-range sequence should aim at screen centre (where
  markers vanish entirely, per the distance sweep) or off-centre toward
  a bezel edge (where a few markers stay in frame). Likely both, as
  separate short sequences, since they exercise different outcomes:
  raising versus solving-but-flagged. Decide during implementation from
  what the render actually yields.
