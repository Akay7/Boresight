// The phone half of the camera link.
//
// Captures from the rear camera, draws each frame to an offscreen
// canvas, encodes it as JPEG, and sends it as one binary WebSocket
// message: an 8-byte little-endian timestamp from this device's clock,
// then the JPEG bytes. The timestamp is only ever compared against a
// later reading of the same clock, so the two machines never need to
// agree on an epoch -- the server echoes it back untouched and we
// subtract here.

"use strict";

const CONFIG = {
  width: 1280,
  height: 720,
  targetFps: 20,
  jpegQuality: 0.7,
  // Skip a capture rather than add to a backlog the socket has not
  // drained. A client-side queue produces exactly the staleness the
  // server's drop policy exists to prevent, one hop earlier.
  maxBufferedBytes: 512 * 1024,
  // Matches HEADER_SIZE in stream.py. Spelled out because JavaScript
  // cannot import it.
  headerBytes: 8,
  // A low fixed exposure. Paper markers beside a bright panel are a
  // severe dynamic-range case, and auto-exposure chases the panel until
  // the markers are mud.
  exposureTime: 300,
};

const els = {};
for (const id of [
  "preview", "overlay", "start", "trigger", "message", "marker-sheet",
  "source-printed", "source-screen", "debug-on", "debug-off",
  "row-decoded", "row-reprojection", "row-lag",
  "stat-connection", "stat-camera", "stat-exposure", "stat-rtt",
  "stat-markers", "stat-aim", "stat-frames", "stat-lost", "stat-skipped",
  "stat-timing", "stat-shots", "stat-decoded", "stat-reprojection", "stat-lag",
]) {
  els[id] = document.getElementById(id);
}

const state = {
  socket: null,
  stream: null,
  timer: null,
  sending: false,
  skipped: 0,
  starting: false,
  // Overlay off by default: the reticle is what you need to aim, the
  // geometry is what you need to debug.
  debug: false,
  geometry: null,
  // What the camera actually granted, kept so the server's decoded
  // frame size can be compared against it rather than assumed equal.
  cameraSize: null,
};

function show(kind, text) {
  els.message.textContent = text;
  els.message.className = "show " + kind;
}

function set(id, text) {
  const node = els[id];
  if (node.textContent !== text) node.textContent = text;
}

// --- Secure context --------------------------------------------------

