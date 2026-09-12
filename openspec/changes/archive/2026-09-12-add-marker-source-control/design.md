## Context

Two pieces exist and do not meet. `overlay/` draws tags and knows the
display; `server.py` solves frames and owns a layout chosen once at
startup by `--markers`. Joining them means two things the current code
cannot do: change the layout while running, and start a process.

One property from the overlay's design constrains everything here. The
layout is a pure function of `(screen_px, tag_px, inset_px)`, called by
both the renderer and the solver, which is what makes it impossible for
them to disagree. That guarantee has to survive: whatever the server
learns about the display, it must end up calling the same function with
the same three numbers the overlay used.

## Goals / Non-Goals

**Goals:**

- One control on the phone, showing what is actually true.
- No `--markers screen:1920x1080` to get right by hand.
- A switch that reaches a phone already streaming, on the next frame.
- An overlay that cannot outlive the server that started it.

**Non-Goals:**

- Choosing the monitor from the phone. The startup flag still picks it;
  a phone-side display picker is a menu for a problem nobody has yet.
- Changing tag size or inset at runtime.
- Any change to how a frame is solved. This selects a layout; it does
  not touch the pipeline's per-frame behaviour.
- Running the overlay on a different machine from the server. The
  server injects the cursor on that display already; splitting them
  would be a different architecture.

## Decisions

### A controller owns the mutable state; `AimPipeline` stays immutable

`AimPipeline` is deliberately stateless and holds fixed collaborators.
Making its marker map swappable would put mutable state inside the one
object whose docstring promises it has none.

Instead a `MarkerSourceController` holds the current source, the current
pipeline, the overlay process, and the last failure. Switching builds a
*new* `AimPipeline` and swaps the reference. The old instance is
discarded rather than mutated.

### Sessions read the pipeline per frame, not per connection

Today `run_frame_session` is handed `app.state.pipeline` when the socket
opens, so a switch would not reach a phone already streaming — it would
keep solving against the layout that was current when it connected,
with nothing to indicate it.

So the session takes the controller and asks for the current pipeline
each frame. That is a dictionary lookup against several milliseconds of
detection and solving, and it is what makes "switching reaches an
already-connected client" true rather than aspirational.

### The overlay reports its geometry; the server does not guess

On start, the overlay writes one JSON line to stdout describing what it
rendered: display size, tag size, inset. The server reads that line,
then builds the solver's layout by calling `overlay_layout` with exactly
those numbers.

*Why not have the server detect the resolution:* it would need a display
connection and probably Qt, which is precisely the dependency the
overlay extra exists to keep optional. It would also be a second
opinion about the display, and two opinions is how they diverge.

*Why this does not break the pure-function guarantee:* the function is
still the single source of the layout. Only its inputs travel, and they
travel from the side that can actually see the display. Both sides
still compute the same layout from the same three numbers.

*Why stdout rather than an HTTP callback or a file:* the server is
already the overlay's parent, so a pipe is the shortest path with no
port, no path, and no cleanup. A structured line rather than parsing
the human-readable banner, so the message and the display text can
change independently.

### Failure is a state, not an exception

Selecting on-screen markers can fail for reasons that are nobody's
mistake: a GNOME Wayland session, the overlay extra not installed, a
headless server. All of those already produce a clear explanation from
`overlay/backend.py`.

The controller captures the child's output, leaves printed markers
active, and stores the explanation for the phone to display. It never
reports on-screen markers as active because it was asked to — only
because the overlay actually started and reported geometry.

*Why this is worth insisting on:* the alternative is a toggle that says
"on" while nothing is on screen, and a solver quietly using a layout
for tags that do not exist. That would present as terrible aim accuracy
with no visible cause.

### The child dies with the parent, and this is load-bearing

Terminated in the server's lifespan shutdown, and on every path that
replaces it.

Ordinarily leaking a child process is untidy. Here it is worse: the
overlay is input-transparent, takes no keyboard focus, and has no title
bar, so nothing the user can click will remove it. Its own Ctrl-C
handling only helps whoever holds its terminal, and when the server
spawned it that terminal is the server's. An orphaned overlay is a
genuine "how do I get this off my screen" problem.

### Endpoints, not WebSocket messages

`GET /markers/source` and `POST /markers/source`. The frame socket
carries frames and telemetry; putting a control that starts processes on
it would mean the phone must be streaming to change a setting it might
want to change *before* streaming.

The existing token middleware covers both, since it covers everything.

### Health is polled with the state, not tracked eagerly

Whether the overlay is still alive is checked when the state is read,
by polling the child. No watchdog task, no callback. The state is read
whenever the phone asks, which is often enough to notice a crash and far
simpler than a supervisor.

## Risks / Trade-offs

**An HTTP request can start a process** → Behind the token, from a fixed
command, with no request content reaching the argument list; the only
caller-supplied value is a display index parsed as an integer. Called
out in the proposal because it deserves the scrutiny rather than a
footnote.

**The server must run inside the desktop session** → True, and already
true for cursor injection, which needs the same session. A headless
server reports the failure on selection rather than misbehaving.

**Reading the pipeline per frame is a shared mutable reference across
tasks** → Mitigated by the swap being a single reference assignment,
which is atomic under the GIL, and by the pipeline being immutable once
built. A frame gets either the old pipeline or the new one, never a
half-changed one.

**The geometry handshake can hang** → The read is bounded by a timeout;
if the overlay neither reports nor exits within it, the child is killed
and the selection fails with that explanation. A hang here would
otherwise block the request.

**Untested against a real display** → As with the overlay itself, the
process lifecycle can be tested with a stub child, but "tags appear and
the aim is right" needs the desktop session and a camera. The manual
tasks say so rather than implying coverage.
