## Context

`server.py` builds its `FastAPI` app through a `create_app()` factory so
tests can substitute a `FakeCursorBackend` for the real `uinput` one.
The only route today is `POST /cursor/move`. `detect.py` already depends
on `opencv-python-headless` and hardcodes `DICTIONARY = "DICT_4X4_50"`;
this change reuses that constant so the generated tags and the detector
can never drift onto different dictionaries. There is no
`config/markers.toml` or marker map yet — those are separate, later
work — so this endpoint takes marker id and size as request parameters
rather than reading a layout file.

## Goals / Non-Goals

**Goals:**
- Serve printable ArUco tags, from the browser, at exact physical size.
- Reuse the existing `DICT_4X4_50` dictionary so server-generated tags
  are guaranteed decodable by `detect.py`.
- Add zero new runtime dependencies.

**Non-Goals:**
- Reading or producing `config/markers.toml` — id/size are passed as
  request parameters, not looked up from a layout.
- Server-side PDF generation — the browser's print-to-PDF already
  produces a to-scale PDF from the same SVG.
- Authentication/access control on the new routes — unchanged from the
  existing loopback-only posture (`server.py` binds `127.0.0.1`).

## Decisions

**Vector SVG built from the bit grid, not a rasterized PNG.** A raster
image is only exact at the DPI it was generated for; a print pipeline
(browser → OS print dialog → driver → printer) can resample it at any
DPI along the way, and README already flags this class of scaling bug
("Print at 100% scale. Never 'fit to page'"). `cv2.aruco.generateImageMarker`
called at the dictionary's native resolution (marker bits plus border —
6x6 for `DICT_4X4_50`'s 4x4 cells + 1-cell quiet border, matching
README's "Sizing" section) returns exactly one pixel per cell. Each
pixel becomes one SVG `<rect>`; the SVG's `viewBox` is the cell grid
(`0 0 6 6`) and its `width`/`height` are set in real `mm` units
(`"80mm"`), so the document itself carries the physical size — nothing
in this code does DPI arithmetic, that's delegated entirely to the
browser/printer's own unit handling, which is the same delegation any
print pipeline makes.

Alternative considered: embed a rasterized PNG at a fixed high DPI
(e.g., 300 DPI) sized to the target mm. Rejected — it reintroduces the
resampling risk the vector approach avoids, for no benefit, since the
bit grid is already available at zero cost from `generateImageMarker`.

**New `src/boresight/markers.py` module with an `APIRouter`, included
into `create_app()`.** Keeps `server.py` focused on cursor injection
wiring and mirrors how a `pipeline.py`/future modules would plug in —
one router per concern, composed in the app factory. Alternative
considered: add routes directly in `server.py`. Rejected — it couples
an unrelated concern (marker rendering has no `CursorBackend`
dependency) into the file whose job is backend wiring.

**No templating dependency.** The HTML index and SVG bodies are small,
static-shaped strings; an f-string built response avoids adding Jinja2
or similar for two simple templates. Revisit if the page grows real
layout logic.

**Request contract:**
- `GET /markers/{marker_id}.svg?size_mm=80` — one tag, `image/svg+xml`.
  `marker_id` validated against the dictionary's id range (0-49 for
  `DICT_4X4_50`); `size_mm` validated positive.
- `GET /markers?ids=0,1,2,3&size_mm=80` — an HTML page embedding each
  requested tag's SVG plus the print-at-100% instruction; `ids` defaults
  to `0-7` and `size_mm` to `80` (README's reference layout: 8 markers,
  80mm) when omitted, since there's no marker map yet to supply a real
  layout.

## Risks / Trade-offs

- [Browser print dialogs default some "shrink to fit"/margin options
  that can silently rescale even an mm-correct SVG] → Mitigated by
  stating the requirement plainly on the page itself; not fully
  solvable in software, which is why README already tells the user to
  verify with a ruler regardless of generation method. This design
  doesn't remove that manual verification step, it only removes a
  second, disconnected code path that could get the dictionary or
  sizing wrong.
- [No auth on new routes] → No new exposure: `server.py`'s `__main__`
  already binds loopback-only, matching the existing `/cursor/move`
  posture; this is unchanged by this design.

## Migration Plan

Additive only — a new module and new routes registered in
`create_app()`. No data migration, no changes to `/cursor/move`. Revert
by removing the router include and the module.
