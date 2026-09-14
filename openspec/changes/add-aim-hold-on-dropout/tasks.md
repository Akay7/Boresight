## 1. The holding wrapper

- [x] 1.1 Add a `HoldingPipeline` wrapping an `AimPipeline`, a
      `CursorBackend`, and a fixed hold window (monotonic clock,
      overridable for tests): on a `SOLVED` outcome, record the position
      and time and return the wrapped pipeline's result unchanged; unit
      test that a solved frame passes through untouched
- [x] 1.2 Test that a non-solved frame within the hold window re-sends
      the last solved position to the backend, and the `FrameResult`
      returned is exactly the wrapped pipeline's real (non-solved) one
      -- no position implied
- [x] 1.3 Test that a non-solved frame beyond the hold window does not
      call the backend at all
- [x] 1.4 Test that a new solve arriving mid-hold replaces the held
      position and time immediately -- the next non-solved frame holds
      the new position, not the previous one
- [x] 1.5 Test that holding is a no-op through a real `OneEuroFilter`:
      wrap a `SmoothingCursorBackend` around a `FakeCursorBackend`,
      drive a solve then a held re-send after an artificial gap, and
      assert the backend's recorded position is unchanged by the resend

## 2. Wiring

- [x] 2.1 Have `MarkerSourceController` build a `HoldingPipeline`
      wrapping the `AimPipeline` it already builds (with the same
      shared, smoothing-wrapped cursor backend) as `self._pipeline`, at
      construction and on every marker-source switch
- [x] 2.2 Update the existing tests that reach `controller.pipeline._map`
      / `controller.pipeline._backend` for the new wrapper shape (inner
      pipeline via `.pipeline._pipeline`, backend unchanged), and
      confirm `uv run pytest` is clean

## 3. Integration tests

- [x] 3.1 Extend a pipeline-level integration test to drive one solved
      frame followed by several non-solved frames within the hold
      window, and assert the backend received additional calls at the
      same position for each
- [x] 3.2 Extend a stream e2e test to confirm a non-solved frame's wire
      report is unaffected by holding (no position, real outcome)
      even though the cursor backend was privately re-sent one

## 4. Manual verification

- [ ] 4.1 On a real device, hold aim steady through a brief natural
      marker dropout (partial occlusion, quick motion blur) and confirm
      the OS cursor no longer visibly blinks or disappears
- [ ] 4.2 On a real device, pull the trigger during a brief dropout and
      confirm the click lands at the position last visibly shown, not a
      stale or unexpected one
- [ ] 4.3 On a real device, let aim go away for longer than the hold
      window (e.g. walk out of frame) and confirm the cursor is allowed
      to go idle rather than staying frozen on the old position forever
- [ ] 4.4 On a real device, switch marker source immediately after a
      dropout on the first source, and confirm nothing stale from the
      old source is held into the new one

## 5. Documentation and gate

- [x] 5.1 Document the hold window and its rationale in README, near
      "Aim smoothing"
- [x] 5.2 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format
      --check` and `uv run pre-commit run --all-files` clean
- [x] 5.3 Run `openspec validate add-aim-hold-on-dropout --strict`
