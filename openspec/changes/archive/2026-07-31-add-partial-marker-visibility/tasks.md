## 1. Conditioning signal in solve.py

- [x] 1.1 Extend `SolveResult` with conditioning fields: aim point
      inside the correspondence convex hull (bool), signed distance from
      the aim point to the hull in mm, and the hull/correspondence
      extent. Additive only -- existing fields, `solve()`'s signature,
      and the existing exception behaviour stay unchanged
- [x] 1.2 Compute them from the screen-plane correspondence points via
      `cv2.convexHull` + `cv2.pointPolygonTest`, using the same points
      already passed to `findHomography` (no new inputs)
- [x] 1.3 Unit tests, pure geometry, no fixture: aim point inside a
      well-spread point set reports inside with interior signed
      distance; aim point outside a clustered set reports outside; the
      returned aim point is byte-identical to what the solver produced
      before the fields existed
- [x] 1.4 Confirm the three existing solver test files still pass
      untouched (the change must be purely additive)

## 2. Deck A -- full visibility

- [x] 2.1 Group the existing full-visibility end-to-end coverage
      (`test_solve_synthetic_image.py`, `test_solve_e2e_realistic.py`,
      `test_solve_video_e2e.py`) as the full-visibility deck, with a
      clear marker in each module docstring saying which deck it is and
      what it is evidence for
- [x] 2.2 Assert in this deck that solves are reported as
      well-conditioned (aim point inside the hull), so the deck states
      the good case explicitly rather than only implying it
- [x] 2.3 Keep tolerances tight here -- this deck is the statement of
      best-case accuracy (currently ~1.5mm on a 1220mm panel); do not
      loosen them to accommodate the partial deck

## 3. Deck B -- partial visibility, by subsetting

- [x] 3.1 Add a partial-visibility test module that reuses the existing
      video fixture but feeds `solve()` only chosen subsets of the
      detected markers, so specific geometries can be hit exactly
- [x] 3.2 Well-conditioned subset: markers on opposite sides of the
      panel spanning the aim point. Assert accuracy comparable to full
      visibility, and that conditioning reports inside-hull. Measure
      first, then set the tolerance
- [x] 3.3 Ill-conditioned subset: markers clustered on a single edge.
      Assert the conditioning flag reports extrapolation. Assert the
      error is large only as a documented observation with a generous
      bound, so a future accuracy improvement fails loudly and prompts a
      revisit instead of silently passing
- [x] 3.4 Single marker: assert an answer is still returned (not
      raised), and that it is flagged as extrapolated
- [x] 3.5 Fewer than four correspondences: assert
      `InsufficientCorrespondencesError`

## 4. Deck B -- partial visibility, from real close-range renders

- [x] 4.1 Add a close-range fixture generator reusing
      `blender_video_scene.py` unchanged -- only camera keyframes and
      output paths differ. Reuse the existing degradation model and JPEG
      encoding
- [x] 4.2 Choose the camera path from what the render actually yields
      (design.md Open Questions): a sequence aiming at screen centre
      close in, where markers leave the frame entirely, and/or one
      aiming toward a bezel edge where a few markers stay visible.
      Verify by rendering before committing the fixture
- [x] 4.3 Generate and check in the fixture; confirm it regenerates
      bit-identically and stays within the size budget (compare against
      the 2.5MB the video fixture costs)
- [x] 4.4 Tests: frames with a few markers visible still solve and are
      flagged appropriately; frames with no markers raise rather than
      returning nonsense
- [x] 4.5 Confirm the new fixture files are LFS-tracked by the existing
      `.gitattributes` rules (no new LFS configuration should be needed)

## 5. Verification

- [x] 5.1 Run `uv run pytest -v`; both decks pass alongside the existing
      suite, zero warnings
- [x] 5.2 Mutation-check the new assertions the way the video deck was
      checked: confirm the conditioning flag actually fails when
      inverted, so the new tests are not vacuous
- [x] 5.3 Run `uv run ruff check .`, `uv run ruff format --check .`, and
      `uv run pre-commit run --all-files`

