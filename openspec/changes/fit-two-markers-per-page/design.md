## Context

`src/boresight/markers.py` serves the printable sheet at `GET /markers`.
Each tag is an inline SVG in a `.marker` box with a dashed border and
`padding: size_mm * MARGIN_FRACTION` (0.25). The orientation mark and
labels are children of that same padded box, so they sit inside the
padding, about 0.4em from the tag. Horizontally the white margin is
20mm. Vertically it is about 1.5mm, followed by text. Boxes are
`inline-block` with `break-inside: avoid` and there are no explicit page
breaks. Each cut-out is about 120mm wide and 145mm tall, so only one fits
across 190mm and one down 277mm. The default sheet printed from
headless Chromium was 9 pages (measured before this change).

DICT_4X4_50 tags are a 6x6 grid: a 4x4 payload plus a one-cell black
border (`marker_grid`). ArUco needs white around that black border to
find the square's outer contour. That white area is the quiet zone, and
it is not part of the grid.

## Goals / Non-Goals

**Goals:**
- Quiet zone exactly one grid cell (`size_mm / n`, n = markerSize + 2),
  plain white, with nothing printed inside it.
- Two cut-outs per printed page for the default layout. That is 5
  printed pages including a cover, measured in a real print engine.
- The size picker's "too wide for A4" note stays correct for the new
  cut-out width.

**Non-Goals:**
- Packing more than two small tags onto a page. The user asked for two
  per page, and one tag per half page keeps the cut simple.
- Side-by-side placement. Two 80mm cut-outs are 213mm across, wider
  than A4's 190mm printable width.
- Changing the single-SVG endpoint. `marker_svg` still renders the bare
  grid. The quiet zone belongs to the sheet.

## Decisions

**Quiet zone = one cell, drawn as padding around the SVG only.** A
`.quiet` wrapper holds just the SVG, with `padding: cell mm` and a white
background. The orientation mark sits above that wrapper and the labels
below it, so no text can come within one cell of the tag. The cell size
comes from the dictionary (`markerSize + 2`), not a hard-coded 6, so the
rule stays true if the dictionary changes. Alternative: keep
`MARGIN_FRACTION` and move the labels out. Rejected because the user
asked for exactly one cell, and at 0.25 two cut-outs do not fit a page.
`MARGIN_FRACTION` is removed.

**Is one cell enough?** Checked by rasterizing IDs 0–7 from the sheet's
own `marker_grid` with exactly one cell of white, pasted on a dark,
mid-grey or black surround, with and without blur, through the repo's
`detect_markers`:
- 5, 6, 8 and 20 px per cell: every tag detected.
- Tiny tags, 3–4 px per cell (18–24 px across): some misses (23 of 96).
  A three-cell margin still misses 12 of 96 at that size, so a wider
  margin helps a little only where decode is already marginal. The
  README's decode floor (~3 px per cell) is unchanged.

This check is now a test (`test_markers.py`) at 8 px per cell. The
full sheet was also rendered to PDF, rasterized, and every tag on it
detected (see tasks 4.x).

**Fixed-height label bands in mm.** The orientation mark gets a 6mm band
above the quiet zone. The id/size line and the position line get 5mm
each below it, all `white-space: nowrap`, plus 1mm padding inside the
dashed border top and bottom. The cut-out height is then a known
function of tag size, `size + 2*cell + 18mm` (124.7mm at 80mm). Python
can decide pairing without guessing how a browser wraps text.
Alternative: `break-inside: avoid` and let the browser pair tags.
Rejected because it gives no deterministic page count to test and pairs
unevenly.

**Pairing rule.** Cut-outs are taken in sheet order. A page holds at most
two. A second cut-out joins the page only if both heights plus a 6mm gap
fit `A4_PRINTABLE_HEIGHT_MM` = 297 − 2×10 = 277mm. Two 80mm cut-outs
take 255.3mm. The largest pairable size is about 88mm, so the 100mm and
120mm presets print one per page. Each tag page is a `.page` block with
`break-before: page`. That gives explicit breaks, and the cover never
leaves a blank trailing page.

**Cover page.** The steps and the layout diagram now print, on page 1,
because they are what you need in hand while sticking tags up. The size
picker and the mismatch warning stay `noprint`. The result is five pages
for the default layout: a cover plus four pages of pairs. Alternative:
put the first pair under the one-line print instruction for 4 pages.
Rejected because that line plus a pair overflows US Letter, and the
diagram is worth a sheet.

**Print margins pinned, paper size not.** `@page { margin: 10mm }`, and
body margin 0 in print. The page size is left to the printer. A pair
(255.3mm) also fits US Letter's 259.4mm printable height, so forcing
`size: A4` would only make Letter printers scale the sheet, which is the
one thing that must never happen.

**`fits_a4` uses the new width**, `size + 2*cell` ≤ 190mm. 140mm now
fits across, so the comment on `SIZE_PRESETS_MM` is updated. The
presets are unchanged.

**Terminology fix.** `marker_grid`'s docstring called the one-cell black
border the "quiet border". It is the black marker border. The quiet zone
is the white area outside it. Corrected, since this change depends on
the distinction.

## Risks / Trade-offs

- [Less white margin means less tolerance for a sloppy cut into the
  quiet zone] → The sheet says to cut on the dashed line, outside the
  labels. Cutting there always leaves the full cell of white.
- [Label text outside the quiet zone is extra contrast near the tag] →
  Verified by detecting every tag on the rasterized PDF page, labels
  included.
- [Browser default margins or "fit to page" still override the CSS] →
  The instruction to print at 100% stays first on the page. The pair
  leaves 21mm of slack on A4 and about 4mm on Letter.
- [Mixed-size layouts with wide labels] → Labels are `nowrap`, so a
  very small tag's box may be wider than its quiet zone. Its height,
  which is what pairing depends on, is unaffected.
