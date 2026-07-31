# marker-map Specification

## Purpose
TBD - created by archiving change add-aim-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Marker layout is loaded from configuration
The system SHALL load the physical marker layout from a TOML file
declaring the active display size (`screen_width_mm`,
`screen_height_mm`) and an array of `[[marker]]` entries, each carrying
an integer `id`, the marker's top-left corner position as `x` and `y`
in screen millimetres, and its printed edge length as `size_mm`. Markers
SHALL be permitted to differ in `size_mm` from one another, so a future
inner ring of smaller tags needs no format change.

#### Scenario: A well-formed layout file loads
- **WHEN** a layout file declaring a screen size and one or more marker
  entries is loaded
- **THEN** the loader returns a marker map exposing the screen size in
  millimetres and every declared marker, keyed by ID

#### Scenario: Markers of differing sizes coexist
- **WHEN** a layout file declares two markers with different `size_mm`
  values
- **THEN** each marker's corners are derived from its own `size_mm`,
  not from a single layout-wide size

### Requirement: Marker positions use a screen-relative coordinate system
The marker map SHALL interpret marker coordinates in millimetres with
its origin at the top-left corner of the active display area, `x`
increasing rightwards and `y` increasing downwards. Negative coordinates,
and coordinates exceeding the declared screen size, SHALL be accepted and
SHALL denote markers sitting on the bezel outside the active panel, which
is where the layout puts them by design.

#### Scenario: Bezel markers outside the panel are accepted
- **WHEN** a layout file declares a marker at a negative `x` and `y`, and
  another at coordinates beyond `screen_width_mm` and `screen_height_mm`
- **THEN** both load without error and retain the declared coordinates

### Requirement: Marker map resolves an ID to its screen-plane corners
The marker map SHALL return, for a given marker ID, that marker's four
corners as screen-millimetre points ordered clockwise from the top-left
corner, matching the corner order the project's marker detector reports,
so corresponding entries of the two sequences describe the same physical
corner and can be paired positionally.

#### Scenario: Corners are derived from position and size
- **WHEN** the corners of a marker declared at `(x, y)` with edge length
  `s` are requested
- **THEN** the map returns exactly `(x, y)`, `(x + s, y)`,
  `(x + s, y + s)`, `(x, y + s)`, in that order

#### Scenario: An unknown marker ID is reported as absent
- **WHEN** corners are requested for an ID the layout does not declare
- **THEN** the map reports the ID as absent rather than raising an
  unhandled lookup error or fabricating a position

### Requirement: Invalid layout files are rejected at load time
The loader SHALL reject a malformed layout rather than producing a map
that fails later during solving. It SHALL raise a clear, identifying
error when a required field is missing, when the same marker `id` is
declared more than once, or when the declared screen dimensions or a
marker's `size_mm` are not positive.

#### Scenario: Duplicate marker IDs are rejected
- **WHEN** a layout file declares two `[[marker]]` entries with the same
  `id`
- **THEN** loading fails with an error naming the duplicated ID

#### Scenario: A missing required field is rejected
- **WHEN** a layout file omits `screen_width_mm`, or a marker entry omits
  any of `id`, `x`, `y`, or `size_mm`
- **THEN** loading fails with an error naming the missing field

#### Scenario: Non-positive dimensions are rejected
- **WHEN** a layout file declares a zero or negative screen dimension, or
  a marker with a zero or negative `size_mm`
- **THEN** loading fails with an error identifying the offending value

### Requirement: Shipped layout matches the rendered reference scene
The repository SHALL ship a layout file describing the reference marker
layout, and that file SHALL agree with the layout recorded in the
manifests of the checked-in rendered fixtures — same screen size, same
marker IDs, same positions, same sizes — so the configuration the
software ships with and the scene the tests are validated against cannot
diverge without a test failing.

#### Scenario: Shipped layout and fixture manifest agree
- **WHEN** the shipped layout file and a rendered fixture's manifest are
  compared
- **THEN** they declare the same screen dimensions and the same set of
  marker IDs at the same positions with the same sizes
