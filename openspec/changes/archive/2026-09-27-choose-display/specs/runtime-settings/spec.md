## ADDED Requirements

### Requirement: The display is a view preference that can change live
The view preferences SHALL include `display`, the chosen display's name
(empty for the primary display), settable in the file, with `--display`,
and over the API. `GET /displays` SHALL list the machine's displays with
each one's name, desktop rectangle and whether it is primary, and the
one in effect. `POST /display` SHALL apply a display to the cursor and
the overlay without a restart; a display that cannot be applied SHALL be
refused with a reason and change nothing. A display named in the file or
flag that cannot be applied at startup SHALL stop the server with that
reason. The chosen display SHALL be saved with the other view
preferences.

#### Scenario: Listing displays
- **WHEN** a client requests `GET /displays` on a machine with two
  monitors
- **THEN** both are listed with name, rectangle and primary flag, and
  the one in effect is named

#### Scenario: Changing the display live
- **WHEN** a client posts a listed display name to `/display`
- **THEN** the cursor and any on-screen markers move to that display and
  the response names it as in effect

#### Scenario: The choice is saved
- **WHEN** a client changes the display and saves settings
- **THEN** the file's `view.display` holds that name
