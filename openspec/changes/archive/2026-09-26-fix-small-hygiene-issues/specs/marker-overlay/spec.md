## MODIFIED Requirements

### Requirement: Printed and on-screen layouts are alternatives, not a replacement
The system SHALL let the marker layout source be selected by
configuration, and SHALL continue to support a layout loaded from a
file exactly as before. Choosing an on-screen layout SHALL NOT be
required in order to use the rest of the system. A layout source that
cannot be understood SHALL be rejected with an error that names the
accepted forms.

#### Scenario: A printed layout still works
- **WHEN** the system is configured to use a layout loaded from a file
- **THEN** it behaves exactly as it did before the overlay existed

#### Scenario: The layout source is selectable
- **WHEN** the system is configured to use an on-screen layout
- **THEN** the pipeline solves against the overlay's derived layout
  rather than a file

#### Scenario: A file source with no path
- **WHEN** the layout source is `file:` with nothing after the colon
- **THEN** the system rejects it as a layout-source error that says a
  path is needed (e.g. `file:markers.toml`) or that plain `file` selects
  the default, rather than failing on a filesystem error
