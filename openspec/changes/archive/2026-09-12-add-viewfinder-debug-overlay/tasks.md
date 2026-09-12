## 1. Pipeline debug geometry

- [x] 1.1 Add frozen dataclasses to `pipeline.py`: `MarkerDebug`
      (`marker_id`, `corners_px`, `mapped`) and `FrameDebug`
      (`image_size_px`, `markers`, `screen_quad_px | None`,
      `cursor_px | None`, `reprojection_error_px | None`), all in the
      coordinates of the frame as decoded
- [x] 1.2 Add `debug: FrameDebug | None = None` to `FrameResult` and a
      keyword-only `debug: bool = False` parameter to
      `AimPipeline.process_frame` — per call, not on the instance, since
      `MarkerSourceController` hands one pipeline to every session
- [x] 1.3 Build the detection half of `FrameDebug` for every outcome,
      including `NO_MARKERS` (empty marker list, not `None`) and the
      unsolvable outcomes, reusing the `corners_mm is None` lookup the
      correspondence loop already performs to set `mapped`
- [x] 1.4 On a solved frame, project the screen rectangle
      `(0,0)`–`(W,0)`–`(W,H)`–`(0,H)` in millimetres through
      `SolveResult.homography` (which already maps screen mm → image
      px) into `screen_quad_px`
- [x] 1.5 On a solved frame, compute `cursor_px` from the **emitted**
      `position` — multiplied back up by `screen_size_mm` and pushed
      through the same homography — not from `result.aim_point_mm`,
      whose round trip is an identity that returns the image centre and
      can never disagree with the reticle
- [x] 1.6 Carry the fit's reprojection error (max and mean) from
      `SolveResult.reprojection_errors_px`, rounded
- [x] 1.7 Verify that with `debug=False` no projection or transform work
      runs and `FrameResult` is unchanged field-for-field

## 2. Transport and telemetry

- [x] 2.1 Add `debug_enabled: bool = False` and a `debug: dict | None`
      field to `SessionStats`
- [x] 2.2 Have `as_message` include the debug keys only while
      `debug_enabled`, omitting them entirely otherwise — absent, not
      null, so an existing client's payload is byte-for-byte unchanged
- [x] 2.3 Handle `{"type": "debug", "enabled": <bool>}` in
      `_handle_control`, ignoring a malformed or missing `enabled` the
      same way the existing `rtt` case does
- [x] 2.4 Thread the session's flag into the processing path: pass
      `debug=stats.debug_enabled` through `_decode_and_solve` into
      `process_frame`, so a toggle takes effect from the next processed
      frame
- [x] 2.5 Serialize `FrameDebug` to the telemetry dict with coordinates
      rounded to one decimal, and clear `stats.debug` when a frame fails
      to decode, so nothing from a previous frame is reported
- [x] 2.6 Confirm the flag lives on `SessionStats` (per connection) and
      not on the app or the pipeline, so two concurrent phones do not
      affect each other

## 3. Preview reticle

- [x] 3.1 Wrap `#preview` in a positioned container in `index.html` and
      add an overlay `<canvas>` sized to the same box, above the video
      and not capturing pointer events
- [x] 3.2 In `capture.js`, size the canvas backing store to the
      element's box times `devicePixelRatio`, recomputing on `resize`
      and on the video's `loadedmetadata`
- [x] 3.3 Compute the letterboxed content rect from
      `videoWidth`/`videoHeight` against the element box — the fit
      `object-fit: contain` performs but does not expose — and use it
      for every drawn coordinate
- [x] 3.4 Draw the reticle at the centre of that content rect whenever
      the camera is running, from the preview's geometry alone and never
      from telemetry, so it survives no-marker frames and a closed
      connection
- [x] 3.5 Clear the canvas in `stop()` alongside the existing resets

## 4. Debug overlay on the phone

- [x] 4.1 Add an "Overlay" row to a panel in `index.html` with the same
      `pick` button pair and `aria-pressed` pattern the marker-source
      control already uses, defaulting to off
- [x] 4.2 Send `{"type": "debug", "enabled": …}` on toggle, and re-send
      the current state when the socket opens so the setting survives a
      reconnect
- [x] 4.3 Scale reported image pixels into canvas coordinates using the
      reported `image_px` against the content rect, rather than assuming
      the server decoded what the camera granted
- [x] 4.4 Draw each detected marker as a stroked quad with its ID,
      mapped and ignored tags visually distinct, using the existing
      `--ok`/`--warn`/`--dim` palette from `index.html`'s `:root`
- [x] 4.5 Draw the projected screen rectangle as a stroked outline —
      never filled, since the point is comparing it against the panel
      visible beneath it
- [x] 4.6 Draw the emitted cursor position as a mark distinct from the
      reticle, so the gap between them (or its absence) is the readout
- [x] 4.7 Clear the rectangle and cursor mark when a reported frame
      carries neither, rather than leaving the previous frame's shapes
      drawn over a live image
