## ADDED Requirements

### Requirement: One-cell quiet zone with labels outside it
Each tag on the printable marker sheet SHALL be surrounded by a plain
white margin exactly one cell of that tag's grid wide on every side. The
grid counts the dictionary's payload bits plus the tag's black border, so
it is `size_mm / 6` for a 4x4 dictionary. The orientation mark and
every label (id, size, position) SHALL be printed outside that white
margin, never inside it. A tag rendered with only this margin SHALL
still be found by the system's own detector.

#### Scenario: Margin is one grid cell
- **WHEN** the sheet renders a tag of `size_mm` for a dictionary whose
  grid, border included, is `n` cells across
- **THEN** the white margin around the tag is `size_mm / n` millimetres
  on each side

#### Scenario: Labels stay out of the quiet zone
- **WHEN** the sheet renders a tag with its orientation mark and labels
- **THEN** none of that text is inside the one-cell white margin

#### Scenario: A one-cell margin is enough to detect the tag
- **WHEN** a tag is rasterized at a decodable resolution with exactly a
  one-cell white margin, against a darker surround
- **THEN** the detector finds the tag and decodes its id

### Requirement: Two cut-outs per printed page
The printable marker sheet SHALL group cut-outs onto printed pages with
explicit page breaks, two per page, stacked vertically, whenever both
fit within an A4 page's printable height (297mm less 10mm print margins
top and bottom) at 100% scale. A cut-out that would not fit beside the
next one SHALL print on a page of its own. The steps and the layout
diagram SHALL print on a first page of their own, before the tag pages.

#### Scenario: The default layout prints on five pages
- **WHEN** a client requests the marker sheet page with no id or size
  parameters (eight 80mm tags)
- **THEN** the page lays the tags out on four printed pages of two tags
  each, after one instructions page, for five printed pages in total

#### Scenario: An oversized tag gets its own page
- **WHEN** the sheet is requested at a size where two cut-outs do not fit
  one page's printable height
- **THEN** each of those cut-outs is laid out on its own printed page

#### Scenario: An odd tag count leaves the last page with one tag
- **WHEN** the sheet is requested with three pairable tag ids
- **THEN** the first tag page holds two cut-outs and the second holds one
