## ADDED Requirements

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
