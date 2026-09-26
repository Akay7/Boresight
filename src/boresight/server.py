from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import cv2
import numpy as np
from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.requests import HTTPConnection

from boresight.calibration import CalibrationCapture
from boresight.inject import CursorBackend, TriggerHold, default_cursor_backend
from boresight.layout_source import (
    DEFAULT_SPEC,
    LayoutSourceError,
    marker_map_factory,
)
from boresight.lens import DEFAULT_LENS_PATH, LensModel, LensStore, lens_key
from boresight.marker_map import MarkerMap, load_marker_map
from boresight.marker_source import (
    MarkerSource,
    MarkerSourceController,
    MarkerSourceError,
    SessionPipeline,
)
from boresight.markers import router as markers_router
from boresight.netaccess import (
    TOKEN_COOKIE_MAX_AGE_S,
    TOKEN_COOKIE_NAME,
    TOKEN_QUERY_PARAM,
    ServerConfig,
    certificate_fingerprint,
    install_log_redaction,
    origin_matches_host,
    presented_token,
    token_matches,
)
from boresight.pipeline import DEFAULT_CONFIG_PATH, FrameResult
from boresight.settings import LiveSettings, Settings, ViewPreferences
from boresight.settings_routes import (
    apply_rel_scale,
    restore_marker_source,
)
from boresight.settings_routes import router as settings_router
from boresight.shooter import CursorArbiter
from boresight.shot import AimHistory, Point, TriggerAction, TriggerQueue
from boresight.stream import (
    CaptureClock,
    FrameDecodeError,
    FrameSlot,
    SessionRegistry,
    SessionStats,
    unpack_frame,
)

# Inside the package, not at the repository root: the wheel target is
# `src/boresight`, so anything outside it is omitted from the built
# distribution -- a failure invisible to a test suite that always runs
# from a checkout, and a 404 for everyone who installs.
WEB_DIR = Path(__file__).parent / "web"
FRAME_SOCKET_PATH = "/ws/frames"

# WebSocket close code 1008 is "policy violation", the right status for
# credentials that were not acceptable. 1003 would claim the data was
# unsupported, which is not what happened.
WS_POLICY_VIOLATION = 1008

# 1011: the server hit a condition it could not continue from. Sent when
# frame processing itself has stopped, so the client reconnects rather
# than streaming into a session that will never answer.
WS_INTERNAL_ERROR = 1011

# A held trigger is let go once its session has sent nothing at all --
# no frame, no message -- for this long. Both clients stream frames many
# times a second while they are alive, so this is a stalled client (a
# backgrounded tab, a hung board, a half-open socket pings have not
# caught yet), not a long hold: holding fire while streaming is fine.
HOLD_IDLE_RELEASE_S = 2.0
HOLD_CHECK_INTERVAL_S = 0.5

# The longest a trigger naming a frame waits for that frame to be
# processed before it fires anyway, where the cursor is. A real frame
# resolves within one processing time (tens of milliseconds); this only
# bounds a shot naming a frame that will never come.
SHOT_WAIT_S = 0.25

# How often a live session reports itself. Frequent enough to answer
# "is the camera actually sending anything" at a glance, rare enough not
# to bury the log under a line per frame.
SESSION_LOG_INTERVAL_S = 5.0

# Longest client kind or version kept from a `hello`.
HELLO_FIELD_MAX = 64

logger = logging.getLogger("boresight")


