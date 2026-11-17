"""The ESP32-CAM firmware, booted in QEMU, against the real server.

Everything above the camera sensor and the radio is the firmware that
runs on a board: the WebSocket client, the fragmented frame send,
`hello`, `rtt`, the debouncer, trigger press and release, reconnection,
token refusal, and setup mode's page, checks and stored settings. The
emulator build swaps in three things only -- recorded frames of the
Blender scene rendered as the ESP32-CAM sees it
(tests/fixtures/esp32cam_video) for the sensor, QEMU's emulated Ethernet
for Wi-Fi, and console commands for reading the trigger pin -- so what
fails here fails on a board too.

Opt-in, because it needs Docker, a built emulator image and a couple of
minutes:

    firmware/boresight-cam/tools/idf.sh emulator build
    BORESIGHT_EMULATOR_TESTS=1 uv run pytest tests/test_firmware_emulator.py

The server is the real app on 127.0.0.1:7391 with a recording cursor
backend, so nothing moves the mouse and nothing is reachable from
elsewhere. One emulator boot serves the whole module; the tests run in
file order. Token refusal comes near the end because the device then
waits 30 seconds before trying again, and setup mode last, since what it
stores outlives the restart (for this run only: the image is merged
afresh on every boot).

Asserts on events and counts only. Emulated time is not real time, so
frame rates and latencies measured here mean nothing.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import pytest
import uvicorn

from boresight.inject import FakeCursorBackend
from boresight.marker_map import load_marker_map
from boresight.netaccess import ServerConfig
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline
from boresight.server import create_app

REPO = Path(__file__).parents[1]
FIRMWARE = REPO / "firmware" / "boresight-cam"
RUN_EMULATOR = FIRMWARE / "tools" / "run-emulator.sh"
EMULATOR_IMAGE = FIRMWARE / "build-emulator" / "flash_args"
# The application images a firmware upload takes.
EMULATOR_APP = FIRMWARE / "build-emulator" / "boresight-cam.bin"
DEVICE_APP = FIRMWARE / "build" / "boresight-cam.bin"
DEVICE_FIXTURE = REPO / "tests" / "fixtures" / "esp32cam_video"

# Fixed by sdkconfig.emulator.
PORT = 7391
TOKEN = "emulator-token"
# Must match main/CMakeLists.txt and main/camera_fake.c.
EMBEDDED_FRAMES = 8

RUNTIME = os.environ.get("CONTAINER", "docker")


def _skip_reason() -> str | None:
    if os.environ.get("BORESIGHT_EMULATOR_TESTS") != "1":
        return (
            "boots the firmware in QEMU: set BORESIGHT_EMULATOR_TESTS=1 "
            "(needs Docker and `firmware/boresight-cam/tools/idf.sh emulator build`)"
        )
    if shutil.which(RUNTIME) is None:
        return f"no container runtime ({RUNTIME}) on PATH"
    if subprocess.run([RUNTIME, "info"], capture_output=True).returncode != 0:
        return f"{RUNTIME} is not answering"
    if not EMULATOR_IMAGE.exists():
        return (
            "no emulator image: run `firmware/boresight-cam/tools/idf.sh "
            "emulator build`"
        )
    return None


_reason = _skip_reason()
pytestmark = [
    pytest.mark.emulator,
    # The harness runs the server under real uvicorn, which picks uvloop,
    # and uvloop's run_in_executor calls asyncio.iscoroutinefunction --
    # deprecated in Python 3.14. The suite's config turns deprecations
    # into errors, which here would fail every frame inside the server.
    # Not this project's code; filtered for this module only, rather
    # than swapping the harness onto a different event loop than the one
    # the server runs on.
    pytest.mark.filterwarnings(
        "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning"
    ),
] + ([pytest.mark.skip(reason=_reason)] if _reason else [])


# --- The server ----------------------------------------------------------


class _RefusalCounter(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage().startswith("frame socket refused"):
            self.count += 1


class LoopbackServer:
    """The real app on loopback, restartable, with one backend throughout.

    The backend outlives restarts so presses are counted across them --
    which is how a press made while the server was down would show up if
    it were ever replayed.
    """

    def __init__(self) -> None:
        self.backend = FakeCursorBackend()
        self.refusals = _RefusalCounter()
        logging.getLogger("boresight").addHandler(self.refusals)
        logging.getLogger("boresight").setLevel(logging.INFO)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        # The token the running server takes; what /sessions is asked with.
        self.token = TOKEN

    def start(self, token: str = TOKEN) -> None:
        self.token = token
        app = create_app(
            backend_factory=lambda: self.backend,
            config=ServerConfig(host="127.0.0.1", port=PORT, token=token),
        )
        self._server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=PORT,
                log_level="warning",
                # With a socket open, a graceful shutdown otherwise waits
                # for the client, which keeps streaming -- and the device
                # never sees the server go away.
                timeout_graceful_shutdown=1,
            )
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.05)

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
            self._thread.join(timeout=10)
            assert not self._thread.is_alive(), "server did not stop"
            self._server = None

    def sessions(self) -> list[dict]:
        url = f"http://127.0.0.1:{PORT}/sessions?token={self.token}"
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.load(response)["sessions"]

    def device_session(self) -> dict | None:
        found = [s for s in self.sessions() if s["client"] == "esp32-cam"]
        return found[0] if found else None


# --- The emulator --------------------------------------------------------


class Emulator:
    """QEMU running the emulator image, with its console as lines."""

    def __init__(self) -> None:
        self.name = f"boresight-emulator-{uuid.uuid4().hex[:8]}"
        # Where run-emulator.sh forwards the setup page, on loopback.
        self.setup_port = _free_loopback_port()
        self.lines: list[str] = []
        self._changed = threading.Condition()
        self._process = subprocess.Popen(
            [str(RUN_EMULATOR)],
            env={
                **os.environ,
                "BORESIGHT_EMULATOR_NAME": self.name,
                "BORESIGHT_EMULATOR_SETUP_PORT": str(self.setup_port),
            },
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self._process.stdout:
            with self._changed:
                self.lines.append(line.rstrip())
                self._changed.notify_all()

    def mark(self) -> int:
        with self._changed:
            return len(self.lines)

    def wait_for(self, pattern: str, timeout: float, after: int = 0) -> str:
        """The first console line from `after` on matching `pattern`."""
        regex = re.compile(pattern)
        deadline = time.monotonic() + timeout
        with self._changed:
            while True:
                for line in self.lines[after:]:
                    if regex.search(line):
                        return line
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    tail = "\n".join(self.lines[-30:])
                    raise AssertionError(
                        f"no console line matching {pattern!r} in {timeout}s; "
                        f"last lines:\n{tail}"
                    )
                self._changed.wait(remaining)

    def send(self, command: str) -> None:
        self._process.stdin.write(command + "\n")
        self._process.stdin.flush()

    def close(self) -> None:
        subprocess.run([RUNTIME, "rm", "-f", self.name], capture_output=True)
        self._process.kill()
        self._process.wait(timeout=10)


def _free_loopback_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _setup_page(
    emulator: Emulator, path: str = "/", form: dict | None = None
) -> tuple[int, str]:
    """GET (or with `form`, POST) the device's setup page: status and body."""
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    request = urllib.request.Request(
        f"http://127.0.0.1:{emulator.setup_port}{path}", data=data
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def _lan_address() -> str | None:
    """This machine's address on its network, if it has one. Nothing is
    sent: connecting a UDP socket only picks the route."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
        except OSError:
            return None
        address = probe.getsockname()[0]
    return None if address.startswith("127.") else address


def _wait_until(condition, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.1)


@pytest.fixture(scope="module")
def server():
    server = LoopbackServer()
    server.start()
    yield server
    server.stop()
    logging.getLogger("boresight").removeHandler(server.refusals)


@pytest.fixture(scope="module")
def emulator(server: LoopbackServer):
    emulator = Emulator()
    try:
        emulator.wait_for(r"state: streaming", timeout=120)
        yield emulator
    finally:
        emulator.close()


@pytest.fixture(scope="module")
def replayed_positions() -> set[tuple[float, float]]:
    """Every position the embedded frames solve to, rounded as the wire is."""
    manifest = json.loads((DEVICE_FIXTURE / "manifest.json").read_text())
    pipeline = AimPipeline(load_marker_map(DEFAULT_CONFIG_PATH), FakeCursorBackend())
    import cv2

    positions = set()
    for entry in manifest["frames"][:EMBEDDED_FRAMES]:
        frame = cv2.imread(str(DEVICE_FIXTURE / entry["file"]), cv2.IMREAD_COLOR)
        result = pipeline.process_frame(frame)
        if result.position is not None:
            positions.add((round(result.position[0], 5), round(result.position[1], 5)))
    return positions


# --- The checks ----------------------------------------------------------


def test_the_device_identifies_itself_and_streams(
    server: LoopbackServer, emulator: Emulator, replayed_positions: set
) -> None:
    _wait_until(
        lambda: (
            (server.device_session() or {}).get("stats", {}).get("processed", 0)
            >= 2 * EMBEDDED_FRAMES
        ),
        timeout=60,
        what="two passes over the embedded frames",
    )
    session = server.device_session()
    assert session["version"].endswith("+emulator")
    manifest = json.loads((DEVICE_FIXTURE / "manifest.json").read_text())
    assert session["frame_size"] == [int(side) for side in manifest["image_size"]]
    assert session["stats"]["failed"] == 0
    assert session["stats"]["round_trip_ms"] > 0

    # Positions arrive one at a time through /sessions; sample for a
    # while. Every one must be a position the same frames replay to --
    # the transport, fragmented as the firmware sends it, changed nothing.
    seen = set()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        stats = server.device_session()["stats"]
        if stats["x"] is not None:
            seen.add((stats["x"], stats["y"]))
        time.sleep(0.05)
    assert seen, "no solved position was reported"
    assert seen <= replayed_positions, seen - replayed_positions
    assert len(seen) >= 2, "the stream should move through several frames"


def test_trigger_press_and_release_hold_the_button(
    server: LoopbackServer, emulator: Emulator
) -> None:
    presses = server.backend.presses
    triggers = server.device_session()["stats"]["triggers"]

    emulator.send("press")
    _wait_until(lambda: server.backend.held, timeout=10, what="the button held")
    assert server.backend.presses == presses + 1

    emulator.send("release")
    _wait_until(lambda: not server.backend.held, timeout=10, what="the button up")
    assert server.device_session()["stats"]["triggers"] > triggers


def test_the_device_reconnects_and_does_not_replay_a_press(
    server: LoopbackServer, emulator: Emulator
) -> None:
    mark = emulator.mark()
    server.stop()
    emulator.wait_for(r"state: (connecting|joining network)", timeout=30, after=mark)

    presses = server.backend.presses
    emulator.send("press")
    emulator.wait_for(r"pressed while disconnected: discarded", timeout=10, after=mark)
    emulator.send("release")

    server.start()
    emulator.wait_for(r"state: streaming", timeout=60, after=mark)
    _wait_until(
        lambda: server.device_session() is not None,
        timeout=10,
        what="the device session to reappear",
    )
    time.sleep(2)
    assert server.backend.presses == presses
    assert not server.backend.held


def test_a_refused_token_is_reported_and_not_hammered(
    server: LoopbackServer, emulator: Emulator
) -> None:
    mark = emulator.mark()
    server.stop()
    server.start(token="not-the-emulator-token")

    emulator.wait_for(r"server refused the connection \(HTTP 40[13]\)", 60, mark)
    emulator.wait_for(r"state: error", timeout=10, after=mark)
    refusals = server.refusals.count

    # The back-off is 30 s; anything under it proves there is no tight loop.
    time.sleep(25)
    assert server.refusals.count == refusals


def test_an_invalid_setup_submission_changes_nothing(
    server: LoopbackServer, emulator: Emulator
) -> None:
    mark = emulator.mark()
    emulator.send("setup")
    emulator.wait_for(r"restarting into setup mode", timeout=10, after=mark)
    emulator.wait_for(r"state: setup", timeout=60, after=mark)
    emulator.wait_for(r"setup page served on port 80", timeout=60, after=mark)

    _wait_until(
        lambda: _setup_page(emulator)[0] == 200, timeout=30, what="the setup page"
    )
    status, page = _setup_page(emulator)
    assert "Boresight camera" in page
    assert 'value="7391"' in page
    # The build's token is in effect and set, but never in the page.
    assert "emulator-token" not in page
    assert "Token <span" in page and "(set: leave empty to keep it)" in page

    status, page = _setup_page(
        emulator,
        "/save",
        {"ssid": "emulated", "port": "70000", "token": "would-be-new"},
    )
    assert status == 400
    assert "Nothing was saved" in page
    assert "A whole number from 1 to 65535." in page
    # What was typed comes back, so nothing has to be typed again.
    assert 'value="70000"' in page

    # Still in setup, with nothing stored.
    time.sleep(2)
    assert not any("leaving setup mode" in line for line in emulator.lines[mark:])
    status, page = _setup_page(emulator)
    assert status == 200 and 'value="7391"' in page

    # Any other path leads to the page, as a phone's sign-in check does.
    request = urllib.request.Request(
        f"http://127.0.0.1:{emulator.setup_port}/generate_204"
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(request, timeout=10)
        raise AssertionError("expected a redirect")
    except urllib.error.HTTPError as error:
        assert error.code == 302
        assert error.headers["Location"] == "/"

    # Forwarded to loopback only: not reachable on this machine's network
    # address.
    lan = _lan_address()
    if lan is not None:
        with socket.socket() as probe:
            probe.settimeout(2)
            assert probe.connect_ex((lan, emulator.setup_port)) != 0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def test_a_token_fixed_through_setup_mode_is_accepted(
    server: LoopbackServer, emulator: Emulator
) -> None:
    """The server still refuses the build's token (the previous test left
    it so): set the right one on the device and it streams again."""
    mark = emulator.mark()
    refusals = server.refusals.count

    status, page = _setup_page(
        emulator, "/save", {"ssid": "emulated", "token": "not-the-emulator-token"}
    )
    assert status == 200 and "Saved" in page
    emulator.wait_for(r"leaving setup mode: restarting", timeout=10, after=mark)
    emulator.wait_for(r"token set \(device\)", timeout=60, after=mark)
    emulator.wait_for(r"state: streaming", timeout=90, after=mark)

    _wait_until(
        lambda: server.device_session() is not None,
        timeout=10,
        what="the device session with the new token",
    )
    assert server.refusals.count == refusals


def _upload(emulator: Emulator, image: bytes) -> tuple[int, str]:
    """POST a firmware image to the setup page as the page's script does."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{emulator.setup_port}/update",
        data=image,
        headers={"Content-Type": "application/octet-stream"},
    )
    try:
        # Emulated Ethernet and flash: a megabyte takes a while.
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def test_a_board_image_and_a_cut_one_are_refused(
    server: LoopbackServer, emulator: Emulator
) -> None:
    if not DEVICE_APP.exists():
        pytest.skip("no board image: run `tools/idf.sh device build`")
    mark = emulator.mark()
    emulator.send("setup")
    emulator.wait_for(r"setup page served on port 80", timeout=90, after=mark)
    _wait_until(
        lambda: _setup_page(emulator)[0] == 200, timeout=30, what="the setup page"
    )
    status, page = _setup_page(emulator)
    assert "Running 0.1.0+emulator" in page

    status, page = _upload(emulator, DEVICE_APP.read_bytes())
    assert status == 400
    assert "this is the emulator, which takes only an emulator build" in page

    image = EMULATOR_APP.read_bytes()
    status, page = _upload(emulator, image[: len(image) // 2])
    assert status == 400
    assert "incomplete or damaged" in page

    status, page = _upload(emulator, b"not a firmware at all" * 50)
    assert status == 400
    assert "Not a firmware image" in page

    # Nothing was installed, and setup mode carries on.
    time.sleep(2)
    assert not any("leaving setup mode" in line for line in emulator.lines[mark:])
    assert _setup_page(emulator)[0] == 200


def test_a_firmware_uploaded_in_setup_mode_is_installed(
    server: LoopbackServer, emulator: Emulator
) -> None:
    """Still in setup mode from the previous test: install the emulator's
    own image, which goes to the other slot and keeps the stored token
    the server now insists on."""
    mark = emulator.mark()

    status, page = _upload(emulator, EMULATOR_APP.read_bytes())
    assert status == 200, page
    assert "Installed 0.1.0+emulator" in page

    emulator.wait_for(r"leaving setup mode: restarting", timeout=10, after=mark)
    emulator.wait_for(r"running 0\.1\.0\+emulator from ota_1", timeout=90, after=mark)
    emulator.wait_for(r"state: streaming", timeout=90, after=mark)
    emulator.wait_for(r"firmware 0\.1\.0\+emulator started: kept", 10, mark)
    _wait_until(
        lambda: server.device_session() is not None,
        timeout=10,
        what="the device session after the update",
    )
