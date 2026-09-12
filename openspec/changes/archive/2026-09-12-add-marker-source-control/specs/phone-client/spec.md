## ADDED Requirements

### Requirement: The client can choose the marker source
The client SHALL let the person holding the phone choose between
printed and on-screen markers, and SHALL show which is currently
active. The choice belongs here rather than only at the PC because that
is where the person is: standing at the display with the camera, not at
the keyboard.

#### Scenario: The current source is visible on the phone
- **WHEN** the client page is open
- **THEN** it shows whether printed or on-screen markers are currently
  active

#### Scenario: Choosing a source takes effect without reconnecting
- **WHEN** the person selects the other marker source while streaming
- **THEN** the selection is applied and the displayed state updates,
  without the video connection being restarted

### Requirement: A failed marker source selection is shown, not swallowed
Where selecting a marker source fails, the client SHALL display the
reason given by the server and SHALL continue to show the source that
is actually active. It SHALL NOT show the requested source as active
when it is not.

#### Scenario: An overlay that refused to start says so on the phone
- **WHEN** on-screen markers are selected and the server reports that
  the overlay could not start
- **THEN** the page shows that explanation and continues to show printed
  markers as the active source
