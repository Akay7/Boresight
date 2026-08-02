## 1. Layout derivation

- [x] 1.1 Add `src/boresight/overlay/layout.py` with
      `overlay_layout(screen_px, tag_px, inset_px, scale=1.0) ->
      MarkerMap`: eight tags (4 corners + 4 edge midpoints) inset from
      the display edges, in the same coordinate convention a printed
      layout uses
- [x] 1.2 Convert pixels with one uniform scale for both axes, so the
      aspect ratio is preserved and the scale cancels under
      normalization
- [x] 1.3 Derive the default tag size from README's sizing table (~3px
      per bit cell over a 6-cell grid at playing distance) rather than
      picking a number, and make it configurable
- [x] 1.4 Add `tests/test_overlay_layout.py`: eight IDs matching the
      printed layout's numbering, every tag inside the panel, corners
      and midpoints where they belong, and no overlap between tags
- [x] 1.5 Test that two different uniform scales produce the same
      normalized aim point for one camera view — the property the
      design relies on
- [x] 1.6 Test that a derived layout is accepted by `AimPipeline`
      unchanged, with no special handling versus a loaded one

## 2. Rendering

- [x] 2.1 Add `src/boresight/overlay/render.py` drawing each tag from
      the same dictionary `detect.py` decodes against, reusing
      `markers.marker_grid` so the overlay and the printed sheet cannot
      diverge
- [x] 2.2 Draw each tag on an opaque quiet-zone patch extending beyond
      it on all sides, rather than compositing onto the pixels beneath
- [x] 2.3 Add a test rendering the overlay image offscreen, running it
      through the real `detect_markers`, and asserting all eight decode
      at their expected positions — the overlay's own output must
      survive the detector

## 3. Platform backends

- [x] 3.1 Add an `OverlayBackend` interface: start, stop, and a
      capability probe reporting whether this environment can host an
      always-on-top, input-transparent surface
- [x] 3.2 Add the Qt backend: `FramelessWindowHint |
      WindowStaysOnTopHint | WindowTransparentForInput`, plus
      `WA_TranslucentBackground`, covering X11 and Windows in one path
- [x] 3.3 Add the Wayland probe: detect the session, and detect whether
      a layer-shell surface can be obtained
- [x] 3.4 Refuse to start where an always-on-top surface is
      unavailable, with a message identifying the environment and
      naming printed markers as the alternative — never a window that
      renders while eating input
- [x] 3.5 Report a missing overlay dependency group as "install the
      overlay extra", not as an `ImportError` traceback
- [x] 3.6 Select the target display, defaulting to the primary one

## 4. Packaging and wiring

- [x] 4.1 Add `[project.optional-dependencies] overlay = ["PySide6-..."]`
      to `pyproject.toml`, leaving core dependencies untouched
- [x] 4.2 Add a `python -m boresight.overlay` entry point taking display,
      tag size and inset
- [x] 4.3 Add configuration selecting the marker layout source — a file
      as today, or the on-screen layout — and wire it into the server's
      existing `marker_map_factory` seam
- [x] 4.4 Verify a default install still has no graphical toolkit and
      that the full suite passes without the overlay group

## 5. Tests

- [x] 5.1 Test the backend selection and capability probe against
      simulated environments (X11, Wayland with layer-shell, Wayland
      without, Windows), asserting the refusal path is taken exactly
      when the environment cannot host the overlay
- [x] 5.2 Test that the refusal message names printed markers, and that
      a missing dependency names the extra to install
- [x] 5.3 Test that overlay tests skip cleanly, rather than fail, on a
      machine with no display and no overlay group installed
- [x] 5.4 Test the layout-source configuration: a file layout behaves
      exactly as before, an on-screen layout reaches the pipeline

## 6. Manual verification

These need a real desktop session and cannot be asserted in CI.

- [ ] 6.1 On X11: start the overlay, confirm the tags draw above a
      running application and that clicking a tag reaches the
      application beneath
- [ ] 6.2 On X11: run the full loop and confirm an injected click at an
      aim point over a tag lands on the application, not the overlay —
      the failure the input-transparency requirement exists to prevent
- [ ] 6.3 Confirm keyboard focus and typing are unaffected while the
      overlay is running
- [ ] 6.4 Point the phone at the screen and confirm the on-screen tags
      decode, at playing distance and at close range
- [ ] 6.5 Confirm the fullscreen-exclusive limitation in practice, and
      that borderless-windowed works, so README documents behaviour
      rather than expectation
- [ ] 6.6 Windows: verify the same overlay behaviour — untested by
      anyone so far, so treat the Qt-to-`WS_EX_TRANSPARENT` mapping as
      a documentation claim until someone runs it

## 7. Documentation and gate

- [x] 7.1 Document the overlay in README: what it removes (printing,
      measuring, the exposure problem), how to start it, and the
      optional install
- [x] 7.2 Document the fullscreen-exclusive limitation alongside the
      feature, in the same breath as README's existing note about
      synthetic input and fullscreen-exclusive titles
- [x] 7.3 Document platform support honestly: X11 and Windows via Qt,
      Wayland only where layer-shell exists, not GNOME, no macOS
- [x] 7.4 Move "On-screen markers" out of Future work, and note the
      calibration and minimum-working-distance milestones it relieves
- [x] 7.5 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format
      --check` and `uv run pre-commit run --all-files` clean
- [x] 7.6 Run `openspec validate add-screen-marker-overlay --strict`
