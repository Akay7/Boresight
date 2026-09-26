## ADDED Requirements

### Requirement: Replay uses a sequence's own layout when it carries one
The replay entry point SHALL, when no layout is explicitly given, use the
layout file stored in the replayed directory if one is present, and the
shipped layout otherwise. A recording is only reproducible against the
layout it was captured with, which need not be the shipped one.

#### Scenario: A recording replays against its own layout
- **WHEN** a directory holding a layout file is replayed without an
  explicit layout
- **THEN** its frames are solved against that directory's layout

#### Scenario: An explicit layout still wins
- **WHEN** a layout is given explicitly
- **THEN** it is used even if the directory holds its own
