## ADDED Requirements

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
