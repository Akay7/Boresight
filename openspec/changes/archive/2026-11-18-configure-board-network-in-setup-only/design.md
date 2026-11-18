# Design

## Context

See proposal.md for why. Today (`add-esp32-cam-setup-portal`):

- `main/Kconfig.projbuild`'s Network menu has the Wi-Fi name and
  password, the server address and port, the token, and TLS, in both
  profiles.
- `settings_build_defaults()` (`main/settings.c`) copies those into the
  defaults. The NVS namespace `boresight` stores each setting only where
  it differs from the build's value. Erasing the namespace is "reset to
  build defaults".
- A board is "configured" when the effective Wi-Fi name is non-empty
  (`setup.c`), whether stored or built in. `main.c`'s
  `configuration_complete()` still points at `menuconfig` when it is
  empty, though a board with no Wi-Fi name never gets there: it opens
  setup mode first.
- The emulator profile (`sdkconfig.emulator`) builds in the server's
  address `10.0.2.2`, port 7391 and an `emulator-token`. The end-to-end
  suite relies on this to stream from boot, and one test overrides the
  token through the setup page.
- CI checks that the generic image's four secret options are empty.

## Goals / Non-Goals

**Goals:**
- A board's network settings and token have exactly one source: what is
  stored on the device.
- No board build can contain them, so no image can leak them.
- The emulator keeps starting connected, unchanged.

**Non-Goals:**
- Moving camera defaults, their ranges, the pins or TLS off the build.
- A settings page on the home network. Setup mode stays the only way
  in.
- Changing the NVS layout or keys. Boards configured through setup mode
  keep everything.

## Decisions

### 1. The network options exist only in the emulator profile
In `Kconfig.projbuild`:
- The server address, port and token gain
  `depends on BORESIGHT_EMULATOR`.
- The Wi-Fi name and password are removed. The emulator has no Wi-Fi.
- TLS stays in both profiles.

A board's `menuconfig` then shows only TLS under Network, and its
`sdkconfig` has no such keys.

- *Alternative:* keep the options, but ignore them on a board. Rejected:
  a setting that is offered and then silently ignored is the confusion
  this change removes.
- *Alternative:* remove them from the emulator too, and configure it
  through its setup page before each test. Rejected: every end-to-end
  test would start with a setup round trip, for no behaviour that
  matters on a board.

### 2. Board defaults: empty network, port 7331 in code
`settings_build_defaults()` on a board leaves the Wi-Fi name and
password, the server address and the token empty, and sets the port to
7331, the server's own default, as a named constant. The stored-only-
if-different rule is kept as it is:
- a port of 7331 is not stored;
- any network value a board has is, by construction, stored.

`configured()` keeps its test, which now means "stored". The
emulator's defaults still come from its Kconfig values.

### 3. Where each value came from, in the boot log
Network values on a board are logged as `(device)` or `not set`, and
the port as `(device)` or `(default)`. Camera values keep `(device)`
or `(build)`. The emulator keeps `(build)` for its network values. The
log then never claims a board took a network value from its build.

### 4. Messages and the page
- `configuration_complete()` drops its board branch. Setup mode is the
  answer for a board with no network, and it is reached first. The
  emulator's missing-address check stays.
- The setup page's reset button keeps its name. Its description says it
  forgets the Wi-Fi, server and token, and that the board then opens
  setup mode by itself.

### 5. CI checks absence, not emptiness
`firmware.yml`'s "nothing secret went in" step checks that the generic
build's `sdkconfig` has no `CONFIG_BORESIGHT_WIFI_*`, `SERVER_HOST` or
`TOKEN` key at all, keeping the certificate check. The old check
(empty values) would pass vacuously.

## Risks / Trade-offs

- **[Risk]** A board that relied on `menuconfig` network settings,
  updated over Wi-Fi or by flashing without erase, comes back
  unconfigured. → **Mitigation:**
  - It opens setup mode by itself, the setup-mode LED shows it, and the
    boot log says so.
  - Entering the network takes about a minute from a phone.
  - The README's update notes say so.
  - A board configured through setup mode, as the bench board is, is
    unaffected.
- **[Trade-off]** After every erase, a developer enters the Wi-Fi and
  token from a phone. → Flashing without erase keeps them, and the
  page's sign-in prompt makes setup quick.
- **[Risk]** The firmware's port default drifts from the server's. →
  One named constant with a comment pointing at the server's default.
  Both are 7331 and documented together.
- **[Risk]** An old local `sdkconfig` still holds the removed keys. →
  The build ignores symbols that no longer exist and drops them on the
  next `menuconfig` save. The README says the lines can be deleted.

## Migration Plan

1. Archive `add-esp32-cam-setup-portal` first. This change modifies
   requirements it introduces.
2. Implement. A board configured through setup mode needs nothing.
3. The developer's `firmware/boresight-cam/sdkconfig`: delete the
   network lines, or leave them; they no longer apply.
4. Rollback: an older image reads the same NVS keys, so stored settings
   keep working. It would also accept build-time network values again.
