## Why

The printable marker sheet puts every cut-out on its own page: the
default eight 80mm tags come out as 9 printed pages, most of each one
blank. The white margin around a tag is a quarter of its edge (20mm at
80mm), which is more than the detector needs, and it is the reason two
cut-outs do not fit on one A4 page. The margin is also not what the
sheet claims. The "TOP" mark and the id labels sit inside the padded box
only a millimetre or so from the tag, so the quiet zone above and below
the tag is not white at all.

## What Changes

- The white margin (quiet zone) around each tag becomes exactly one cell
  of the tag's own grid (dictionary bits plus the black border, so
  `size_mm / 6` for DICT_4X4_50). It is 13.3mm for an 80mm tag, down
  from 20mm.
- The orientation mark and the labels (id, size, where it goes) move
  outside that white margin on every side. Nothing is printed inside the
  quiet zone.
- The sheet groups cut-outs two per printed page, stacked vertically,
  with explicit page breaks. A cut-out too tall to share a page with the
  next one (e.g. 100mm and 120mm tags) prints on its own page.
- The steps and the layout diagram now print on page 1, which acts as a
  cover page. Before, they were screen-only. The default layout
  therefore prints as 5 pages (cover plus 4 pages of two tags) instead
  of 9. The size picker and the layout-mismatch warning stay
  screen-only.
- The sheet sets 10mm print margins. The "too wide for A4" note in the
  size picker is recomputed from the one-cell margin.
- The printing instructions (sheet and README) say where to cut, that the
  white border is one cell wide and must stay white, and that it prints
  two tags to a page.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `marker-generation`: adds requirements for the one-cell quiet zone with
  labels outside it, and for pairing cut-outs two per printed page.

## Impact

- `src/boresight/markers.py`: tag cut-out markup and CSS, pagination,
  `fits_a4`, sheet instructions.
- `tests/test_markers.py`, `tests/test_marker_routes.py`: new tests for
  quiet-zone width, pairing and page count, and detection with a
  one-cell margin.
- `README.md`: the printing note next to the reference layout.
- No API or query-parameter changes.