// Browsers expose camera capture only in a secure context. A phone
// loading this page over plain HTTP from a LAN address does not get a
// denied permission -- navigator.mediaDevices is simply absent, which
// is a confusing symptom for a cause that has nothing to do with
// permissions. Say so explicitly.
function cameraApiAvailable() {
  return Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

if (!cameraApiAvailable()) {
  els.start.disabled = true;
  // The port comes from the URL the phone actually opened rather than
  // from a constant, so the adb line stays correct when the server is
  // started on a non-default --port.
  const port = location.port || (location.protocol === "https:" ? "443" : "80");

  // Report what the browser actually thinks, rather than assuming.
  // Plain HTTP and "HTTPS whose certificate this browser will not
  // accept for a secure context" are different problems with different
  // fixes, and they are indistinguishable without these two values.
  const diagnosis =
    location.protocol === "https:"
      ? "The page is already HTTPS, so this is the certificate: some " +
        "browsers refuse to treat a self-signed origin as secure even " +
        "after you click through the warning. The USB route below " +
        "avoids certificates entirely and is the reliable fix."
      : "The page was loaded over plain HTTP, which is never a secure " +
        "context except on localhost.";

  show(
    "error",
    "No camera API on this page.\n\n" +
      `origin: ${location.origin}\n` +
      `protocol: ${location.protocol}\n` +
      `isSecureContext: ${window.isSecureContext}\n\n` +
      diagnosis +
      "\n\nTwo ways to fix it:\n" +
      `  1. USB, no certificate — run \`adb reverse tcp:${port} ` +
      `tcp:${port}\` on the PC, then open http://localhost:${port} here. ` +
      "localhost is always a secure context.\n" +
      "  2. HTTPS — start the server with --tls and accept the " +
      "certificate warning once. Does not work on every browser."
  );
}

// --- Connection ------------------------------------------------------

// Every link and socket on this page is built from where the page was
// loaded, not hardcoded: the address the phone opened is by definition
// one it can reach, and the token rides along on the same URL.
function currentToken() {
  return new URLSearchParams(location.search).get("token");
}

function sameOriginUrl(path) {
  const url = new URL(path, location.href);
  const token = currentToken();
  if (token) url.searchParams.set("token", token);
  return url;
}

function socketUrl() {
  const url = sameOriginUrl("ws/frames");
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

// Carrying the token matters: without it the link 401s, and it is
// guarded exactly when the server is reachable from this phone.
els["marker-sheet"].href = sameOriginUrl("markers").toString();

// --- Marker source ---------------------------------------------------

// Printed tags, or tags drawn on the display. Selecting on-screen
// markers starts the overlay on the PC; selecting printed stops it.
// Available before streaming starts, since it is the sort of thing you
// would want to set first.

function showMarkerSource(state) {
  const active = state && state.source;
  els["source-printed"].setAttribute("aria-pressed", String(active === "printed"));
  els["source-screen"].setAttribute("aria-pressed", String(active === "screen"));
}

async function loadMarkerSource() {
  try {
    const response = await fetch(sameOriginUrl("markers/source"));
    if (response.ok) showMarkerSource(await response.json());
  } catch {
    // Not worth a message: the page is useful without this, and any
    // real connection problem will surface when streaming starts.
  }
}

async function selectMarkerSource(source) {
  // Starting the overlay means launching a process and waiting for it
  // to report its geometry, which is seconds rather than milliseconds.
  // Both buttons are held during it -- two overlapping requests would
  // race -- so the pressed one has to say it is working, or the control
  // reads as simply broken.
  const pressed = source === "screen" ? "source-screen" : "source-printed";
  const label = els[pressed].textContent;
  for (const id of ["source-printed", "source-screen"]) els[id].disabled = true;
  els[pressed].textContent = "…";
  try {
    const response = await fetch(sameOriginUrl("markers/source"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
    });
    const state = await response.json();
    // The server reports what is *actually* active, which after a
    // failure is still the old source. Render that, not what was asked
    // for -- a control showing "on-screen" while nothing is on the
    // display would leave the solver using a layout for tags that do
    // not exist, and present as terrible aim with no visible cause.
    showMarkerSource(state);
    if (!response.ok) {
      show("error", state.detail || "could not change the marker source");
    } else if (source === "screen") {
      const size = state.geometry ? state.geometry.screen_px.join("x") : "";
      show("info", `On-screen markers active${size ? ` on ${size}` : ""}.`);
    } else {
      show("info", "Printed markers active.");
    }
  } catch (error) {
    show("error", `Could not change the marker source: ${error.message}`);
  } finally {
    els[pressed].textContent = label;
    for (const id of ["source-printed", "source-screen"]) els[id].disabled = false;
  }
}

els["source-printed"].addEventListener("click", () => selectMarkerSource("printed"));
els["source-screen"].addEventListener("click", () => selectMarkerSource("screen"));
loadMarkerSource();

// --- Viewfinder ------------------------------------------------------

// Two layers over one canvas. The reticle marks the aim point and is
// drawn from this page's own geometry: solve.py takes the *image
// centre* through the inverse homography, so the centre of the element
// showing that image is the aim point by definition. Nothing the server
// says can make it more or less true, which is why it survives a
// no-marker frame and a dropped connection.
//
// The debug geometry on top comes from the server and describes a frame
// captured a round trip ago. It is drawn newest-only and never held
// over: last frame's outline on this frame's picture would be exactly
// the confident, wrong picture this view exists to prevent.

const overlayCtx = els.overlay.getContext("2d");

// Read from :root so the drawing and the numbers beside it are coloured
// from one place.
const palette = getComputedStyle(document.documentElement);
const COLOUR = {
  mapped: palette.getPropertyValue("--ok").trim() || "#6fcf6f",
  ignored: palette.getPropertyValue("--warn").trim() || "#e0b34a",
  quad: palette.getPropertyValue("--quad").trim() || "#7fb0f0",
  aim: palette.getPropertyValue("--aim").trim() || "#ff5cf0",
};

function pixelRatio() {
  return window.devicePixelRatio || 1;
}

function sizeOverlay() {
  const ratio = pixelRatio();
  const width = Math.round(els.overlay.clientWidth * ratio);
  const height = Math.round(els.overlay.clientHeight * ratio);
  // Assigning either dimension clears the canvas, so only do it when it
  // actually changed.
  if (els.overlay.width !== width || els.overlay.height !== height) {
    els.overlay.width = width;
    els.overlay.height = height;
  }
}

// The rectangle the video actually occupies inside its element. This is
// the fit `object-fit: contain` performs and does not expose: the
// browser letterboxes to preserve aspect, and every drawn coordinate
// has to land in the letterboxed content, not the element box.
function contentRect() {
  const video = els.preview;
  if (!video.videoWidth || !video.videoHeight) return null;
  const boxWidth = els.overlay.width;
  const boxHeight = els.overlay.height;
  const scale = Math.min(boxWidth / video.videoWidth, boxHeight / video.videoHeight);
  const width = video.videoWidth * scale;
  const height = video.videoHeight * scale;
  return {
    x: (boxWidth - width) / 2,
    y: (boxHeight - height) / 2,
    width,
    height,
  };
}

// Server image pixels -> canvas pixels. Scaled by the image size the
// server reports rather than the one the camera granted, so the two
// disagreeing displaces nothing silently -- the mismatch is reported as
// a number instead.
function toCanvas(rect, geometry, point) {
  const [imageWidth, imageHeight] = geometry.image_px;
  return [
    rect.x + (point[0] / imageWidth) * rect.width,
    rect.y + (point[1] / imageHeight) * rect.height,
  ];
}

// Everything is stroked twice: a dark under-stroke, then the colour.
// The overlay sits on whatever the camera happens to see, which can be
// any brightness, and a single-colour line disappears against half of
// it.
function strokeTwice(path, colour, ratio) {
  overlayCtx.lineJoin = "round";
  overlayCtx.lineCap = "round";
  overlayCtx.strokeStyle = "rgba(0, 0, 0, 0.65)";
  overlayCtx.lineWidth = 4 * ratio;
  overlayCtx.stroke(path);
  overlayCtx.strokeStyle = colour;
  overlayCtx.lineWidth = 1.5 * ratio;
  overlayCtx.stroke(path);
}

function drawReticle(rect) {
  const ratio = pixelRatio();
  const x = rect.x + rect.width / 2;
  const y = rect.y + rect.height / 2;
  const radius = 9 * ratio;
  const gap = 4 * ratio;
  const arm = 9 * ratio;

  const path = new Path2D();
  // Gapped arms: the centre pixel itself is left uncovered, so the
  // emitted cursor mark is visible exactly where it matters most --
  // sitting under the reticle, or not.
  path.moveTo(x - gap - arm, y);
  path.lineTo(x - gap, y);
  path.moveTo(x + gap, y);
  path.lineTo(x + gap + arm, y);
  path.moveTo(x, y - gap - arm);
  path.lineTo(x, y - gap);
  path.moveTo(x, y + gap);
  path.lineTo(x, y + gap + arm);
  path.moveTo(x + radius, y);
  path.arc(x, y, radius, 0, Math.PI * 2);

  strokeTwice(path, "#ffffff", ratio);
}

function quadPath(rect, geometry, corners) {
  const path = new Path2D();
  corners.forEach((corner, index) => {
    const [x, y] = toCanvas(rect, geometry, corner);
    if (index === 0) path.moveTo(x, y);
    else path.lineTo(x, y);
  });
  path.closePath();
  return path;
}

function drawGeometry(rect, geometry) {
  const ratio = pixelRatio();

  for (const marker of geometry.markers) {
    // Outlined, never filled: the whole job of this drawing is to be
    // compared against the image beneath it.
    strokeTwice(
      quadPath(rect, geometry, marker.corners_px),
      marker.mapped ? COLOUR.mapped : COLOUR.ignored,
      ratio
    );
    const [x, y] = toCanvas(rect, geometry, marker.corners_px[0]);
    overlayCtx.font = `${11 * ratio}px system-ui, sans-serif`;
    overlayCtx.textBaseline = "bottom";
    overlayCtx.lineWidth = 3 * ratio;
    overlayCtx.strokeStyle = "rgba(0, 0, 0, 0.65)";
    overlayCtx.strokeText(String(marker.id), x, y - 2 * ratio);
    overlayCtx.fillStyle = marker.mapped ? COLOUR.mapped : COLOUR.ignored;
    overlayCtx.fillText(String(marker.id), x, y - 2 * ratio);
  }

  if (geometry.screen_quad_px) {
    strokeTwice(
      quadPath(rect, geometry, geometry.screen_quad_px),
      COLOUR.quad,
      ratio
    );
  }

  if (geometry.cursor_px) {
    // Where the position that was actually emitted lands back in the
    // image. It should sit under the reticle; a visible gap is the
    // emitted cursor disagreeing with the solve.
    const [x, y] = toCanvas(rect, geometry, geometry.cursor_px);
    const path = new Path2D();
    path.moveTo(x + 4 * ratio, y);
    path.arc(x, y, 4 * ratio, 0, Math.PI * 2);
    strokeTwice(path, COLOUR.aim, ratio);
    overlayCtx.fillStyle = COLOUR.aim;
    overlayCtx.fill(path);
  }
}

function drawOverlay() {
  sizeOverlay();
  overlayCtx.clearRect(0, 0, els.overlay.width, els.overlay.height);
  if (!state.stream) return;
  const rect = contentRect();
  if (!rect) return;
  drawReticle(rect);
  if (state.debug && state.geometry) drawGeometry(rect, state.geometry);
}

window.addEventListener("resize", drawOverlay);
els.preview.addEventListener("loadedmetadata", drawOverlay);

// --- Debug overlay control -------------------------------------------

function showDebugRows(on) {
  for (const id of ["row-decoded", "row-reprojection", "row-lag"]) {
    els[id].classList.toggle("show", on);
  }
}

function showDebug(enabled) {
  state.debug = enabled;
  els["debug-on"].setAttribute("aria-pressed", String(enabled));
  els["debug-off"].setAttribute("aria-pressed", String(!enabled));
  showDebugRows(enabled);
  if (!enabled) state.geometry = null;
  drawOverlay();
}

async function loadDebug() {
  try {
    const response = await fetch(sameOriginUrl("debug"));
    if (response.ok) showDebug((await response.json()).enabled);
  } catch {
    // The page works without it; a real connection problem will show
    // itself when streaming starts.
  }
}

function selectDebug(enabled) {
  showDebug(enabled);
  // Told to the server rather than only to the socket: the setting has
  // to survive a reload, and it has to be settable before there is a
  // socket at all. A running session still takes it over the socket,
  // which is what keeps one phone's overlay off another phone's frames.
  if (state.socket) send(JSON.stringify({ type: "debug", enabled }));
  fetch(sameOriginUrl("debug"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  }).catch(() => {});
  if (enabled) {
    show(
      "info",
      "Overlay on. It describes a frame from one round trip ago, so it " +
        "trails the picture while you sweep -- judge alignment with the " +
        "camera held still. The screen outline should hug the panel, and " +
        "the cursor dot should sit under the reticle."
    );
  }
}

els["debug-on"].addEventListener("click", () => selectDebug(true));
els["debug-off"].addEventListener("click", () => selectDebug(false));
loadDebug();

function showGeometryStats(geometry, roundTrip) {
  if (!geometry) {
    set("stat-decoded", "—");
    set("stat-reprojection", "—");
    set("stat-lag", roundTrip === null ? "—" : `${roundTrip.toFixed(0)} ms`);
    return;
  }

  // The size the server decoded, next to the size the camera granted.
  // A browser may hand over a different resolution than was asked for,
  // and a silent disagreement here would displace every drawn shape.
  const decoded = geometry.image_px.join("x");
  const granted = state.cameraSize;
  set(
    "stat-decoded",
    granted && granted !== decoded ? `${decoded} ≠ camera ${granted}` : decoded
  );

  set(
    "stat-reprojection",
    geometry.reprojection_max_px === null
      ? "—"
      : `${geometry.reprojection_max_px} px max, ` +
        `${geometry.reprojection_mean_px} mean`
  );

  // How stale the drawing is: it describes the frame whose round trip
  // just completed, so that round trip is its age at the moment it is
  // drawn.
  set("stat-lag", roundTrip === null ? "—" : `${roundTrip.toFixed(0)} ms`);
}

// Neither getUserMedia nor a WebSocket handshake is guaranteed to
// settle. A permission dialog nobody answers, a server that accepted
// the TCP connection and then went quiet -- both leave a promise
// pending for ever, and the Start button stuck on "Starting…" with no
// way to tell what it is waiting for.
function withTimeout(promise, ms, message) {
  let timer;
  const expiry = new Promise((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([promise, expiry]).finally(() => clearTimeout(timer));
}

// Generous: a permission prompt is answered by a human.
const CAMERA_TIMEOUT_MS = 30000;
// Tight: this is a handshake against a server on the same network, or
// the same machine over adb.
const SOCKET_TIMEOUT_MS = 8000;

function connect() {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(socketUrl());
    socket.binaryType = "arraybuffer";
    socket.onopen = () => {
      set("stat-connection", "connected");
      resolve(socket);
    };
    socket.onerror = () => reject(new Error("could not connect to the server"));
    socket.onclose = (event) => {
      set("stat-connection", `closed (${event.code})`);
      stop();
      if (event.code === 1008) {
        show("error", "Rejected: missing or invalid token. Reopen the exact URL the server printed.");
      } else if (event.code !== 1000) {
        show("warn", `Connection closed (code ${event.code}).`);
      }
    };
    socket.onmessage = (event) => onTelemetry(event.data);
  });
}

// The server acknowledges every frame, so at 20fps this arrives twenty
// times a second. Rendering all of it spends the main thread on DOM
// mutation no eye can follow, and starves the capture loop -- which is
// what made the page unresponsive while streaming. These numbers are
// read by a human; a few updates a second is plenty.
const RENDER_INTERVAL_MS = 200;
const RTT_REPORT_INTERVAL_MS = 1000;

let lastRender = 0;
let lastRttReport = 0;
let lastRoundTrip = null;

function onTelemetry(data) {
  let stats;
  try {
    stats = JSON.parse(data);
  } catch {
    return;
  }
  if (stats.type !== "stats") return;

  const now = performance.now();

  if (typeof stats.client_ms === "number") {
    lastRoundTrip = now - stats.client_ms;
    // The server cannot compute this itself -- only this clock can be
    // compared against itself -- so report what we measured. Once a
    // second: it is a smoothed reading rather than a per-frame one, and
    // every report is another send competing with the frames.
    if (now - lastRttReport >= RTT_REPORT_INTERVAL_MS) {
      lastRttReport = now;
      send(JSON.stringify({ type: "rtt", ms: lastRoundTrip }));
    }
  }

  // Drawn every frame, deliberately: the reticle marks where *this*
  // frame was solved, so throttling it would show it lagging the image.
  // Present only while this session has debug enabled; present and null
  // means "enabled, and this frame had nothing to show", which clears
  // the drawing rather than leaving the previous frame's on screen.
  if ("debug" in stats) {
    state.geometry = stats.debug;
    drawOverlay();
  }

  if (now - lastRender < RENDER_INTERVAL_MS) return;
  lastRender = now;

  if ("debug" in stats) showGeometryStats(stats.debug, lastRoundTrip);
  if (lastRoundTrip !== null) set("stat-rtt", `${lastRoundTrip.toFixed(0)} ms`);
  set("stat-markers", `${stats.markers_detected} (${stats.outcome})`);
  set(
    "stat-aim",
    stats.x === null
      ? "—"
      : `${stats.x.toFixed(3)}, ${stats.y.toFixed(3)}` +
        (stats.inside_hull === false ? "  extrapolated" : "")
  );
  set("stat-frames", `${stats.received} / ${stats.processed}`);
  set("stat-lost", `${stats.dropped} / ${stats.failed}`);
  set("stat-timing", `${stats.decode_ms} / ${stats.solve_ms} ms`);
  set("stat-shots", String(stats.triggers));
}

function send(payload) {
  if (state.socket && state.socket.readyState === WebSocket.OPEN) {
    state.socket.send(payload);
  }
}

// --- Camera ----------------------------------------------------------

async function openCamera() {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: {
      facingMode: { ideal: "environment" },
      width: { ideal: CONFIG.width },
      height: { ideal: CONFIG.height },
    },
    audio: false,
  });

  // A browser may substitute a different camera or resolution than the
  // one asked for. Detection range is governed by pixels across a
  // marker, so a silent downgrade changes what the system can do --
  // report what was actually granted, not what was requested.
  const track = stream.getVideoTracks()[0];
  const settings = track.getSettings();
  state.cameraSize = `${settings.width}x${settings.height}`;
  set(
    "stat-camera",
    `${settings.width}x${settings.height} ${settings.facingMode || "unknown facing"}`
  );

  await pinExposure(track);
  return stream;
}