class MoveRequest(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


@dataclass
class ViewSettings:
    """Client-facing preferences the server remembers.

    The marker source lives in `MarkerSourceController`; this holds what
    is left. Kept on the server so the phone can render the right button
    states the moment the page loads, and so a reload does not silently
    drop a setting the operator chose.

    This is the *default* a new session inherits, not the flag a running
    session uses. Those stay separate on purpose: one `AimPipeline`
    serves every connection, so a live session's debug flag has to be
    its own, or one phone's overlay would change what another phone's
    frames compute.
    """

    debug: bool = False


class DebugRequest(BaseModel):
    enabled: bool


class MarkerSourceRequest(BaseModel):
    # Constrained to the two known values, so an unknown source is a 422
    # rather than something that reaches the controller. Nothing from
    # this model ever becomes part of the overlay's command line.
    source: Literal["printed", "screen"]


class CalibrationRequest(BaseModel):
    # As `GET /sessions` lists it. Optional: with one session connected,
    # which is the usual case for a screenless camera, there is only one
    # thing it could mean.
    address: str | None = Field(default=None, max_length=128)
    action: Literal["start", "cancel"] = "start"


class OverlayMarginRequest(BaseModel):
    # Bounded well above any real panel height, so a garbled value is a
    # 422 rather than a margin that swallows the whole display; the
    # overlay's own `OverlayGeometryError` still covers a value that is
    # merely too large for a particular monitor.
    extra_margin_px: int = Field(ge=0, le=2000)


def get_cursor_backend(request: Request) -> CursorBackend:
    return request.app.state.cursor_backend


def _default_marker_map() -> MarkerMap:
    return load_marker_map(DEFAULT_CONFIG_PATH)


def create_app(
    backend_factory: Callable[[], CursorBackend] = default_cursor_backend,
    marker_map_factory: Callable[[], MarkerMap] = _default_marker_map,
    config: ServerConfig | None = None,
    display: int | None = None,
    overlay_extra_margin_px: int = 0,
    tracked_detection: bool = True,
    settings: LiveSettings | None = None,
    lens_store_factory: Callable[[], LensStore] = lambda: LensStore(None),
) -> FastAPI:
    """Build the FastAPI app.

    The factories are the seam tests use to substitute a
    `FakeCursorBackend` and a synthetic layout instead of opening a real
    uinput device and reading the shipped config. Both are called at
    startup rather than on first request, so a broken environment
    (no `/dev/uinput` permission, an unparseable layout) fails fast
    instead of failing on the first frame.

    `settings` is what `main()` resolved from flags, environment and the
    settings file; without it, defaults with `overlay_extra_margin_px`
    and nowhere to save.

    Lens calibrations default to an in-memory store, so an app built for
    a test never reads or writes the operator's `.boresight/lenses.json`;
    `main()` passes the persistent one.
    """
    config = config or ServerConfig()
    live_settings = settings or LiveSettings(
        Settings(view=ViewPreferences(overlay_extra_margin_px=overlay_extra_margin_px))
    )
    saved_view = live_settings.startup.view

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.cursor_backend = backend_factory()
        app.state.marker_map = marker_map_factory()
        app.state.markers = MarkerSourceController(
            app.state.cursor_backend,
            app.state.marker_map,
            display=display,
            overlay_extra_margin_px=saved_view.overlay_extra_margin_px,
            tracked_detection=tracked_detection,
            tuning=lambda: live_settings.tuning,
        )
        app.state.settings = ViewSettings(debug=saved_view.debug)
        app.state.live_settings = live_settings
        apply_rel_scale(app.state.cursor_backend, live_settings.tuning)
        restore_marker_source(app.state.markers, saved_view.marker_source)
        app.state.lenses = lens_store_factory()
        app.state.sessions = SessionRegistry()
        app.state.trigger_hold = TriggerHold(app.state.cursor_backend)
        app.state.arbiter = CursorArbiter(app.state.cursor_backend)
        try:
            yield
        finally:
            # Before the backend closes: an overlay outliving the server
            # cannot be dismissed by clicking, since it takes no input.
            app.state.markers.shutdown()
            close = getattr(app.state.cursor_backend, "close", None)
            if close is not None:
                close()

    app = FastAPI(lifespan=lifespan)
    app.state.config = config

    # Enforced in one place rather than per route, so a route added
    # later is protected by default instead of by remembering. It also
    # covers the static mount below -- middleware runs ahead of a
    # mounted sub-application, where a route-level dependency would not
    # have reached at all.
    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if not config.token:
            return await call_next(request)
        if not _authorized(config.token, request):
            return JSONResponse({"detail": "invalid or missing token"}, status_code=401)
        response = await call_next(request)
        # A valid token in the URL is traded for a cookie, so the page
        # never has to put it in a URL again -- and so it stops landing
        # in the access log with every fetch. Only for the query
        # parameter: a bearer caller chose headers precisely to avoid
        # cookies. `_authorized` passing with a query token present
        # means that token is the valid one, since it takes precedence.
        query_token = request.query_params.get(TOKEN_QUERY_PARAM)
        if query_token and request.cookies.get(TOKEN_COOKIE_NAME) != query_token:
            response.set_cookie(
                TOKEN_COOKIE_NAME,
                query_token,
                max_age=TOKEN_COOKIE_MAX_AGE_S,
                path="/",
                # Only under TLS: plain HTTP is a supported path (`adb
                # reverse` to localhost), and a Secure cookie would
                # silently never be stored there.
                secure=config.tls,
                httponly=True,
                samesite="strict",
            )
        return response

    app.include_router(markers_router)
    app.include_router(settings_router)

    @app.post("/cursor/move", status_code=204)
    def move_cursor(
        move: MoveRequest,
        backend: Annotated[CursorBackend, Depends(get_cursor_backend)],
    ) -> None:
        backend.move_absolute(move.x, move.y)

    @app.get("/markers/source")
    def read_marker_source(request: Request) -> dict:
        return request.app.state.markers.state()

    @app.post("/markers/source")
    def select_marker_source(selection: MarkerSourceRequest, request: Request) -> dict:
        controller = request.app.state.markers
        try:
            return controller.select(MarkerSource(selection.source))
        except MarkerSourceError as error:
            # 409: the request was well-formed and the server simply
            # cannot be in that state -- an unsupported compositor, the
            # overlay extra absent, no display. The body carries the
            # overlay's own words, and the state still reports printed
            # markers as active, because they are.
            return JSONResponse(
                {"detail": str(error), **controller.state()}, status_code=409
            )

    @app.post("/markers/overlay-margin")
    def set_overlay_margin(selection: OverlayMarginRequest, request: Request) -> dict:
        controller = request.app.state.markers
        try:
            return controller.set_overlay_extra_margin_px(selection.extra_margin_px)
        except MarkerSourceError as error:
            # Same shape as a failed source switch: the margin the
            # request asked for is still stored (the next successful
            # start uses it), but the overlay that was supposed to pick
            # it up right now did not, so printed markers stay active
            # and the state says so.
            return JSONResponse(
                {"detail": str(error), **controller.state()}, status_code=409
            )

    @app.get("/debug")
    def read_debug(request: Request) -> dict:
        return {"enabled": request.app.state.settings.debug}

    @app.post("/debug")
    def set_debug(selection: DebugRequest, request: Request) -> dict:
        request.app.state.settings.debug = selection.enabled
        logger.info("viewfinder overlay %s", "on" if selection.enabled else "off")
        return {"enabled": selection.enabled}

    # Async so it runs on the event loop, the only place the registry is
    # ever mutated: a threadpool route could read it mid-update.
    @app.get("/sessions")
    async def read_sessions(request: Request) -> dict:
        return {"sessions": request.app.state.sessions.listing(time.monotonic())}

    @app.get("/calibration")
    def read_calibrations(request: Request) -> dict:
        return {"lenses": request.app.state.lenses.listing()}

    # Async for the same reason as `/sessions`: it reads the registry.
    @app.post("/calibration")
    async def calibrate_session(
        selection: CalibrationRequest, request: Request
    ) -> JSONResponse:
        sessions = [
            session
            for session in request.app.state.sessions
            if selection.address in (None, session.address)
        ]
        if not sessions:
            return JSONResponse(
                {"detail": "no such session is streaming"}, status_code=404
            )
        if len(sessions) > 1:
            return JSONResponse(
                {
                    "detail": "several sessions are streaming; name one by the "
                    "address GET /sessions lists",
                    "addresses": [session.address for session in sessions],
                },
                status_code=409,
            )
        session = sessions[0]
        _calibration_action(
            session.stats, selection.action, request.app.state.lenses, session.label
        )
        calibration = session.stats.calibration
        return JSONResponse(
            {
                "address": session.address,
                "calibration": None if calibration is None else calibration.status(),
            }
        )

    @app.websocket(FRAME_SOCKET_PATH)
    async def stream_frames(websocket: WebSocket) -> None:
        # A browser cannot set headers on a WebSocket handshake, but it
        # sends the cookie the page's first request was issued. A device
        # holds no cookies, so the query parameter stays for it.
        client = _describe(websocket)
        if config.token and not _authorized(config.token, websocket):
            # Logged rather than silent: from the phone this looks like
            # the connection simply not working, and the cause is a URL
            # missing its token or a cookie from a previous run.
            logger.warning(
                "frame socket refused: bad or missing token, or foreign origin (%s)",
                client,
            )
            await websocket.close(code=WS_POLICY_VIOLATION)
            return
        await websocket.accept()
        # Unidentified until its `hello` arrives, which is the first
        # thing a current client sends.
        logger.info("client connected: %s", client)
        await run_frame_session(
            websocket,
            websocket.app.state.markers,
            websocket.app.state.cursor_backend,
            client,
            websocket.app.state.settings,
            websocket.app.state.sessions,
            websocket.app.state.trigger_hold,
            websocket.app.state.arbiter,
            lenses=websocket.app.state.lenses,
        )

    if WEB_DIR.is_dir():
        # Mounted last: "/" matches everything, so it must not shadow
        # the routes above.
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

    return app


def _authorized(configured: str, connection: HTTPConnection) -> bool:
    """Whether an HTTP request or socket handshake carries the token.

    The origin check applies to the cookie alone: it is the one
    credential a browser attaches on another page's behalf. A token in
    the URL or a header was put there deliberately by whoever sent it.
    """
    query_token = connection.query_params.get(TOKEN_QUERY_PARAM)
    authorization = connection.headers.get("authorization")
    token = presented_token(
        query_token, authorization, connection.cookies.get(TOKEN_COOKIE_NAME)
    )
    if not token_matches(configured, token):
        return False
    if presented_token(query_token, authorization) is not None:
        return True
    return origin_matches_host(
        connection.headers.get("origin"), connection.headers.get("host")
    )


def _describe(websocket: WebSocket) -> str:
    client = getattr(websocket, "client", None)
    return f"{client.host}:{client.port}" if client else "unknown address"


def _decode_and_solve(
    pipeline: SessionPipeline,
    payload: bytes,
    debug: bool = False,
    t: float | None = None,
    lenses: LensStore | None = None,
    identity: tuple[str | None, str | None] = (None, None),
    calibration: CalibrationCapture | None = None,
) -> tuple[FrameResult | None, float, float, LensModel | None]:
    """Blocking work, kept off the event loop.

    Both halves are CPU-bound and would otherwise stall every other
    connection the server is handling. A thread rather than a process
    because OpenCV releases the GIL during detection, and moving a
    1280x720 array across a process boundary would cost more than the
    few milliseconds of work being parallelised.

    Decoded straight to greyscale: detection uses nothing else, and
    skipping the colour conversion saves about a third of the decode
    (numbers in the `speed-up-marker-detection` change's design.md).

    The lens is looked up by the decoded frame's size, not the size the
    client's `hello` claimed: the frame is what the camera produced. A
    running calibration sees the same frame afterwards.
    """
    started = time.perf_counter()
    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    decoded_at = time.perf_counter()
    if frame is None:
        return None, (decoded_at - started) * 1000.0, 0.0, None
    height, width = frame.shape[:2]
    key = lens_key(*identity, (width, height))
    lens = None if lenses is None else lenses.get(key)
    result = pipeline.process_frame(frame, debug=debug, t=t, lens=lens)
    if calibration is not None and calibration.active:
        calibration.offer(frame, key)
    return (
        result,
        (decoded_at - started) * 1000.0,
        (time.perf_counter() - decoded_at) * 1000.0,
        lens,
    )


def _calibration_action(
    stats: SessionStats,
    action: object,
    lenses: LensStore | None,
    label: Callable[[], str],
) -> None:
    """Start or cancel a session's lens calibration.

    Starting replaces whatever calibration the session had, finished or
    not. The capture reaches the store only through its callback, which
    runs on the session's executor thread with an accepted model.
    """
    if action == "cancel":
        if stats.calibration is not None:
            stats.calibration.cancel()
            logger.info("lens calibration cancelled for %s", label())
        return
    if action != "start" or lenses is None:
        return

    def store(key: str, lens: LensModel) -> None:
        lenses.put(key, lens)
        logger.info(
            "lens calibrated for %s: %s, %.2fpx RMS over %d views",
            label(),
            key,
            lens.rms_px,
            lens.views,
        )

    stats.calibration = CalibrationCapture(store)
    logger.info("lens calibration started for %s", label())


async def run_frame_session(
    websocket: WebSocket,
    markers: MarkerSourceController,
    backend: CursorBackend,
    address: str = "unknown address",
    settings: ViewSettings | None = None,
    sessions: SessionRegistry | None = None,
    hold: TriggerHold | None = None,
    arbiter: CursorArbiter | None = None,
    lenses: LensStore | None = None,
) -> None:
    """One connection: receive frames, solve the newest, report back.

    Takes the marker source controller rather than a pipeline, and asks
    it for the current one per frame. Capturing the pipeline here would
    mean a marker source switched mid-session never reached a phone
    already streaming -- it would go on solving against the layout that
    was current when it connected, with nothing to say so.

    Two tasks over one slot. The receiver never decodes and never waits
    on the pipeline, so a slow frame cannot apply backpressure to the
    client; the processor always takes the newest frame available, and
    the slot counts whatever that displaced.

    A report goes back per processed frame rather than on a timer. At
    30fps that is 30 small JSON messages against 30 JPEGs travelling the
    other way, which is negligible, and it makes the transport
    deterministic to test: a client can wait for frame N to be
    acknowledged before sending frame N+1.

    The session is listed in `sessions` for exactly as long as the
    connection lasts, so a client with no screen can be watched from
    another device, and a dead one is never shown as streaming.

    Its aim is its own: the session smooths and holds through its own
    `SessionPipeline`, and reaches the cursor only through `arbiter`,
    which lets one session at a time -- the active shooter -- move it.
    """
    settings = settings or ViewSettings()
    slot = FrameSlot()
    stats = SessionStats(_slot=slot)
    # The session's own: capture timestamps are only comparable with
    # others from the same client clock.
    capture_clock = CaptureClock()
    # Inherited at connect, then owned by this session. A phone that
    # left the overlay on gets it back after a reload; a phone that
    # toggles it mid-session changes only its own frames.
    stats.debug_enabled = settings.debug
    loop = asyncio.get_running_loop()
    started = time.monotonic()
    last_logged = started
    seen_first_frame = False
    sessions = sessions if sessions is not None else SessionRegistry()
    hold = hold if hold is not None else TriggerHold(backend)
    arbiter = arbiter if arbiter is not None else CursorArbiter(backend)
    last_heard = started
    session = sessions.register(address, stats, started)
    # Every move this session makes goes through the arbiter, and only
    # lands while this session is the active shooter.
    cursor = arbiter.cursor_for(stats, session.label)
    aim = markers.session_pipeline(cursor)
    # The gated cursor, not the smoothing one: a shot goes exactly where
    # its frame aimed, and the filter never hears about it.
    triggers = _SessionTriggers(
        stats, hold, cursor, loop, claim=lambda: arbiter.claim(stats, session.label)
    )

    async def report(client_ms: float | None) -> None:
        stats.cursor = arbiter.status(stats)
        await _report(websocket, stats, client_ms)

    async def receive_loop() -> None:
        nonlocal seen_first_frame, last_heard
        while True:
            message = await websocket.receive()
            last_heard = time.monotonic()
            if message["type"] == "websocket.disconnect":
                return
            payload = message.get("bytes")
            if payload is None:
                # Text: control and telemetry, including the trigger.
                known_kind = stats.client_kind
                _handle_control(
                    stats,
                    triggers,
                    message.get("text"),
                    settings,
                    calibrate=lambda action: _calibration_action(
                        stats, action, lenses, session.label
                    ),
                )
                if stats.client_kind != known_kind:
                    logger.info(
                        "client identified: %s (version %s, frames %s)",
                        session.label(),
                        stats.client_version or "unknown",
                        "x".join(map(str, stats.frame_size or ())) or "unknown",
                    )
                continue
            stats.received += 1
            if not seen_first_frame:
                seen_first_frame = True
                logger.info("first frame received from %s", session.label())
            try:
                client_ms, jpeg = unpack_frame(payload)
            except FrameDecodeError:
                stats.failed += 1
                await report(None)
                continue
            slot.put(client_ms, jpeg)

    frame_errors = 0
    # The frame on an executor thread, if any. Cancelling the processor
    # cannot stop a thread, so teardown waits for this instead.
    in_flight: asyncio.Future | None = None

    async def process_loop() -> None:
        nonlocal frame_errors, in_flight
        while True:
            client_ms, jpeg = await slot.get()
            # Aim smoothing is timed by when the frame was captured, not
            # when it got here: the network's jitter is not the aim's.
            captured_at = capture_clock.stamp(client_ms)
            # A shot must not move the cursor while this session's own
            # smoothed move may be landing from a worker thread.
            triggers.processing = True
            try:
                # Read per frame rather than captured once: a debug toggle
                # arriving mid-session takes effect on the next frame.
                in_flight = loop.run_in_executor(
                    None,
                    _decode_and_solve,
                    aim,
                    jpeg,
                    stats.debug_enabled,
                    captured_at,
                    lenses,
                    (stats.client_kind, stats.camera),
                    stats.calibration,
                )
                # Retrieved here as well, for a job that fails after its
                # session stopped awaiting it.
                in_flight.add_done_callback(_retrieve)
                # Shielded: cancelling the processor must not orphan the
                # job's future, or teardown could not wait for it.
                result, decode_ms, solve_ms, lens = await asyncio.shield(in_flight)
            except Exception:
                triggers.processing = False
                # Anything the pipeline does not already turn into an
                # outcome -- an OpenCV error on a pathological frame, a
                # cursor device write failing. One frame is lost, not the
                # session. The traceback is logged once: at frame rate, a
                # persistent fault would otherwise bury the log.
                frame_errors += 1
                if frame_errors == 1:
                    logger.exception(
                        "frame from %s raised; counting it as failed "
                        "(further errors this session are counted, not logged)",
                        session.label(),
                    )
                stats.failed += 1
                stats.outcome = "error"
                stats.position = None
                stats.debug = None
                triggers.frame_processed(client_ms, None)
                await report(client_ms)
                continue
            triggers.processing = False
            stats.decode_ms = decode_ms
            stats.solve_ms = solve_ms
            stats.lens_rms_px = None if lens is None else lens.rms_px
            if result is None:
                # Undecodable bytes cost one frame, not the session. A
                # corrupt frame on a lossy link should not disconnect
                # the player.
                stats.failed += 1
                stats.outcome = "decode_failed"
                stats.position = None
                stats.debug = None
            else:
                stats.processed += 1
                stats.outcome = result.outcome.value
                stats.markers_detected = result.markers_detected
                stats.inside_hull = result.aim_point_inside_hull
                stats.position = result.position
                stats.debug = (
                    None if result.debug is None else result.debug.as_message()
                )
            # Before the report, so a shot this frame resolved is already
            # in the trigger count it carries.
            triggers.frame_processed(client_ms, stats.position)
            await report(client_ms)

            nonlocal last_logged
            now = time.monotonic()
            if now - last_logged >= SESSION_LOG_INTERVAL_S:
                fps = stats.processed / max(now - started, 1e-9)
                logger.info(
                    "streaming from %s: %.1f fps, %s markers, %s, "
                    "%d received / %d solved / %d dropped / %d failed",
                    session.label(),
                    fps,
                    stats.markers_detected,
                    stats.outcome,
                    stats.received,
                    stats.processed,
                    stats.dropped,
                    stats.failed,
                )
                if frame_errors:
                    logger.warning(
                        "%s: %d frame(s) raised so far", session.label(), frame_errors
                    )
                last_logged = now

    receiver = asyncio.create_task(receive_loop())
    processor = asyncio.create_task(process_loop())

    async def hold_watchdog() -> None:
        while True:
            await asyncio.sleep(HOLD_CHECK_INTERVAL_S)
            silent_for = time.monotonic() - last_heard
            if silent_for > HOLD_IDLE_RELEASE_S and hold.release(stats):
                logger.warning(
                    "%s held the trigger but went silent for %.1fs; released it",
                    session.label(),
                    silent_for,
                )

    watchdog = asyncio.create_task(hold_watchdog())
    try:
        # Both, not just the receiver: a processor that dies while the
        # receiver carries on would leave a session that accepts frames
        # forever and never answers one, with nothing in the log to say
        # why.
        await asyncio.wait((receiver, processor), return_when=asyncio.FIRST_COMPLETED)
        if processor.done() and not processor.cancelled():
            error = processor.exception()
            logger.error(
                "frame processing for %s stopped; closing the session",
                session.label(),
                exc_info=error,
            )
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
            try:
                await websocket.close(code=WS_INTERNAL_ERROR)
            except (RuntimeError, ConnectionError):
                pass
    finally:
        # Everything that must happen comes before the first await. This
        # handler can itself be cancelled while it cleans up -- a server
        # shutting down cancels it, and Starlette's test client cancels
        # right after sending the disconnect -- and a cancelled await
        # would skip whatever follows it: a trigger left held down, a
        # dead session still listed.
        #
        # The client is gone: stop solving its frames and emit nothing
        # further on its behalf. The tasks and the slot go with the
        # connection, so the next one starts from zero.
        receiver.cancel()
        processor.cancel()
        watchdog.cancel()
        # A shot still waiting for its frame never fired, so there is
        # nothing to undo: it is simply dropped with the session.
        triggers.close()
        # Whatever ended the session, a button it was holding goes up
        # with it: nothing else would ever send the release.
        hold.release(stats)
        # The cursor too: the next session to aim takes it at once
        # rather than after the idle lapse. Closing the gate, not just
        # releasing, so a frame still on an executor thread cannot take
        # it straight back when it lands.
        cursor.close()
        sessions.unregister(session)
        elapsed = time.monotonic() - started
        if seen_first_frame:
            logger.info(
                "client disconnected: %s after %.1fs, "
                "%d received / %d solved / %d dropped / %d failed (%.1f fps)",
                session.label(),
                elapsed,
                stats.received,
                stats.processed,
                stats.dropped,
                stats.failed,
                stats.processed / max(elapsed, 1e-9),
            )
        else:
            # Connected but never streamed: the page was open and Start
            # was never pressed, or capture failed on the device.
            logger.info(
                "client disconnected: %s after %.1fs without sending a frame",
                session.label(),
                elapsed,
            )
        # Last, so being cancelled here costs nothing that matters.
        # `wait`, not `gather`: cancelled mid-wait, `gather` raises one
        # of the cancellations this block just sent its own tasks, which
        # the canceller cannot recognise as its own -- anyio's scope,
        # for one, then lets it escape as an error. `wait` re-raises
        # the canceller's, and leaves the tasks' outcomes to be read
        # below.
        pending = {receiver, processor, watchdog}
        if in_flight is not None:
            pending.add(in_flight)
        await asyncio.wait(pending)
        for task in (receiver, processor, watchdog):
            _retrieve(task)


def _retrieve(future: asyncio.Future) -> None:
    """Mark a finished future's outcome as seen, whatever it was.

    What `gather(..., return_exceptions=True)` used to do for the
    session's tasks: a task that died is already logged where it matters,
    and asyncio would otherwise log it again as never retrieved.
    """
    if not future.cancelled():
        future.exception()


def _handle_control(
    stats: SessionStats,
    triggers: _SessionTriggers,
    text: str | None,
    settings: ViewSettings,
    calibrate: Callable[[object], None] | None = None,
) -> None:
    """Client-side telemetry and control arriving the other way.

    Round-trip time is measured on the phone, because only the phone's
    clock can meaningfully be compared against itself. The server echoes
    each frame's timestamp; the phone subtracts and reports back what it
    measured, so the server's telemetry carries the number too.

    Without a `state` the trigger is one click, exactly as before holds
    existed. `down` holds the button for this session and `up` lets go,
    so frames arriving in between drag; an unreadable `state` is ignored
    rather than guessed at. A click or `down` may name, in `frame_ms`,
    the frame it was aimed with, and then fires at that frame's
    unsmoothed aim instead of wherever the smoothed cursor has got to;
    without it (or with one that is not a finite number) it acts where
    the cursor is. Either way it goes through the session's
    `_SessionTriggers`, which keeps the order they were sent in. The
    count is of presses: a click or a `down` that started a hold.

    `hello` names the kind of client on the other end. Like `rtt`, a
    field that cannot be read is ignored rather than guessed at: a
    session that stays unidentified is served exactly as before.

    The debug flag is set on this session's stats and nowhere else. The
    pipeline behind every session is one shared object, so anything
    stickier than a per-connection flag would let one phone's debug view
    change what another phone's frames compute.
    """
    if not text:
        return
    try:
        message = json.loads(text)
    except ValueError:
        return
    if not isinstance(message, dict):
        return
    if message.get("type") == "rtt":
        try:
            stats.round_trip_ms = float(message["ms"])
        except (KeyError, TypeError, ValueError):
            return
    elif message.get("type") == "trigger":
        state = message.get("state")
        if state is None:
            triggers.submit(TriggerAction("click", _frame_ms(message)))
        elif state == "down":
            triggers.submit(TriggerAction("down", _frame_ms(message)))
        elif state == "up":
            triggers.submit(TriggerAction("up"))
    elif message.get("type") == "hello":
        kind = message.get("client")
        if not isinstance(kind, str) or not kind.strip():
            return
        # Bounded: these end up in log lines and in GET /sessions.
        stats.client_kind = kind.strip()[:HELLO_FIELD_MAX]
        version = message.get("version")
        stats.client_version = (
            version.strip()[:HELLO_FIELD_MAX] if isinstance(version, str) else None
        )
        stats.frame_size = _frame_size(message.get("frame_size"))
        camera = message.get("camera")
        stats.camera = (
            camera.strip()[:HELLO_FIELD_MAX] or None
            if isinstance(camera, str)
            else None
        )
    elif message.get("type") == "calibrate":
        # An unknown action is ignored there, as everywhere here.
        if calibrate is not None:
            calibrate(message.get("action"))
    elif message.get("type") == "debug":
        enabled = message.get("enabled")
        if not isinstance(enabled, bool):
            # Same posture as `rtt` above: ignore what cannot be read
            # rather than guess at it. Guessing here would silently
            # start or stop a debug session the operator did not ask
            # for.
            return
        stats.debug_enabled = enabled
        if not enabled:
            stats.debug = None
        # Remembered for the next session too, so the button comes back
        # the way it was left. Only sessions opened after this see it --
        # one already running keeps its own flag.
        settings.debug = enabled


def _frame_ms(message: dict) -> float | None:
    """A trigger's `frame_ms`, if it is a usable timestamp."""
    value = message.get("frame_ms")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


class _SessionTriggers:
    """One session's trigger: its actions, the aim they fire at, and when.

    A trigger naming a frame fires once that frame (or a newer one that
    displaced it from the slot) has been processed, at the unsmoothed
    aim of the solved frame nearest it (`shot.AimHistory`). Actions run
    strictly in the order they arrived (`shot.TriggerQueue`), and only
    while no frame of this session is in the executor, so a shot's move
    and its press cannot have this session's smoothed move land between
    them. A shot still waiting after `SHOT_WAIT_S` fires anyway, with
    whatever the history has -- late, never lost.

    The cursor is moved only for an action that will actually press:
    with the button already down, a click or `down` presses nothing, and
    moving would drag whatever is held.
    """

    def __init__(
        self,
        stats: SessionStats,
        hold: TriggerHold,
        cursor: CursorBackend,
        loop: asyncio.AbstractEventLoop,
        claim: Callable[[], None] = lambda: None,
    ) -> None:
        self._stats = stats
        self._hold = hold
        self._cursor = cursor
        self._loop = loop
        self._claim = claim
        self.history = AimHistory()
        self._queue = TriggerQueue()
        self.processing = False
        self._deadline: asyncio.TimerHandle | None = None
        self._overdue = False

    def submit(self, action: TriggerAction) -> None:
        self._queue.push(action)
        self.drain()

    def frame_processed(self, client_ms: float, position: Point | None) -> None:
        self.history.record(client_ms, position)
        self.drain()

    def drain(self) -> None:
        if self.processing:
            return
        for action in self._queue.ready(self.history, force=self._overdue):
            self._run(action)
        if not self._queue:
            self._overdue = False
            if self._deadline is not None:
                self._deadline.cancel()
                self._deadline = None
        elif self._deadline is None:
            self._deadline = self._loop.call_later(SHOT_WAIT_S, self._expire)

    def close(self) -> None:
        if self._deadline is not None:
            self._deadline.cancel()
            self._deadline = None
        self._queue.clear()

    def _expire(self) -> None:
        # If a frame is mid-process, its completion drains with force.
        self._deadline = None
        self._overdue = True
        self.drain()

    def _run(self, action: TriggerAction) -> None:
        if action.state == "up":
            self._hold.release(self._stats)
            return
        if action.state == "down" and self._hold.holds(self._stats):
            return
        # A press makes this session the active shooter, before the
        # shot moves the cursor through its gate.
        self._claim()
        if action.frame_ms is not None and not self._hold.active:
            aim = self.history.aim_at(action.frame_ms)
            if aim is not None:
                self._cursor.move_absolute(*aim)
        if action.state == "click":
            self._hold.click()
            self._stats.triggers += 1
        elif self._hold.acquire(self._stats):
            self._stats.triggers += 1


def _frame_size(value: object) -> tuple[int, int] | None:
    """A `[width, height]` pair of positive integers, or nothing."""
    if not isinstance(value, list) or len(value) != 2:
        return None
    if not all(
        isinstance(side, int) and not isinstance(side, bool) and side > 0
        for side in value
    ):
        return None
    return value[0], value[1]


async def _report(
    websocket: WebSocket, stats: SessionStats, client_ms: float | None
) -> None:
    try:
        await websocket.send_json(stats.as_message(client_ms))
    except (RuntimeError, ConnectionError):
        # The socket closed under us mid-report. The receive loop is
        # about to notice; nothing here needs to escalate.
        return


def _device_details(config: ServerConfig, certfile: Path | None) -> str:
    """What a client without a browser has to be configured with.

    A phone is handed a URL to open. A device has its settings typed into
    a build configuration, so it needs them as separate values -- and,
    under TLS, a fingerprint to check the certificate it embedded against
    the one actually being served. Regenerating `.boresight/` changes it,
    and from the device that looks only like a connection that fails.
    """
    lines = [
        "  For a device (ESP32-CAM), configure:",
        f"    host    {config.advertised_host()}",
        f"    port    {config.port}",
        f"    path    {FRAME_SOCKET_PATH}",
        f"    tls     {'on' if config.tls else 'off'}",
        f"    token   {config.token or '(none)'}",
    ]
    if certfile is not None:
        lines.append(f"    cert    {certfile}")
        lines.append(f"    sha256  {certificate_fingerprint(certfile)}")
    return "\n".join(lines) + "\n"


# Deliberately no module-level `app = create_app()`: one built at import
# has the default config, with no token, and `uvicorn
# boresight.server:app --host 0.0.0.0` would serve it without `main()`
# ever validating anything. Run `python -m boresight.server`.


def main(argv: list[str] | None = None) -> int:
    import argparse

    import uvicorn

    from boresight import terminal_qr
    from boresight.netaccess import (
        DEFAULT_HOST,
        DEFAULT_PORT,
        InsecureConfigurationError,
        generate_token,
        is_loopback,
        resolve_certificate,
    )
    from boresight.settings import (
        DEFAULT_SETTINGS_PATH,
        SettingsError,
        resolve_settings,
    )

    parser = argparse.ArgumentParser(prog="python -m boresight.server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--token", default=None, help="shared token clients must present"
    )
    parser.add_argument(
        "--token-auto",
        action="store_true",
        help="generate a random token and print it with the phone URL",
    )
    parser.add_argument(
        "--tls",
        action="store_true",
        help="serve HTTPS. Required for the phone: browsers expose the "
        "camera only in a secure context, and a LAN IP over plain HTTP "
        "is not one",
    )
    parser.add_argument("--certfile", type=Path, default=None)
    parser.add_argument("--keyfile", type=Path, default=None)
    parser.add_argument(
        "--markers",
        default=DEFAULT_SPEC,
        metavar="SOURCE",
        help="marker layout: 'file', 'file:<path>', or "
        "'screen:<W>x<H>' for tags drawn on the display by "
        "`python -m boresight.overlay` (default: %(default)s)",
    )
    parser.add_argument(
        "--overlay-extra-margin-px",
        type=int,
        default=None,
        help="shrink the on-screen overlay's auto-detected available "
        "area by this much on every side, on top of whatever the "
        "desktop's own panels already reserve. For a display whose "
        "panel reservation isn't detected automatically (default: the "
        "settings file's, else 0; see `python -m boresight.overlay --help`)",
    )
    # Settings: flag > BORESIGHT_* environment variable > settings file
    # > default. See `settings.py`.
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        metavar="PATH",
        help="settings file, read at startup and written when settings "
        "are saved from the phone (default: %(default)s)",
    )
    tuning = parser.add_argument_group(
        "aim tuning", "each overrides its BORESIGHT_* variable and the settings file"
    )
    tuning.add_argument(
        "--aim-min-cutoff",
        type=float,
        default=None,
        metavar="HZ",
        help="one-euro min cutoff: raise if a held aim creeps into place",
    )
    tuning.add_argument(
        "--aim-beta",
        type=float,
        default=None,
        help="one-euro beta: raise if a fast swing still feels smoothed",
    )
    tuning.add_argument(
        "--aim-hold-s",
        type=float,
        default=None,
        metavar="SECONDS",
        help="how long a brief detection dropout holds the last aim (0: off)",
    )
    tuning.add_argument(
        "--rel-scale",
        type=float,
        default=None,
        help="relative-motion units per full-screen sweep (0: off, the default)",
    )
    parser.add_argument(
        "--no-qr",
        action="store_true",
        help="do not print the phone URL as a QR code (it is printed only "
        "to an interactive terminal large enough for it anyway)",
    )
    parser.add_argument(
        "--full-frame-detection",
        action="store_true",
        help="search every frame in full at full resolution, instead of "
        "letting each session search a half-size frame while its markers "
        "stay large and in view. Slower; for comparison, or if tracking "
        "misbehaves with your camera",
    )
    args = parser.parse_args(argv)

    # Uvicorn configures its own loggers and leaves the root alone, so
    # without this the connection lines below never appear -- which is
    # exactly when you most want them: working out whether the phone
    # reached the server at all.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        layout_factory = marker_map_factory(args.markers)
    except (LayoutSourceError, OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")

    try:
        settings = resolve_settings(
            args.config,
            cli={
                "tuning.min_cutoff": args.aim_min_cutoff,
                "tuning.beta": args.aim_beta,
                "tuning.hold_s": args.aim_hold_s,
                "tuning.rel_scale": args.rel_scale,
                "view.overlay_extra_margin_px": args.overlay_extra_margin_px,
            },
        )
    except SettingsError as error:
        parser.exit(2, f"{error}\n")

    config = ServerConfig(
        host=args.host,
        port=args.port,
        token=args.token or (generate_token() if args.token_auto else None),
        tls=args.tls,
        certfile=args.certfile,
        keyfile=args.keyfile,
    )
    try:
        config.validate()
    except InsecureConfigurationError as error:
        parser.exit(2, f"{error}\n")

    ssl_options = {}
    certfile = None
    if config.tls:
        certfile, keyfile = resolve_certificate(config)
        ssl_options = {"ssl_certfile": str(certfile), "ssl_keyfile": str(keyfile)}

    # flush: stdout is block-buffered when redirected to a file or a
    # pipe, and this is the one line the operator has to read before
    # anything else can happen. Buffered, it appears after the server
    # has already been running for a while -- or never.
    print(f"\n  Open this on the phone:  {config.phone_url()}\n", flush=True)
    # Printed, never logged, like the line above: see `terminal_qr`.
    qr = None if args.no_qr else terminal_qr.for_terminal(config.phone_url())
    if qr is not None:
        print(qr, flush=True)
    print(_device_details(config, certfile), flush=True)
    if not config.tls and not is_loopback(config.host):
        print(
            "  Warning: serving plain HTTP. The camera will not be available\n"
            "  on the phone -- browsers expose it only in a secure context.\n"
            "  Use --tls, or reach the server as localhost via\n"
            f"  `adb reverse tcp:{config.port} tcp:{config.port}` over USB.\n",
            flush=True,
        )

    lens_store = LensStore(DEFAULT_LENS_PATH)

    # Before `uvicorn.run`, whose logging setup keeps logger filters.
    # The banner above is the one place the token is meant to appear.
    install_log_redaction()
    uvicorn.run(
        create_app(
            marker_map_factory=layout_factory,
            config=config,
            tracked_detection=not args.full_frame_detection,
            settings=settings,
            lens_store_factory=lambda: lens_store,
        ),
        host=config.host,
        port=config.port,
        **ssl_options,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