## 6. Documentation

- [x] 6.1 README: record the working-distance floor (below ~1.8m at 45°
      FOV aiming at screen centre, no bezel markers are in frame) next
      to the existing marker-layout and sizing guidance
- [x] 6.2 README: record that accuracy is governed by correspondence
      geometry relative to the aim point rather than marker count, and
      qualify the existing "One marker is sufficient" claim with the
      measured extrapolation error
- [x] 6.3 README: document the conditioning signal and that reprojection
      error must not be used as a validity check, with the measured
      reason (exact fit, near-zero reprojection error, badly wrong aim
      point)
- [x] 6.4 Note the `solvePnP`-with-intrinsics path as the real fix for
      sparse-marker accuracy, blocked on the camera-calibration
      milestone, so the limitation is recorded rather than rediscovered

## 7. Implementation notes

- **The headline result.** Sweeping every marker subset across every
  frame of the video fixture (4844 combinations): solves whose aim point
  lies *inside* the correspondence hull peaked at **18.3mm** error
  (median 1.5mm); solves outside it reached **2037mm** (median 8.7mm).
  The flag is therefore a usable filter with a real bound, which is what
  justified building it.

- **Being flagged does not mean being wrong**, which the close-range
  fixture made obvious and which the tests were written to respect. Its
  one- and two-marker frames are all flagged as extrapolated yet land
  within 1.3-5.9mm, because a marker seen from 1.3m spans far more
  pixels than one seen from 3m, so its corners localise better and the
  extrapolation is shorter in screen mm. Deck B therefore asserts the
  *flag* and the raise-vs-return behaviour on ill-conditioned frames,
  never that they are inaccurate.

- **The flag is about geometry, not marker count** — worth stating
  because it is the counterintuitive part. Four corner markers (half the
  layout) are inside-hull and accurate to 1.95mm. Two markers on
  opposite sides span the panel horizontally but their hull is a thin
  band, so an aim point above or below it is still extrapolated in one
  axis, and is flagged. Three close-range markers spanning two bezel
  edges enclose the aim point and are accurate.

- **`solve.py`'s change is purely additive**: three new dataclass fields
  with defaults, computed via `cv2.convexHull` + `cv2.pointPolygonTest`
  from points `solve()` already had. Signature, exception behaviour and
  the returned aim point are unchanged, and the pre-existing tests
  passed untouched at every step.

- **Mutation-checked, as the video deck was.** Inverting the
  inside/outside flag failed 10 tests across all four affected modules;
  making it constantly `True` -- the way a broken signal would most
  plausibly fail silently -- failed 8. The new assertions are not
  vacuous.

- **`render_sequence()` was extracted** from the video fixture generator
  so the close-range generator reuses the scene, ground-truth
  derivation, degradation and encoding, differing only in camera path.
  `blender_video_scene.py` is untouched. Verified behaviour-neutral by
  confirming the video fixture regenerates bit-identically after the
  extraction.

- **`test_the_fixture_still_shows_what_it_was_built_to_show`** guards
  the close-range deck against silent drift: each pose records the
  marker count it was chosen for, so if the scene or detector changes
  such that the poses no longer produce 0/1/2/3 markers, the deck fails
  loudly instead of continuing to pass while testing something else.

- **`test_single_marker_accuracy_is_still_poor` is an observation lock,
  not a goal.** It asserts sparse accuracy is *still bad* so that a
  future `solvePnP` improvement fails the test and prompts revisiting
  the README caveats, rather than landing silently.

- **Fixture cost:** close-range adds 912KB (7 JPEG frames + scene.blend)
  on top of the video fixture's 2.5MB. Both regenerate bit-identically;
  both are LFS-tracked by the existing `*.jpg` / `*.blend` rules with no
  new configuration.

- **Still out of scope**, per design.md: fixing sparse accuracy
  (`solvePnP` needs camera intrinsics, an unbuilt milestone), policy for
  low-confidence solves, temporal fallback across frames, and any
  marker-layout change such as README's suggested inner ring.
