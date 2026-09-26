## Context

`MarkerSourceController` (`marker_source.py`) starts the overlay with
both stdout and stderr as pipes. stdout carries one JSON geometry line,
read by a short-lived thread with a timeout; stderr is read only by
`_explain_exit`, after the process has died. Nothing reads either pipe
while the overlay runs. See proposal.md for why that freezes it.

The routes that change the source — `POST /markers/source` and
`POST /markers/overlay-margin` in `server.py` — are plain `def`
functions. FastAPI runs those in its threadpool, so two requests are two
OS threads calling the controller at the same time. `GET
/markers/source` is also a plain `def`, and `state()` mutates: it
reaps an overlay that died. Shutdown is called from the lifespan
handler, on the event loop thread, synchronously.

The frame path reads `controller.pipeline` once per frame from the
executor. That read is a single attribute load and must stay free of
any lock.

## Goals / Non-Goals

**Goals:**

- No amount of overlay output can block the overlay.
- At most one overlay process exists, whatever order requests arrive in.
- Shutdown finishes promptly and leaves nothing running, even if it
  lands in the middle of a start.

**Non-Goals:**

- Changing the overlay itself, or the geometry handshake's format.
- Queueing or coalescing requests beyond "one at a time". A tap that
  arrives during a switch waits for it, then runs against the new state.
- A supervisor that restarts a dead overlay. Liveness is still polled
  on read.

## Decisions

### One reader thread per pipe, for the life of the process

A small `_PipeDrain` starts a daemon thread per pipe as soon as the
process is launched. It reads line by line until EOF, keeps the last
`OUTPUT_TAIL_LINES` (20) lines in a `deque`, and forwards every line to
the `boresight.overlay` logger. Lines are read with a length cap
(`OUTPUT_LINE_CHARS`, 1000), so one enormous line without a newline is
split into pieces rather than buffered whole: memory stays bounded at
roughly 20 KB per pipe regardless of what the child does.

A start that fails because shutdown stopped it reports "the server is
shutting down", not the overlay's exit status.

The stdout drain also hands its first line to whoever is waiting for
the geometry, through a one-slot queue. That replaces
`_readline_with_timeout`'s throwaway thread: one reader owns the pipe
from start to EOF, so there is no hand-over between "the thread reading
the geometry" and "the thread draining the rest" in which the pipe is
briefly unread or read by two threads at once.

Alternatives considered:

- *Send stderr to `DEVNULL` or to the server's own stderr.* Either
  removes the freeze, but `DEVNULL` loses the overlay's explanation —
  the most useful part of a failure — and inheriting the server's
  stderr puts it in the log without any way to attach it to the error
  the phone sees.
- *`select`/`selectors` on the pipes.* Not portable to Windows pipes,
  which is why the geometry read already uses a thread.
- *`communicate()`.* Waits for exit; the overlay is meant to run.

**stdout is drained too.** The overlay's own code writes nothing to
stdout after the geometry line — the banner and every diagnostic go to
stderr. But a third-party library that `print`s is enough to fill the
pipe eventually, and draining it costs one idle thread. Lines after the
first are logged, not kept for error messages.

### Forwarded output goes to DEBUG; failures surface it at WARNING

Per-line forwarding is at DEBUG on `boresight.overlay`. The case this
change exists for is an overlay that writes a lot; at INFO, a Qt
warning repeated per frame would bury the server's own log. What
matters is still visible at the default level: a failed start already
logs a warning carrying the explanation (now from the tail), and an
overlay that exits on its own is logged at WARNING with its last line,
and that line is appended to the `error` the phone sees.

### A `threading.Lock` in the controller, not an `asyncio.Lock`

The callers are threadpool threads (the sync routes) and the event loop
thread (lifespan shutdown). An `asyncio.Lock` would do nothing for the
former. The lock lives in the controller rather than in `server.py`
because every path that changes the source goes through the controller,
tests drive the controller directly, and shutdown needs it too.