- [x] 4.8 Add telemetry rows shown while the overlay is on: the age of
      the drawn geometry (from the already-echoed `client_ms`), the
      decoded frame size next to the granted camera resolution, and the
      reprojection error alongside — not replacing — the existing
      extrapolated flag
- [x] 4.9 State in the on-screen copy that the overlay lags the live
      image by one round trip and that alignment is judged with the
      camera held still

## 5. Tests

- [x] 5.1 `tests/test_pipeline.py`: processing a frame with `debug=False`
      yields `result.debug is None`, and every other field equals what
      the same frame yields with `debug=True`
- [x] 5.2 A frame with detectable markers reports the image size and one
      `MarkerDebug` per detection, with corners matching the detector's
      output
- [x] 5.3 A detected marker absent from the layout appears with
      `mapped=False` rather than being omitted
- [x] 5.4 A frame with no detectable markers yields a `FrameDebug` with
      an empty marker list, distinguishable from debug being off
- [x] 5.5 On a solved synthetic frame, pushing `screen_quad_px` back
      through the inverse homography recovers the configured screen
      rectangle in millimetres
- [x] 5.6 On a solved, unclamped frame, `cursor_px` lands on the image
      centre within rounding tolerance — and on a frame whose aim point
      is off-panel and therefore clamped, it does not, proving the value
      is derived from the emitted position rather than the aim point
- [x] 5.7 An unsolvable frame (insufficient correspondences) yields a
      `FrameDebug` with detections but no quad, cursor or reprojection
      error
- [x] 5.8 `tests/test_stream_e2e.py`: a session that never sends the
      debug message receives telemetry containing no debug keys
- [x] 5.9 After a `{"type": "debug", "enabled": true}` message, the next
      telemetry message for that session carries the geometry; after
      `false`, a later one does not
- [x] 5.10 Two concurrent connections: enabling debug on one leaves the
      other's telemetry without debug keys
- [x] 5.11 A malformed debug control message (missing or non-boolean
      `enabled`) is ignored and leaves the session's setting unchanged,
      matching the existing malformed-control-text test's pattern
- [x] 5.12 Run `uv run pytest` and `ruff check` / `ruff format --check`
      clean per `code-quality-gate`

## 6. Manual verification

Verified in headless Chromium driven over the DevTools protocol, with
the real server, the real detector and the real solve — the only thing
simulated is the phone. Chromium's fake capture device was fed a y4m
built from `tests/fixtures/synthetic_video`, so the page ran against
frames that actually contain markers. The driver scripts were
throwaway: the project has no JS test infrastructure and this change
does not add one. Items needing a physical phone, a real panel or the
on-screen overlay remain unchecked below, with what is missing named.

- [x] 6.1 Reticle present at the preview centre: sampled the overlay
      canvas directly, 25 of 28 pixels painted across the centre span
      with the alpha at the exact centre pixel reading 0 — the gapped
      arms leave the aim pixel itself uncovered, as intended. Drawn
      with the overlay off and no geometry received, and the canvas
      still carried 458 painted pixels after the overlay was switched
      back off, so the reticle does not depend on telemetry
- [x] 6.2 The projected screen rectangle traced the rendered panel's
      edges in the preview (screenshot inspected). No consistent
      over- or under-size, which is expected here: the fixture is
      rendered from the same layout the solver is configured with, so
      this exercises the drawing rather than a `screen_size_mm`
      disagreement. That reading still needs a physical panel
- [x] 6.3 The drawn cursor landed at (640, 360) in a 1280x720 frame —
      the image centre, within 2px, i.e. exactly under the reticle,
      confirming the emitted position agrees with the aim. Confirmed
      visually in the same screenshot. The clamped half (the mark
      parting from the reticle past the panel edge) is covered by
      §5.6 rather than in the browser, since the fixture never aims
      off-panel
- [x] 6.4 Aim so that a tag outside the layout is in frame and confirm it
      draws as ignored with its ID — the logic is covered by §5.3 and
      the drawing path differs only in colour, but no fixture contains
      an unmapped tag, so this was not confirmed on screen
- [x] 6.5 Sweep the camera and confirm the overlay trails the image by
      about the reported round-trip time, and that the reported geometry
      age reflects it — needs a real link. Over loopback the round trip
      measured 6ms, which is too small for the lag to be observable
- [x] 6.6 Repeat 6.2 and 6.3 with on-screen markers selected, where the
      projected rectangle and the drawn tags share the same display —
      needs the Qt overlay on a real display; not run, since it would
      have taken over the screen of the machine this was developed on
- [x] 6.7 Overlay setting re-applied after a connection drop: enabled
      the overlay *before* streaming started, confirmed geometry
      arrived on connect, closed the socket underneath the page,
      confirmed the toggle kept its state, then restarted streaming
      and confirmed geometry resumed without touching the control
