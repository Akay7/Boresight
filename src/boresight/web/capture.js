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
  "preview", "start", "trigger", "message", "marker-sheet",
  "stat-connection", "stat-camera", "stat-exposure", "stat-rtt",
  "stat-markers", "stat-aim", "stat-frames", "stat-lost", "stat-skipped",
  "stat-timing", "stat-shots",
]) {
  els[id] = document.getElementById(id);
}

const state = { socket: null, stream: null, timer: null, sending: false, skipped: 0 };

function show(kind, text) {
  els.message.textContent = text;
  els.message.className = "show " + kind;
}

function set(id, text) {
  els[id].textContent = text;
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
  show(
    "error",
    "No camera API on this page.\n\n" +
      `This page was loaded from ${location.origin}, which the browser ` +
      "does not treat as a secure context, so it exposes no camera at " +
      "all. This is not a permission you can grant.\n\n" +
      "Two ways to fix it:\n" +
      "  1. Serve over HTTPS — start the server with --tls and accept " +
      "the certificate warning once.\n" +
      `  2. Connect the phone by USB and run \`adb reverse tcp:${port} ` +
      `tcp:${port}\`, then open http://localhost:${port} — localhost is a ` +
      "secure context, needs no certificate, and removes the Wi-Fi hop."
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

function onTelemetry(data) {
  let stats;
  try {
    stats = JSON.parse(data);
  } catch {
    return;
  }
  if (stats.type !== "stats") return;

  if (typeof stats.client_ms === "number") {
    const rtt = performance.now() - stats.client_ms;
    set("stat-rtt", `${rtt.toFixed(0)} ms`);
    // The server cannot compute this itself -- only this clock can be
    // compared against itself -- so report what we measured.
    send(JSON.stringify({ type: "rtt", ms: rtt }));
  }

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
  els.start.disabled = false;
  els.start.textContent = "Start streaming";
  els.trigger.disabled = true;
}

els.start.addEventListener("click", async () => {
  els.start.disabled = true;
  els.start.textContent = "Starting…";
  try {
    set("stat-connection", "connecting");
    state.stream = await openCamera();
    els.preview.srcObject = state.stream;
    await els.preview.play();
    state.socket = await connect();
    state.timer = setInterval(captureAndSend, 1000 / CONFIG.targetFps);
    els.start.textContent = "Streaming";
    els.trigger.disabled = false;
    show("info", "Streaming. Aim at the display; the cursor follows the frame centre.");
  } catch (error) {
    stop();
    show("error", `${error.name || "Error"}: ${error.message}`);
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
