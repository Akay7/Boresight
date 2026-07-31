## 1. Marker SVG rendering

- [x] 1.1 Add `src/boresight/markers.py` with a function that builds a
      marker's bit grid via `cv2.aruco.generateImageMarker` at the
      dictionary's native resolution (reuse `detect.py`'s `DICTIONARY`
      constant) and validates `marker_id` against the dictionary's valid
      range.
- [x] 1.2 Add a function that renders that bit grid to an SVG string:
      one `<rect>` per cell, `viewBox` sized to the grid, `width`/
      `height` set to `"{size_mm}mm"`.
- [x] 1.3 Validate `size_mm` is positive; raise on invalid input.
- [x] 1.4 Unit tests: correct grid dimensions for `DICT_4X4_50` (6x6),
      SVG `width`/`height` match requested `size_mm`, invalid id and
      invalid size both raise.

## 2. HTTP routes

- [x] 2.1 Add an `APIRouter` in `src/boresight/markers.py` (or a
      sibling module) with `GET /markers/{marker_id}.svg` accepting a
      `size_mm` query parameter, returning `image/svg+xml`.
- [x] 2.2 Add `GET /markers` returning an HTML page that embeds the
      requested `ids` (comma-separated query param, default `0-7`) at
      `size_mm` (default `80`), with visible print-at-100%/actual-size
      instructions.
- [x] 2.3 Include the new router in `create_app()` in `server.py`.
- [x] 2.4 Route tests via FastAPI's test client: valid single-marker
      request returns 200 SVG with expected mm dimensions; out-of-range
      id and non-positive `size_mm` return 4xx; default sheet request
      returns the reference 8-marker/80mm set; explicit `ids`/`size_mm`
      override the default; page body contains the print instruction
      text.

## 3. Docs

- [x] 3.1 Update README's "Repo layout" to drop `tools/gen_markers.py`
      and reflect the new routes.
- [x] 3.2 Update the "Generate and print markers at verified physical
      size" milestone note to point at the new endpoint.
