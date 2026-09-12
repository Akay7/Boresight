## 1. Overlay reports its geometry

- [x] 1.1 Have `python -m boresight.overlay` write one JSON line to
      stdout on start — display size, tag size, inset — flushed
      immediately, and keep the human-readable banner separate so the
      two can change independently
- [x] 1.2 Add `--report-only` (start, report the geometry it would use,
      exit) so the handshake can be exercised without mapping a window
- [x] 1.3 Test that the reported geometry matches what `render_overlay`
      actually draws for that display size

## 2. The controller

- [x] 2.1 Add `src/boresight/marker_source.py` with a
      `MarkerSourceController` holding the active source, the current
      `AimPipeline`, the overlay process handle, and the last failure
- [x] 2.2 Build a *new* `AimPipeline` on switch and swap the reference,
      leaving `AimPipeline` itself stateless and immutable
- [x] 2.3 Start the overlay as a child process using a fixed command,
      with the display index validated as an integer and no request
      content reaching the argument list
- [x] 2.4 Read the geometry line with a timeout; on timeout kill the
      child and fail the selection with that reason
- [x] 2.5 Build the solver's layout by calling `overlay_layout` with
      exactly the reported numbers, so the drawn and solved layouts stay
      identical
- [x] 2.6 On failure, keep printed markers active and store the child's
      own explanation — never report on-screen markers as active
      because a selection was requested
- [x] 2.7 Stop the overlay when printed markers are selected, when a new
      overlay replaces it, and on shutdown; selecting the already-active
      source is a no-op
- [x] 2.8 Report liveness by polling the child when the state is read,
      so an overlay that died is not still claimed as active

## 3. Server wiring

- [x] 3.1 Build the controller at startup from the existing `--markers`
      default, and terminate the overlay in lifespan shutdown
- [x] 3.2 Change `run_frame_session` to read the current pipeline per
      frame rather than capturing it when the socket opens, so a switch
      reaches a phone that is already streaming
- [x] 3.3 Add `GET /markers/source` returning the active source, whether
      the overlay is running, its geometry when it is, and the last
      failure
- [x] 3.4 Add `POST /markers/source` selecting a source and returning
      the resulting state, reporting a failed selection as a failure
      rather than a success
- [x] 3.5 Confirm both endpoints are covered by the existing token
      middleware

## 4. Phone client

- [x] 4.1 Add a marker source control to `index.html` showing which
      source is active
- [x] 4.2 Fetch the current state on load and after every selection,
      carrying the token like every other request from the page
- [x] 4.3 Display a failed selection's explanation, and keep showing the
      source that is actually active
- [x] 4.4 Make the control usable before streaming starts, since the
      source is something you would want to set first

## 5. Tests

- [x] 5.1 Test the controller against a stub child that reports geometry
      on stdout: selection starts it, the layout comes from the reported
      numbers, and the state reflects it
- [x] 5.2 Test the failure paths with stub children that exit non-zero,
      print nothing, and hang — asserting printed markers stay active,
      the explanation is kept, and the hang is bounded by the timeout
- [x] 5.3 Test that switching mid-stream changes the layout used by the
      next frame without closing the connection
- [x] 5.4 Test that the overlay is terminated on server shutdown, and
      that selecting the active source twice starts only one process
- [x] 5.5 Test that a died-on-its-own overlay stops being reported as
      active
- [x] 5.6 Test both endpoints reject an unauthenticated request and
      start no process
- [x] 5.7 Test that no request content reaches the child's argument list

## 6. Manual verification

- [x] 6.1 From the phone, switch to on-screen markers and confirm tags
      appear on the display; switch back and confirm they vanish
- [x] 6.2 Switch while streaming and confirm the aim point stays correct
      across the change, with no reconnect
- [x] 6.3 Kill the overlay from a terminal and confirm the phone stops
      showing on-screen markers as active
- [x] 6.4 Stop the server while the overlay is running and confirm no
      overlay is left on screen — the failure this is most meant to
      prevent

## 7. Documentation and gate

- [x] 7.1 Update README's on-screen markers section: the phone control
      replaces the two-terminal procedure, and `--markers screen:WxH` is
      no longer needed to match a resolution by hand
- [x] 7.2 Note that starting the overlay needs the server inside the
      desktop session, not headless
- [x] 7.3 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format
      --check` and `uv run pre-commit run --all-files` clean
- [x] 7.4 Run `openspec validate add-marker-source-control --strict`
