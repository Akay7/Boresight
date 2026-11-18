# Design

## Context

See proposal.md for why. The current state that shapes the approach:

- **Every setting is a compile-time constant.** `CONFIG_BORESIGHT_*` is
  read in `wifi.c` (SSID, password), `link.c` (host, port, token, TLS),
  `camera.c` (resolution, quality, exposure, gain) and `main.c` (frame
  rate cap, send timeout, the completeness check). The link builds its
  URI once in `link_start()`.
- **NVS exists but holds nothing of ours.** `main.c` initialises it after
  the configuration check, for the Wi-Fi driver. The partition is 24 KB
  (`0x9000`, `0x6000`) in both the device and the emulator tables, and
  the Wi-Fi driver and PHY calibration keep data there too.
- **Flash budget.** The device app is 1.04 MB in a 1.47 MB factory
  partition. The emulator's is 3 MB, sized for its embedded frames.
- **Pure logic lives in `components/boresight_proto`.** Wire format,
  debouncer, pin allowlist, back-off and LED patterns have no ESP-IDF
  includes and are tested on the host (`test_host/`). New pure logic
  goes there too.
- **The emulator uses QEMU user networking.** `run-emulator.sh` runs
  `-nic user,model=open_eth`, so the guest reaches the host at 10.0.2.2.
  Nothing reaches the guest without a `hostfwd`, and multicast does not
  cross. `esp_restart()` reboots the emulated chip and the flash image
  file keeps its writes for the rest of the run. The script re-merges the
  image on every start, so each run begins with empty NVS.
- **The server.** It resolves `0.0.0.0` to a LAN address for the device
  block (`ServerConfig.advertised_host()`), starts and stops background
  work in the FastAPI `lifespan`, and validates `server.*` keys from the
  settings file with flag precedence.

## Goals / Non-Goals

**Goals:**
- Change every network, server and camera setting on a board with only
  a phone, and keep the old `menuconfig` path working unchanged.
- Keep the setup network's exposure small: physical action to open it
  on a configured board, a hard 10-minute lifetime, and secrets that are
  write-only.
- Test the setup page's logic on the host, and the save → restart →
  connect path in the emulator. Only the radio-specific parts are left
  to hardware.

**Non-Goals:**
- Setting TLS, the trusted certificate or the pin assignments from the
  page. They stay build-time.
- Updating firmware over the air.
- Encrypting NVS (flash encryption). Secrets in flash were already in
  plain text in the image.
- A native app or BLE provisioning.
- Discovery in the emulator.

## Decisions

### 1. Settings: one effective struct; build values are defaults, NVS overrides
A pure `bp_settings_t` (in `boresight_proto`) holds every editable
setting. At boot `settings.c` fills it from Kconfig, then overlays each
key found in NVS namespace `boresight`. Modules read the struct, never
`CONFIG_BORESIGHT_*`, for anything editable. Keys are short and fixed
(`ssid`, `pass`, `host`, `port`, `token`, `res`, `jpegq`, `fps`, `aec`,
`agc`), each stored only if set on the device, so "not stored" and
"stored as the default" stay distinguishable. "Reset to build defaults"
is `nvs_erase_all` on our namespace only, never the whole partition,
which also holds Wi-Fi and PHY data.

- *Alternative:* Kconfig wins when non-empty. Rejected: then the page
  could never change a value a build set, which is exactly what it is
  for.
- *Alternative:* one blob key holding a struct. Rejected: per-key values
  survive adding a field without a migration, and an absent key falls
  back to its default for free.

### 2. Entering setup mode: decided once, at boot, before the camera starts
The boot order becomes:
1. NVS init (moved earlier).
2. Settings load.
3. The trigger-hold check: configure the trigger GPIO as an input with
   its pull-up, and if it reads pressed, sample it for up to 5 s. Any
   release ends the check.
4. Branch to setup mode or normal mode.

Setup mode never starts the camera, buttons or link, so it does not
compete with them for RAM or the radio. Leaving setup mode is always
`esp_restart()`, so normal mode starts from a clean boot. The emulator
enters setup mode through a one-shot NVS key, `setup_next`, which the
`setup` console command sets before restarting and boot erases once
read.

- *Alternative:* switch modes live, without a restart. Rejected: it
  doubles the state space (camera running alongside the AP, link
  half-torn-down) for no user-visible gain.