async function pinExposure(track) {
  const capabilities = track.getCapabilities ? track.getCapabilities() : {};
  if (!capabilities.exposureMode || !capabilities.exposureMode.includes("manual")) {
    set("stat-exposure", "auto (not adjustable)");
    show(
      "warn",
      "This device does not expose manual exposure control. Auto-exposure " +
        "will chase the bright panel and underexpose the markers. Keep some " +
        "ambient light on the bezel and expect shorter detection range."
    );
    return;
  }
  try {
    const constraints = { exposureMode: "manual" };
    if (capabilities.exposureTime) {
      constraints.exposureTime = Math.max(
        capabilities.exposureTime.min,
        Math.min(CONFIG.exposureTime, capabilities.exposureTime.max)
      );
    }
    await track.applyConstraints({ advanced: [constraints] });
    const applied = track.getSettings().exposureTime;
    set("stat-exposure", applied ? `pinned (${applied})` : "pinned");
  } catch (error) {
    set("stat-exposure", "auto (pinning refused)");
    show("warn", `Exposure could not be pinned: ${error.message}`);
  }
}

// --- Capture loop ----------------------------------------------------

const canvas = document.createElement("canvas");
const context = canvas.getContext("2d", { willReadFrequently: false });

async function captureAndSend() {
  if (state.sending) return;
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) return;

  if (state.socket.bufferedAmount > CONFIG.maxBufferedBytes) {
    state.skipped += 1;
    set("stat-skipped", String(state.skipped));
    return;
  }

  const video = els.preview;
  if (!video.videoWidth) return;

  state.sending = true;
  try {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    context.drawImage(video, 0, 0);

    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", CONFIG.jpegQuality)
    );
    if (!blob) return;

    const jpeg = new Uint8Array(await blob.arrayBuffer());
    const message = new Uint8Array(CONFIG.headerBytes + jpeg.length);
    new DataView(message.buffer).setFloat64(0, performance.now(), true);
    message.set(jpeg, CONFIG.headerBytes);
    send(message.buffer);
  } catch (error) {
    show("error", `Capture failed: ${error.message}`);
  } finally {
    state.sending = false;
  }
}

