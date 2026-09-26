# marker-generation Specification

## Purpose
Renders ArUco markers as print-ready SVG at an exact physical size,
singly and as printable sheets, served over HTTP.

## Requirements

### Requirement: Single marker SVG rendering
The system SHALL serve a single ArUco marker as a vector SVG image for a
caller-specified marker id and physical size, rendered from the same
dictionary `detect.py` uses to decode markers, so any tag served here is
guaranteed detectable.

#### Scenario: Valid id and size returns an SVG
- **WHEN** a client requests a marker with an id within the dictionary's
  valid range and a positive `size_mm`
- **THEN** the system returns a `200` response with content type
  `image/svg+xml` whose document dimensions are the requested `size_mm`

#### Scenario: Marker id out of range is rejected
- **WHEN** a client requests a marker id outside the dictionary's valid
  range (e.g. negative, or beyond the dictionary's maximum id)
- **THEN** the system returns a `4xx` error and renders no image

#### Scenario: Non-positive size is rejected
- **WHEN** a client requests `size_mm` that is zero or negative
- **THEN** the system returns a `4xx` error and renders no image

### Requirement: Printable marker sheet page
The system SHALL serve an HTML page that embeds one or more markers at
true physical size and states plainly that the page must be printed at
100%/actual size rather than scaled to fit the page.

#### Scenario: Default request returns the reference marker set
- **WHEN** a client requests the marker sheet page with no id or size
  parameters
- **THEN** the system returns a `200` HTML page embedding the reference
  layout's marker ids at the reference size (README's 8 markers at 80mm)

#### Scenario: Explicit ids and size override the default
- **WHEN** a client requests the marker sheet page with an explicit list
  of marker ids and a `size_mm` value
- **THEN** the system returns a `200` HTML page embedding exactly those
  markers at that size

#### Scenario: Page states the print-scale requirement
- **WHEN** a client loads the marker sheet page
- **THEN** the page's visible content includes an instruction to print
  at 100%/actual size and not to use a "fit to page" print option

### Requirement: Physical size accuracy
Generated marker artwork SHALL be exact vector output — one shape per
dictionary bit cell, including the dictionary's quiet border — with
document dimensions expressed in real-world millimeter units, so that
print scale is not dependent on any rasterization DPI chosen by this
system.

#### Scenario: SVG carries physical units matching the request
- **WHEN** a marker SVG is generated for a given `size_mm`
- **THEN** the SVG's `width` and `height` attributes are expressed in
  millimeters and equal the requested `size_mm`

#### Scenario: No rasterization step in the render path
- **WHEN** a marker SVG is generated
- **THEN** each cell of the dictionary's bit grid (including its border)
  is emitted as its own vector shape rather than sampled from a
  fixed-resolution raster image

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

### Requirement: ChArUco calibration board
The system SHALL serve a ChArUco calibration board as a vector SVG, with
one shape per run of black pixels of the board's exact pixel pattern
and document dimensions in millimetres, and SHALL serve an HTML page
that shows the board to be printed or displayed full-screen, with brief
instructions for collecting calibration views. The board's markers
SHALL come from a different ArUco dictionary from the aim markers, so
the aim detector does not report them as layout markers. The board's
physical size SHALL NOT matter to calibration, and the page SHALL say
so.

#### Scenario: The board SVG is served at a requested width
- **WHEN** a client requests the board SVG with a positive width in
  millimetres
- **THEN** the system returns `image/svg+xml` whose width is that many
  millimetres and whose height keeps the board's aspect ratio

#### Scenario: Non-positive width is rejected
- **WHEN** a client requests the board SVG with a zero or negative width
- **THEN** the system returns a `4xx` error

#### Scenario: The rendered board is detected by the calibration detector
- **WHEN** the board is rasterised at a decodable resolution
- **THEN** the calibration detector finds all of its inner corners

#### Scenario: The aim detector ignores the board
- **WHEN** the aim marker detector is run on the rasterised board
- **THEN** it reports no markers

#### Scenario: The board page links from the marker sheet
- **WHEN** a client loads the marker sheet page
- **THEN** it contains a link to the calibration board page
