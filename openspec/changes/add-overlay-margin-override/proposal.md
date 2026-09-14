## Why

Real-device testing on a multi-monitor setup found an on-screen marker
tag hidden behind a visible desktop taskbar. The overlay already avoids
desktop panels by asking Qt for `screen.availableGeometry()`
(`qt_backend.py`), but on the affected monitor Qt reported zero
reservation even though a taskbar visibly occupied its bottom edge —
confirmed live: the server's own log line
(`overlay running on 1920x1080, tags 86px inset 22px`) carries no
"reserved by desktop panels" suffix at all for that screen. The root
cause is a real limitation of the X11 EWMH properties the overlay's
XWayland-hosted Qt process reads: `_NET_WORKAREA` is one rectangle for
the whole virtual desktop, not per monitor, so a monitor whose panel
reservation doesn't happen to overlap that single global rectangle's
band is reported as having no reservation at all, regardless of what a
panel actually occupies on it. This is an environment limitation, not
something the overlay's own geometry math gets wrong — see design.md
for why smarter auto-detection isn't the fix.

## What Changes

- Add a manual "extra margin" the overlay subtracts from Qt's
  auto-detected available area on all four sides, on top of whatever
  panel reservation Qt itself found (zero or otherwise). This exists
  specifically for the case demonstrated above: a setup where automatic
  detection under-reports what is actually reserved on a given monitor.
- Expose it as `--extra-margin-px` on `python -m boresight.overlay`
  (alongside the existing `--tag-px`/`--inset-px`), and thread the same
  value through the server's own launch path
  (`MarkerSourceController` → the spawned overlay subprocess), which
  today only forwards `--display` and drops `--tag-px`/`--inset-px`
  entirely rather than exposing them to whoever starts the server.
- Zero by default: an unset or zero margin changes nothing about
  today's behavior or its test coverage.
- Also expose it live from the phone: a new `POST
  /markers/overlay-margin` route lets the margin be set while the
  server is running, restarting the overlay with the new value
  immediately if on-screen markers are currently active, so an operator
  can dial it in by eye against the taskbar it exists for — without a
  server restart, which the CLI flag alone would require. The phone
  client gains a stepper control for it next to the existing marker
  source buttons.

## Capabilities

### Modified Capabilities
- `marker-overlay`: adds a requirement that the panel-avoidance margin
  can be manually extended, for a display environment where automatic
  detection under-reports what is actually reserved.
- `phone-client`: adds a requirement that the margin can be set from
  the phone, and takes effect on the running overlay without a restart.

## Impact

- `src/boresight/overlay/qt_backend.py`: `run()` gains an
  `extra_margin_px` parameter, applied to `available` before `area_px`
  is derived.
- `src/boresight/overlay/__main__.py`: new `--extra-margin-px` CLI flag.
- `src/boresight/marker_source.py`: `MarkerSourceController` and
  `_overlay_command()` gain the same parameter, forwarded to the
  spawned subprocess.
- `src/boresight/server.py`: `create_app()`/`main()` gain a way to set
  it at server startup (CLI flag), alongside the existing `--display`;
  a new `POST /markers/overlay-margin` route sets it at runtime.
- `src/boresight/web/index.html` / `capture.js`: a stepper control next
  to the marker source buttons, reading and setting the margin over the
  new route.
- No change to `AimPipeline`, the frame wire protocol, or default
  behavior when the value is left at zero.
