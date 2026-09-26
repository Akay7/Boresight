## Why

Two ways the server-managed overlay can go wrong in ordinary use, both
invisible until they bite.

The overlay's stderr is a pipe that nobody reads until the process has
already died. A pipe holds about 64 KiB. An overlay that is chatty on
stderr — Qt platform warnings, a repeated driver complaint — fills it,
and its next write blocks forever. A blocked overlay is still "alive",
so the server keeps reporting on-screen markers as active while the
window has stopped repainting or, worse, is stuck mid-start and never
reports its geometry at all.

Switching the marker source has no serialization. Two quick taps on the
phone arrive as two concurrent requests, each running in its own
threadpool worker, and both can pass the "already active?" check before
either has started anything. The result is two overlay processes, one of
which the controller no longer holds a handle to — exactly the orphaned,
un-dismissable window the controller exists to prevent. The same race
exists between a switch and a margin change, and between a switch and
server shutdown.

## What Changes

- Drain the overlay's stderr continuously from the moment it starts,
  keeping a bounded tail of recent lines and forwarding each line to
  the server's log. A failure explanation is taken from that tail
  rather than from a read after death.
- Drain the overlay's stdout after the geometry line too. Nothing in
  the overlay writes there after the handshake today, but a library
  that prints would otherwise reintroduce the same freeze.
- When an overlay that was running exits on its own, the reported error
  carries its last line of output, so the reason reaches the phone.
- Serialize every marker-source change — selecting a source, changing
  the overlay margin, shutting down — behind one lock in the
  controller. Selecting the source already active, or setting the margin
  already in effect, is a no-op.
- Shutdown aborts a start that is still waiting for the overlay's
  geometry, rather than waiting it out, and no start can begin after
  shutdown.
- Reading the state never waits on a switch in progress; it reports
  `switching: true` instead.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `marker-source-control`: switching becomes serialized (concurrent
  requests cannot start two overlays; shutdown cannot race a switch),
  the overlay's output is always drained so it cannot block, and the
  reported state gains a `switching` flag and an exit reason for an
  overlay that died on its own.

## Impact

- Modified: `src/boresight/marker_source.py` (pipe draining, the lock,
  shutdown ordering), `tests/test_marker_source.py`,
  `tests/test_marker_source_routes.py`.
- Unchanged: `server.py` — the routes are already plain `def`, run in
  FastAPI's threadpool, and call the controller synchronously; the
  lock lives in the controller where every caller goes through it. The
  overlay itself is unchanged.
- API: `GET /markers/source` and the switch responses gain a boolean
  `switching` field. Additive; existing clients ignore it.
- Dependencies: none.
