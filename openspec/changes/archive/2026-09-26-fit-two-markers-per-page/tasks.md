## 1. Quiet zone

- [x] 1.1 Add `quiet_zone_mm(size_mm)` (one grid cell, from the dictionary's marker size plus border), remove `MARGIN_FRACTION`, and fix the "quiet border" wording in docstrings; verify with a unit test that it is `size_mm / 6` for DICT_4X4_50
- [x] 1.2 Restructure `_tag` so the SVG sits alone in a white `.quiet` box padded by one cell, with the orientation mark above it and the labels below it in fixed-height mm bands; verify with a route test that the padding equals one cell and no label is inside `.quiet`
- [x] 1.3 Add a detection test that rasterizes tags with exactly a one-cell white margin on a dark surround and checks `detect_markers` decodes each id

## 2. Pagination

- [x] 2.1 Add `cutout_height_mm` and `paginate` (at most two per page, pair only if both plus the gap fit 277mm), with unit tests for 80mm pairs, oversized singles and odd counts
- [x] 2.2 Emit each page as a `.page` block with `break-before: page`, set `@page { margin: 10mm }`, drop the body margin in print, and print the steps plus diagram as the cover; verify with a route test that the default sheet has 4 tag pages of 2 (5 printed pages)
- [x] 2.3 Update `fits_a4` to the one-cell width and its comment; verify the picker test still flags only sizes over 142.5mm (none of the presets up to 120mm)

## 3. Instructions

- [x] 3.1 Update the sheet's printing instructions (two per page, cut on the dashed line, the white border is one cell and must stay white) and README's printing note; verify the existing instruction tests still pass

## 4. Verification

- [x] 4.1 Render the default sheet to PDF with headless Chromium on Letter and on A4; verify with `pdfinfo` that both are 5 pages
- [x] 4.2 Rasterize the A4 PDF with `pdftoppm` and run `detect_markers` on each page; verify every id 0–7 is found, and that no cut-out crosses a page edge
- [x] 4.3 Run `uv run pytest -q`, `uv run ruff check` and `uv run ruff format --check`, and `openspec validate fit-two-markers-per-page`; all pass
