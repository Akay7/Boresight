## Why

README's "Repo layout" plans a standalone `tools/gen_markers.py` script to
produce printable marker sheets, and "Generate and print markers at
verified physical size" is the first unchecked item in the Milestones
list — every downstream milestone (calibration, detection tuning, the
whole aim pipeline) needs correctly-sized printed markers to test
against. Rather than add a second, disconnected CLI entry point, serve
the marker sheet from the FastAPI app `server.py` already hosts: a
browser-first path is what the phone client will use too, and a browser
can already render vector graphics at true physical size and print them
without any new dependency.

## What Changes

- Add marker-rendering routes to the FastAPI app in `server.py`: an HTML
  index listing available tags and an SVG endpoint per marker.
- Render each tag as vector SVG built directly from the ArUco bit grid
  (`cv2.aruco.generateImageMarker` at the dictionary's native
  cell-plus-border resolution, one `<rect>` per cell) rather than a
  rasterized PNG, so print scale stays exact at any print DPI.
- Accept marker `id` and `size_mm` as request parameters so any tag from
  the existing `DICT_4X4_50` dictionary (`detect.py`'s `DICTIONARY`
  constant) can be produced at any size — no dependency on
  `config/markers.toml` or a marker map, neither of which exists yet.
- Index page states the print requirement plainly ("Print at 100% / actual
  size — never Fit to page"), same caution README already gives for the
  tool-based approach, since a browser print dialog has the identical
  DPI-scaling failure mode.
- Drop `tools/gen_markers.py` from README's planned repo layout; the
  Milestones checklist item is unchanged in meaning, only in how it gets
  built. No server-side PDF generation is added for this change — a
  browser's own "Save as PDF" from the print dialog already produces a
  to-scale PDF from the same SVG.

## Capabilities

### New Capabilities
- `marker-generation`: producing correctly-sized, printable ArUco marker
  artwork (SVG) for a given marker ID and physical size from the
  project's `DICT_4X4_50` dictionary, served over HTTP for viewing and
  printing in a browser.

### Modified Capabilities
<!-- None. The existing `/cursor/move` route and CursorBackend contract
     are untouched; this adds new routes to the same FastAPI app. -->

## Impact

- New: a marker-rendering module (bit grid → SVG) and new routes
  registered on the FastAPI app in `server.py`.
- Unchanged: `detect.py`, `solve.py`, `inject.py`, the `/cursor/move`
  route and `CursorBackend` protocol. `config/markers.toml` and a marker
  map remain out of scope — this change parameterizes id/size directly,
  it does not consume a layout file.
- Dependencies: none added. `cv2.aruco` (already a dependency via
  `opencv-python-headless`) supplies the bit pattern; SVG is generated as
  plain text.
- README: "Repo layout" drops `tools/gen_markers.py`; the corresponding
  Milestones entry's implementation note updates to point at the new
  endpoint instead of a standalone tool.