function stop() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  if (state.stream) state.stream.getTracks().forEach((track) => track.stop());
  state.stream = null;
  state.socket = null;
  state.geometry = null;
  els.start.disabled = false;
  els.start.textContent = "Start streaming";
  els.trigger.disabled = true;
  // The camera is gone, so there is no longer an image for the reticle
  // to mark a point on. The debug toggle keeps its setting.
  drawOverlay();
}

els.start.addEventListener("click", async () => {
  // The button is the stop button while streaming. Without this there
  // is no way to release the camera or the socket short of reloading
  // the page.
  if (state.timer) {
    stop();
    show("info", "Stopped. The camera is released.");
    return;
  }

  // Starting can be cancelled. Without this the only way out of a start
  // that is waiting on something is to reload the page.
  if (state.starting) {
    state.starting = false;
    stop();
    set("stat-connection", "cancelled");
    show("warn", "Start cancelled.");
    return;
  }

  els.start.textContent = "Starting… (tap to cancel)";
  state.starting = true;
  try {
    set("stat-connection", "waiting for camera permission");
    state.stream = await withTimeout(
      openCamera(),
      CAMERA_TIMEOUT_MS,
      "the camera did not respond. If a permission prompt appeared, " +
        "answer it and press Start again; if the camera is in use by " +
        "another app, close it first."
    );
    // Cancelling does not abort getUserMedia, so a stream can still
    // arrive after the operator gave up. Release it, or the camera
    // stays live with nothing using it.
    if (!state.starting) {
      state.stream.getTracks().forEach((track) => track.stop());
      state.stream = null;
      return;
    }
    set("stat-connection", "camera ready");
    els.preview.srcObject = state.stream;
    await els.preview.play();
    // Before the socket: the reticle is a property of the preview, not
    // of the connection, and it should be there the moment there is an
    // image to mark.
    drawOverlay();
    set("stat-connection", "opening socket");
    state.socket = await withTimeout(
      connect(),
      SOCKET_TIMEOUT_MS,
      "the server did not accept the connection. Check it is still " +
        "running, and that this page's address still reaches it."
    );
    // No re-assert needed: the server remembers the setting and a new
    // session inherits it at connect.
    if (!state.starting) {
      state.socket.close();
      stop();
      return;
    }
    state.timer = setInterval(captureAndSend, 1000 / CONFIG.targetFps);
    els.start.disabled = false;
    els.start.textContent = "Stop streaming";
    els.trigger.disabled = false;
    show("info", "Streaming. Aim at the display; the cursor follows the frame centre.");
  } catch (error) {
    stop();
    set("stat-connection", "failed");
    show("error", `${error.name || "Error"}: ${error.message}`);
  } finally {
    state.starting = false;
  }
});

// pointerdown rather than click: click waits for pointerup and, on
// touch, the browser's tap-recognition delay -- a trigger should fire
// the instant it's pressed. preventDefault plus touch-action: none (in
// CSS) stops the browser from treating the press as the start of a
// scroll/zoom gesture instead of a tap on the button.
els.trigger.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  send(JSON.stringify({ type: "trigger" }));
});
