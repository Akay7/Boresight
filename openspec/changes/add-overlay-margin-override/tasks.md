## 1. The overlay itself

- [x] 1.1 Add `extra_margin_px: int = 0` to `qt_backend.run()`, applied
      to `available` via `.adjusted(margin, margin, -margin, -margin)`
      before `area_px` is derived; test that a zero/unset margin
      produces exactly today's `area_px` for a given `availableGeometry`
- [x] 1.2 Test that a nonzero margin shrinks the reported `area_px` by
      that amount on every side, relative to the same
      `availableGeometry`
- [x] 1.3 Add `--extra-margin-px` to `python -m boresight.overlay`
      (alongside `--tag-px`/`--inset-px`) and thread it to
      `qt_backend.run()`; test the CLI parses it and passes it through

## 2. Wiring through the server's launch path

- [x] 2.1 Add `extra_margin_px` to `MarkerSourceController.__init__`
      and `_overlay_command()`, appending `--extra-margin-px` to the
      spawned command only when nonzero (matching how `--display` is
      conditionally added); test the command built for a nonzero value
      and confirm an unset one omits the flag entirely
- [x] 2.2 Add an `overlay_extra_margin_px` parameter to `create_app()`,
      forwarded to `MarkerSourceController`; test it reaches the
      controller
- [x] 2.3 Add `--overlay-extra-margin-px` to `python -m
      boresight.server`'s CLI, wired to `create_app(...,
      overlay_extra_margin_px=...)`

## 3. Runtime control from the phone

- [x] 3.1 Add `MarkerSourceController.set_overlay_extra_margin_px(value)`:
      updates the stored margin, and if on-screen markers are currently
      active, restarts the overlay through `_start_screen_markers()`
      (propagating `MarkerSourceError` the same way `select()` does);
      test both branches (active vs. not) and the error-propagation path
- [x] 3.2 Include `overlay_extra_margin_px` in `MarkerSourceController.state()`,
      so it is visible wherever marker-source state already is; test it
      appears and reflects the last value set
- [x] 3.3 Add `POST /markers/overlay-margin` (body: `{"extra_margin_px":
      int}`, validated non-negative with a sane upper bound) returning
      `controller.state()`, mirroring `POST /markers/source`'s
      `MarkerSourceError` → 409 handling; test success, validation
      rejection, and the 409 path
- [x] 3.4 Add a stepper control (`−`/value/`+`) next to the marker
      source buttons in `index.html`, wired in `capture.js` to read the
      margin from the same state the source buttons already load and to
      `POST` a changed value the same way `selectMarkerSource` does
      (disable during the request, restore after, show the server's
      error on failure); test the page's static assertions the way
      existing marker-source markup is tested

## 4. Manual verification

- [ ] 4.1 On the real multi-monitor setup that surfaced this (the
      external monitor whose overlay log showed no "reserved by desktop
      panels" suffix), start the server with an `--overlay-extra-
      margin-px` value large enough to clear the taskbar, and confirm
      the previously-hidden tag is now fully visible
- [ ] 4.2 From the phone, with on-screen markers active, tap the margin
      stepper and confirm the overlay visibly restarts with the tag
      clearing the taskbar, without the video connection dropping

## 5. Documentation and gate

- [x] 5.1 Document the flag in README, near "On-screen markers" --
      what it is for and the concrete symptom (a monitor where
      `availableGeometry()` under-reports) that motivates it
- [x] 5.2 Document the phone control in the same README section
- [x] 5.3 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format
      --check` and `uv run pre-commit run --all-files` clean
- [x] 5.4 Run `openspec validate add-overlay-margin-override --strict`
