## ADDED Requirements

### Requirement: The phone shows whether it drives the cursor
The client SHALL display, alongside its other telemetry, whether this
phone currently drives the cursor, another client does, or nobody does,
from the `cursor` field of the server's stats messages, so a player
whose aim is not moving the cursor can see why.

#### Scenario: Another client has the cursor
- **WHEN** the server's stats say `cursor` is `other`
- **THEN** the page shows that another device is driving the cursor
