from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from boresight.inject import CursorBackend, UinputCursorBackend
from boresight.marker_map import MarkerMap, load_marker_map
from boresight.markers import router as markers_router
from boresight.netaccess import (
    TOKEN_QUERY_PARAM,
    ServerConfig,
    presented_token,
    token_matches,
)
from boresight.pipeline import DEFAULT_CONFIG_PATH, AimPipeline, FrameResult
from boresight.stream import (
    FrameDecodeError,
    FrameSlot,
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


class MoveRequest(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


def get_cursor_backend(request: Request) -> CursorBackend:
    return request.app.state.cursor_backend


def _default_marker_map() -> MarkerMap:
    return load_marker_map(DEFAULT_CONFIG_PATH)


def create_app(
    backend_factory: Callable[[], CursorBackend] = UinputCursorBackend,
    marker_map_factory: Callable[[], MarkerMap] = _default_marker_map,
    config: ServerConfig | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    The factories are the seam tests use to substitute a
    `FakeCursorBackend` and a synthetic layout instead of opening a real
    uinput device and reading the shipped config. Both are called at
    startup rather than on first request, so a broken environment
    (no `/dev/uinput` permission, an unparseable layout) fails fast
    instead of failing on the first frame.
    """
    config = config or ServerConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.cursor_backend = backend_factory()
        app.state.marker_map = marker_map_factory()
        app.state.pipeline = AimPipeline(app.state.marker_map, app.state.cursor_backend)
        try:
            yield
        finally:
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
        token = presented_token(
            request.query_params.get(TOKEN_QUERY_PARAM),
            request.headers.get("authorization"),
        )
        if not token_matches(config.token, token):
            return JSONResponse({"detail": "invalid or missing token"}, status_code=401)
        return await call_next(request)

    app.include_router(markers_router)

    @app.post("/cursor/move", status_code=204)
    def move_cursor(
        move: MoveRequest,
        backend: Annotated[CursorBackend, Depends(get_cursor_backend)],
    ) -> None:
        backend.move_absolute(move.x, move.y)

    @app.websocket(FRAME_SOCKET_PATH)
    async def stream_frames(websocket: WebSocket) -> None:
        # A browser cannot set headers on a WebSocket handshake, so the
        # query parameter is not a convenience here -- it is the only
        # mechanism the phone has.
        token = websocket.query_params.get(TOKEN_QUERY_PARAM)
        if not token_matches(config.token, token):
            await websocket.close(code=WS_POLICY_VIOLATION)
            return
        await websocket.accept()
        await run_frame_session(websocket, websocket.app.state.pipeline)

    if WEB_DIR.is_dir():
        # Mounted last: "/" matches everything, so it must not shadow
        # the routes above.
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

    return app


def _decode_and_solve(
    pipeline: AimPipeline, payload: bytes
) -> tuple[FrameResult | None, float, float]:
    """Blocking work, kept off the event loop.

    Both halves are CPU-bound and would otherwise stall every other
    connection the server is handling. A thread rather than a process
    because OpenCV releases the GIL during detection, and moving a
    1280x720 array across a process boundary would cost more than the
    few milliseconds of work being parallelised.
    """
    started = time.perf_counter()
    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    decoded_at = time.perf_counter()
    if frame is None:
        return None, (decoded_at - started) * 1000.0, 0.0
    result = pipeline.process_frame(frame)
    return (
        result,
        (decoded_at - started) * 1000.0,
        (time.perf_counter() - decoded_at) * 1000.0,
    )


async def run_frame_session(websocket: WebSocket, pipeline: AimPipeline) -> None:
    """One connection: receive frames, solve the newest, report back.

    Two tasks over one slot. The receiver never decodes and never waits
    on the pipeline, so a slow frame cannot apply backpressure to the
    client; the processor always takes the newest frame available, and
    the slot counts whatever that displaced.

    A report goes back per processed frame rather than on a timer. At
    30fps that is 30 small JSON messages against 30 JPEGs travelling the
    other way, which is negligible, and it makes the transport
    deterministic to test: a client can wait for frame N to be
    acknowledged before sending frame N+1.
    """
    slot = FrameSlot()
    stats = SessionStats(_slot=slot)
    loop = asyncio.get_running_loop()

    async def receive_loop() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            payload = message.get("bytes")
            if payload is None:
                # Text: control and telemetry. The trigger event will
                # land here without disturbing frame handling.
                _handle_control(stats, message.get("text"))
                continue
            stats.received += 1
            try:
                client_ms, jpeg = unpack_frame(payload)
            except FrameDecodeError:
                stats.failed += 1
                await _report(websocket, stats, None)
                continue
            slot.put(client_ms, jpeg)

    async def process_loop() -> None:
        while True:
            client_ms, jpeg = await slot.get()
            result, decode_ms, solve_ms = await loop.run_in_executor(
                None, _decode_and_solve, pipeline, jpeg
            )
            stats.decode_ms = decode_ms
            stats.solve_ms = solve_ms
            if result is None:
                # Undecodable bytes cost one frame, not the session. A
                # corrupt frame on a lossy link should not disconnect
                # the player.
                stats.failed += 1
                stats.outcome = "decode_failed"
                stats.position = None
            else:
                stats.processed += 1
                stats.outcome = result.outcome.value
                stats.markers_detected = result.markers_detected
                stats.inside_hull = result.aim_point_inside_hull
                stats.position = result.position
            await _report(websocket, stats, client_ms)

    receiver = asyncio.create_task(receive_loop())
    processor = asyncio.create_task(process_loop())
    try:
        await receiver
    finally:
        # The client is gone: stop solving its frames and emit nothing
        # further on its behalf. Both tasks and the slot go with the
        # connection, so the next one starts from zero.
        processor.cancel()
        await asyncio.gather(processor, return_exceptions=True)


def _handle_control(stats: SessionStats, text: str | None) -> None:
    """Client-side telemetry arriving the other way.

    Round-trip time is measured on the phone, because only the phone's
    clock can meaningfully be compared against itself. The server echoes
    each frame's timestamp; the phone subtracts and reports back what it
    measured, so the server's telemetry carries the number too.
    """
    if not text:
        return
    try:
        message = json.loads(text)
    except ValueError:
        return
    if isinstance(message, dict) and message.get("type") == "rtt":
        try:
            stats.round_trip_ms = float(message["ms"])
        except KeyError, TypeError, ValueError:
            return


async def _report(
    websocket: WebSocket, stats: SessionStats, client_ms: float | None
) -> None:
    try:
        await websocket.send_json(stats.as_message(client_ms))
    except RuntimeError, ConnectionError:
        # The socket closed under us mid-report. The receive loop is
        # about to notice; nothing here needs to escalate.
        return


app = create_app()


def main(argv: list[str] | None = None) -> int:
    import argparse

    import uvicorn

    from boresight.netaccess import (
        DEFAULT_HOST,
        DEFAULT_PORT,
        InsecureConfigurationError,
        generate_token,
        is_loopback,
        resolve_certificate,
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
    args = parser.parse_args(argv)

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
    if config.tls:
        certfile, keyfile = resolve_certificate(config)
        ssl_options = {"ssl_certfile": str(certfile), "ssl_keyfile": str(keyfile)}

    # flush: stdout is block-buffered when redirected to a file or a
    # pipe, and this is the one line the operator has to read before
    # anything else can happen. Buffered, it appears after the server
    # has already been running for a while -- or never.
    print(f"\n  Open this on the phone:  {config.phone_url()}\n", flush=True)
    if not config.tls and not is_loopback(config.host):
        print(
            "  Warning: serving plain HTTP. The camera will not be available\n"
            "  on the phone -- browsers expose it only in a secure context.\n"
            "  Use --tls, or reach the server as localhost via\n"
            "  `adb reverse tcp:8000 tcp:8000` over USB.\n",
            flush=True,
        )

    uvicorn.run(
        create_app(config=config), host=config.host, port=config.port, **ssl_options
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
