"""Reading, changing and saving the runtime settings over HTTP.

A router of its own, like `markers.router`, so the token middleware in
`server.create_app` covers it like every other route. The routes are
plain `def`s, run in FastAPI's threadpool: `LiveSettings` serializes
changes under its own lock, and every session reads the new snapshot on
its next frame (`marker_source.SessionPipeline`), so nothing here has to
find or touch a running session.

The file path is `LiveSettings.path`, fixed at startup. Nothing from a
request names a file.
"""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from boresight.inject import CursorBackend
from boresight.marker_source import (
    MarkerSource,
    MarkerSourceController,
)
from boresight.settings import (
    SettingsError,
    Tuning,
    TuningUpdate,
    ViewPreferences,
    tuning_limits,
)

logger = logging.getLogger("boresight")

router = APIRouter()


def apply_rel_scale(backend: CursorBackend, tuning: Tuning) -> None:
    """Push the relative scale to a backend that has one.

    The one tunable no session reads per frame: the backend is shared
    and has no frame to read it on. A backend without the feature (any
    but uinput) simply does not have the attribute.
    """
    if hasattr(backend, "rel_scale"):
        backend.rel_scale = tuning.rel_scale


def restore_marker_source(controller: MarkerSourceController, source: str) -> None:
    """Bring saved on-screen markers back, without holding up startup.

    Starting the overlay can take seconds. The controller's lock already
    serializes this against a client's selection and against shutdown,
    and a failure leaves printed markers active and says why in the
    state the phone reads -- the same as a failed tap.
    """
    if source != MarkerSource.SCREEN.value:
        return

    def restore() -> None:
        try:
            controller.select(MarkerSource.SCREEN)
        except Exception as error:  # logged, never fatal
            logger.warning(
                "could not restore on-screen markers from the settings "
                "file; printed markers are active (%s)",
                error,
            )
        else:
            logger.info("on-screen markers restored from the settings file")

    threading.Thread(target=restore, name="restore-markers", daemon=True).start()


def current_view(app: FastAPI) -> ViewPreferences:
    """The view preferences in effect, read from whoever owns each."""
    markers = app.state.markers
    return ViewPreferences(
        debug=app.state.settings.debug,
        marker_source=markers.source.value,
        overlay_extra_margin_px=markers.overlay_extra_margin_px,
    )


def _state(app: FastAPI) -> dict:
    live = app.state.live_settings
    return {
        "tuning": live.tuning.model_dump(),
        "view": current_view(app).model_dump(),
        "limits": tuning_limits(),
        # Dotted key -> the flag or variable that set it. A value pinned
        # this way wins over the file again on the next start.
        "pinned": live.pinned,
        "rel_scale_supported": hasattr(app.state.cursor_backend, "rel_scale"),
        "path": str(live.path) if live.path is not None else None,
    }


@router.get("/settings")
def read_settings(request: Request) -> dict:
    return _state(request.app)


@router.post("/settings/tuning")
def update_tuning(update: TuningUpdate, request: Request) -> dict:
    # The ranges were already enforced by `TuningUpdate` (a 422 before
    # this runs); `update_tuning` validates the combined result again.
    app = request.app
    changes = update.model_dump(exclude_none=True)
    try:
        tuning = app.state.live_settings.update_tuning(
            changes,
            apply=lambda tuning: apply_rel_scale(app.state.cursor_backend, tuning),
        )
    except SettingsError as error:
        return JSONResponse({"detail": str(error), **_state(app)}, status_code=422)
    if changes:
        logger.info(
            "tuning: min_cutoff %.3g, beta %.3g, hold %.2fs, rel scale %g",
            tuning.min_cutoff,
            tuning.beta,
            tuning.hold_s,
            tuning.rel_scale,
        )
    return _state(app)


@router.post("/settings/save")
def save_settings(request: Request) -> dict:
    app = request.app
    try:
        path = app.state.live_settings.save(current_view(app))
    except SettingsError as error:
        # No file configured: the request was fine, the server just
        # has nowhere to put it.
        return JSONResponse({"detail": str(error), **_state(app)}, status_code=409)
    except OSError as error:
        logger.warning("could not save settings: %s", error)
        return JSONResponse(
            {"detail": f"could not save settings: {error}", **_state(app)},
            status_code=500,
        )
    logger.info("settings saved to %s", path)
    return _state(app)
