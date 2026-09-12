## Why

The on-screen overlay exists, but using it takes two terminals and a
restart: start `python -m boresight.overlay` on the PC, then restart the
server with `--markers screen:1920x1080` so the solver agrees. Get the
resolution wrong in either place and nothing reports it — the tags are
simply solved against the wrong positions.

That is the wrong shape for the thing it controls. You are standing at
the television holding the phone, not sitting at the PC. Switching
between printed and on-screen markers is exactly the kind of thing you
want to try both ways in the first ten minutes, and right now each
attempt costs a walk back to the keyboard.

There is also a safety reason to put the overlay under the server's
control rather than leaving it a detached process. The overlay window
is input-transparent, takes no focus and has no title bar — by design,
since it must not intercept the shots the gun fires. The only way to
dismiss it is Ctrl-C in the terminal that started it. A stray overlay
whose terminal has been closed is genuinely hard to get rid of. A
parent process that always cleans up its child removes that failure.

## What Changes

- Add a marker source control to the phone client: printed or
  on-screen, with the current state and any failure shown on the page.
- Add HTTP endpoints to read and set the marker source.
- Selecting on-screen markers **starts the overlay process**;
  selecting printed markers **stops it**. The server owns the child
  process for its whole lifetime and terminates it on shutdown, so an
  overlay cannot outlive the thing that started it.
- Switch the layout the solver uses at runtime, taking effect on the
  next frame, without dropping the phone's connection or restarting
  anything.
- Have the overlay report the geometry it actually used — display size,
  tag size, inset — and build the solver's layout from those exact
  numbers, so the two cannot be configured into disagreement. This
  removes the `--markers screen:WxH` guesswork entirely.
- Surface overlay failures as failures. The overlay already refuses to
  start on an unsupported compositor or without its optional
  dependencies; that message must reach the phone rather than leaving
  the control showing "on" while nothing is on screen.
- Keep `--markers` working as the startup default, so a headless or
  scripted deployment is unchanged.

Out of scope: changing which tags the overlay draws, multi-monitor
selection from the phone (the startup flag still chooses the display),
and any change to detection, solving or the pipeline's per-frame
behaviour.

## Capabilities

### New Capabilities
- `marker-source-control`: choosing the marker source while running —
  the overlay process's lifecycle under the server, the handshake that
  keeps the drawn and solved layouts identical, switching the live
  pipeline, and reporting the current state and any failure.

### Modified Capabilities
- `phone-client`: the client gains a marker source control and has to
  show what the source currently is and when selecting one failed.

## Impact

- New: `src/boresight/marker_source.py` (the controller and the overlay
  process lifecycle), endpoints on the existing server, a control on
  the phone page, and their tests.
- Modified: `server.py` — the pipeline becomes something read per frame
  rather than captured when a session opens, so a switch reaches an
  already-connected phone. `overlay/__main__.py` — reports the geometry
  it used. `web/index.html` and `web/capture.js` — the control.
- Unchanged: `solve.py`, `detect.py`, `pipeline.py`, `marker_map.py`,
  `overlay/layout.py`, `overlay/render.py`. `AimPipeline` stays
  stateless and immutable; a switch replaces the instance rather than
  mutating one.
- Dependencies: none added. The overlay's Qt extra is still optional and
  still only needed on the machine with the display.
- **Security:** this lets an authenticated client start a process on the
  PC. It sits behind the existing token, the command is fixed rather
  than composed from request data, and the only caller-supplied value is
  a display index validated as an integer. Worth stating plainly
  because "web request spawns a process" deserves the scrutiny.
- **Deployment:** starting the overlay requires the server to be running
  inside the desktop session, not headless. A server that cannot reach a
  display must report that on selection rather than failing obscurely.
- README: the on-screen markers section documents the two-terminal
  procedure this replaces.
