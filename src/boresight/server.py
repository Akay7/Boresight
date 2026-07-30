from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, Field

from boresight.inject import CursorBackend, UinputCursorBackend


class MoveRequest(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


def get_cursor_backend(request: Request) -> CursorBackend:
    return request.app.state.cursor_backend


def create_app(
    backend_factory: Callable[[], CursorBackend] = UinputCursorBackend,
) -> FastAPI:
    """Build the FastAPI app.

    `backend_factory` is the seam tests use to substitute a
    `FakeCursorBackend` instead of opening a real uinput device.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Constructed at startup, not on first request, so a broken
        # environment (e.g. no /dev/uinput permission) fails fast.
        app.state.cursor_backend = backend_factory()
        try:
            yield
        finally:
            close = getattr(app.state.cursor_backend, "close", None)
            if close is not None:
                close()

    app = FastAPI(lifespan=lifespan)

    @app.post("/cursor/move", status_code=204)
    def move_cursor(
        move: MoveRequest,
        backend: Annotated[CursorBackend, Depends(get_cursor_backend)],
    ) -> None:
        backend.move_absolute(move.x, move.y)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    # Loopback-only by default: nothing on the network should be able to
    # move the cursor until there's a real auth/transport story.
    uvicorn.run(app, host="127.0.0.1", port=8000)