- *Alternative:* RTC no-init memory for the emulator flag. Rejected: it
  is unproven to survive QEMU's software reset, while NVS writes do
  survive within a run.

### 3. The setup network: open SoftAP in APSTA mode, captive DNS, `esp_http_server`
`WIFI_MODE_APSTA`, so the device can scan while serving:
- **The network:** SSID `Boresight-` plus the last two bytes of the SoftAP
  MAC in hex, open, channel 1, at most 2 stations, with the stock DHCP
  server and **4.3.2.1** as the device's address. Not the default
  192.168.4.1: on the bench, an Android phone looked up
  `connectivitycheck.gstatic.com`, was answered 192.168.4.1, and never
  made its check request, so it reported "no internet" where a PC
  offered the sign-in page. WLED uses 4.3.2.1 for the same reason. The
  network has no internet, so the address collides with nothing.
- **The sign-in address in DHCP:** option 114 (RFC 8910) carries
  `http://4.3.2.1/`, which phones that honour it open without a check.
- **Name lookups:** a small UDP responder on port 53 answers every A query
  with 4.3.2.1 and anything else with an empty answer, and logs each
  query, so a phone's checks can be seen. The packet
  logic is a pure function in `boresight_proto`, host-tested against
  captured query bytes.
- **The page server:** `esp_http_server` serves `GET /`, `GET /scan`,
  `POST /save` and `POST /reset`. A catch-all handler answers any other
  path, including the phones' sign-in checks (`/generate_204`,
  `/hotspot-detect.html`, `/connecttest.txt`), with a redirect to `/`,
  and logs it.
- **The page:** one inline HTML document with inline CSS and no
  JavaScript requirement. The phone has no internet on this network, so
  nothing can come from a CDN.
- **Scanning:** once on entering setup mode, before the AP starts. A
  rescan button is offered, which may briefly disturb the phone's link.

- *Alternative:* ESP-IDF's `wifi_provisioning` with Espressif's phone
  app. Rejected: it needs an app, and it only covers Wi-Fi credentials,
  not server or camera settings.
- *Alternative:* the IDF captive-portal example's `dns_server` component.
  Rejected: it is example code, not a published component. A
  ~100-line responder whose packet code is host-tested is smaller to own.

### 4. Form handling and the page are pure, escaped and write-only for secrets
In `boresight_proto`, all host-tested:
- `bp_form_decode`: `application/x-www-form-urlencoded`, `+` and `%XX`,
  bounded output, rejecting malformed escapes.
- `bp_settings_apply_form`: validates every field against the limits in
  the esp32-cam-setup spec. The camera ranges are the Kconfig ranges,
  passed in so the pure code shares the firmware's limits. It writes
  nothing unless every field passes, and returns per-field errors.
- `bp_html_escape`: everything echoed into the page goes through it,
  including scanned SSIDs, which come from strangers' access points.

The password and token are never rendered. Their fields show "set" or
"not set". An empty submission keeps the stored value, and a separate
"clear" checkbox removes it. The save response is sent and flushed
before a ~1.5 s timer calls `esp_restart()`.

### 5. Lifetime: a one-shot 10-minute timer from entering setup mode
It is started when the AP comes up and not extended by activity, so the
window is fixed. On expiry it stops the AP and restarts if an SSID is in
effect. Otherwise it sets the error pattern and parks. A save or reset
restarts sooner.

- *Alternative:* 10 minutes of inactivity. Rejected: a page left open on
  a phone would keep the network up indefinitely.

### 6. Discovery: `zeroconf` on the server, the `espressif/mdns` component on the device
**Server:** `AsyncZeroconf` registered in the lifespan when
`announce` is on and the bind address is not loopback, and unregistered
on shutdown.
- It registers the service `Boresight on <hostname>._boresight._tcp.local.`
  at the advertised LAN address(es) and the server's port.
- Its TXT record carries `path=/ws/frames`, `tls=0|1` and `v=1`. It never
  carries the token.
- The new setting `server.announce` (default true) gets
  `--announce/--no-announce`, following the existing precedence rules.
- The startup device block gains an `announce` line, and its `host` line
  says the address may be left empty when announcing.

**Device:** `mdns_init()` once the network is up. While the effective
host is empty, each connection attempt runs
`mdns_query_ptr("_boresight", "_tcp", 3000 ms)`.
- It takes the first result with an IPv4 address and logs every result.
- A TXT `tls` value that disagrees with the build's TLS setting is a
  configuration error: error pattern, maximum back-off.