`select()`, `set_overlay_extra_margin_px()`, `stop_overlay()` and
`shutdown()` take it. The no-op checks ("already this source, overlay
alive"; "already this margin") are made *inside* the lock, so the
second of two concurrent taps sees the first one's result and returns
it rather than starting another overlay. A plain `Lock` rather than
`RLock`: internal helpers assume the lock is held and never re-acquire
it, which keeps the locking visible at the public entry points.

### Reading the state never waits

`state()` tries the lock without blocking. If it gets it, it reaps a
dead overlay as before. If a switch holds it — which can last up to the
geometry timeout — it returns a snapshot without reaping and with
`switching: true`. Blocking instead would stall the phone's poll for
the length of an overlay start. Skipping the reap during a switch is
not just an optimisation: mid-restart, the source is still `screen`
while the old process has already been stopped, and a reap then would
report the overlay as having "exited on its own" when it was
deliberately replaced.

The snapshot is assembled from several attributes without the lock, so
during a switch it can mix old and new values. It is flagged as
`switching`, and the switch's own response is the authoritative result.

### Shutdown aborts a start in progress

`shutdown()` first sets a `_closed` flag, then — if the lock is held —
terminates whatever process is currently stored as starting. The start
is waiting on the stdout drain's first line; the child's death gives it
EOF immediately, the start fails through the ordinary "exited without
reporting" path, and releases the lock. Shutdown then takes the lock
and stops anything left. Without this, a Ctrl-C during an overlay start
would sit for up to `GEOMETRY_TIMEOUT_S` (20 s).

The flag closes the remaining window: a start checks `_closed` after
storing its process and before waiting for geometry, and again after
receiving it. Setting the flag before reading the process (in
shutdown) and storing the process before reading the flag (in a start)
means at least one side always sees the other. Once closed, selecting
on-screen markers or changing the margin raises `MarkerSourceError`
("the server is shutting down") and starts nothing; selecting printed
markers still succeeds, since it only ever stops things.

### Setting the margin already in effect is a no-op

The spec's "selecting the active source changes nothing" is extended to
the margin: a restart that would produce the same overlay is pure cost,
and two taps on the same value would otherwise restart it twice. Both
`select()` and the margin setter reap a dead overlay first, under the
lock, so "already on screen" always means an overlay that is actually
running; a dead one is replaced by printed markers, not silently kept.

### `stop_overlay()` also returns to printed markers

It used to stop the process and leave the source alone, relying on the
next `state()` to notice. With `state()` no longer reaping during a
switch, and the reap now reporting "exited on its own", that would
misreport a deliberate stop. Nothing outside the controller calls it;
internally `_stop_overlay_locked()` does the stopping and each caller
decides the source.

### `switching` is added to the state

An additive boolean on every state response. The phone client does not
read it yet; nothing else about the response shape changes.

## Risks / Trade-offs

- [A grandchild inherits the overlay's pipes and keeps them open after
  the overlay exits, so the drain never sees EOF] → Joins on the drain
  are bounded by `STOP_TIMEOUT_S`, and the threads are daemons, so a
  stuck drain costs a thread, never a hang or a blocked shutdown.
- [A request that arrives during a slow start waits up to the geometry
  timeout for the lock] → Acceptable: it is the same wait the first
  request has, and the second request then usually returns immediately
  as a no-op. `GET` does not wait.
- [Shutdown on the event loop thread blocks the loop while waiting for
  the lock] → The switch holding it does not need the loop, so there is
  no deadlock, and aborting the in-flight start keeps the wait short.
- [The drain's DEBUG logging hides overlay chatter by default] →
  Deliberate (see above); failures still surface at WARNING.
- [`stop_overlay()` now takes the lock, so calling it from inside a
  locked section would deadlock] → Internal code calls
  `_stop_overlay_locked()`; `stop_overlay()` is only the public entry.