- The link builds its URI per attempt instead of once in `link_start()`.
- A TLS connection to a discovered IP still verifies the pinned
  certificate. The server already regenerates its certificate to cover a
  new LAN address, and the device then needs the new certificate exactly
  as it does today.

- *Alternative:* a custom UDP broadcast "where are you?" protocol, with
  no new server dependency. Rejected: mDNS is the standard, debuggable
  with `avahi-browse`, and the ESP-IDF component already exists.
- *Licence:* python-zeroconf is LGPL-2.1-or-later. It is used unmodified
  as an installed dependency of an MIT project, which LGPL permits.
  Noted in the extra's comment.

### 7. The emulator: the same page over openeth, reachable via a loopback-only hostfwd
- In the emulator build, setup mode skips the AP, DNS and scan, and
  serves the HTTP handlers on the Ethernet interface.
- `run-emulator.sh` adds `hostfwd=tcp:127.0.0.1:${BORESIGHT_EMULATOR_SETUP_PORT:-7380}-:80`
  to `-nic user`, bound to loopback so nothing else on the LAN can reach
  it.
- The opt-in suite gains two tests:
  - An invalid submission is refused and nothing changes.
  - A wrong token is refused; then `setup`, posting the right token, and
    the restart lead to streaming.

  Each test runs against the run's freshly merged image, so stored
  settings never leak between runs.

### 8. The LED: a new link state and pattern
`BP_LINK_SETUP` maps to `BP_LED_DOUBLE_BLINK`, two short flashes every
1.5 s. It is distinct from the slow blink, fast blink, error flash,
solid and heartbeat patterns, which a host test checks. During the boot
hold, the LED switches to it the moment 5 s are reached.

## Risks / Trade-offs

- **[Risk]** The setup network is open and the page is plain HTTP, so
  someone in radio range during setup could read the submitted Wi-Fi
  password and token, or submit their own settings. → **Mitigation:**
  - On a configured board, setup needs the trigger held at boot.
  - The network lives at most 10 minutes and closes on save.
  - Secrets are never sent back.
  - The trade-off is documented in the README beside the existing
    "plain-text token" note.
  - A WPA2 option can follow without changing the specs' observable
    flow.
- **[Risk]** Someone configures an unconfigured board before its owner
  does. → **Mitigation:** low value to an attacker, since they learn no
  secret of the owner's and get the camera's view of the TV. The owner's
  next trigger-hold setup overrides it.
- **[Risk]** The app grows past the 1.47 MB partition. → **Mitigation:**
  measure after adding `esp_http_server` and `mdns` (an estimated
  +150–250 KB). If needed, switch the device table to a custom one with a
  larger factory partition; the 4 MB flash has room.
- **[Risk]** Holding the trigger at power-on could be confused with a
  stuck switch, putting the board in setup mode on every boot. →
  **Mitigation:** it needs 5 s held from boot, and the setup pattern
  makes it visible. A stuck switch shows as setup mode and is logged on
  serial.
- **[Risk]** Several servers are announced on one LAN. →
  **Mitigation:** the device takes the first and logs all of them. The
  page's address field pins one.
- **[Risk]** Settings stored on the device silently override a later
  `menuconfig` change. → **Mitigation:**
  - Boot logs which settings came from the device and which from the
    build.
  - The README says so.
  - "Reset to build defaults" is one tap.
- **[Trade-off]** Discovery cannot be tested in the emulator (multicast
  does not cross user networking). → The server side is unit-tested with
  a fake zeroconf, the device's TXT handling is host-tested, and the
  end-to-end discovery check is a hardware bring-up task.

## Migration Plan

- **Existing boards keep working.** A board flashed with `menuconfig`
  settings has no NVS keys of ours, so after the update it runs exactly
  as before. Setup mode opens only when held for, or when no SSID is
  built in.
- **The emulator profile keeps its built-in host and token**
  (`sdkconfig.emulator`), so the existing end-to-end tests are unchanged.
- **Rollback:** flashing an older image ignores the `boresight` NVS
  namespace, and the build values apply again.
- **Server:** `announce` defaults on only for network-bound servers. A
  loopback-only server behaves as before, and `--no-announce` restores
  the old behaviour exactly.
