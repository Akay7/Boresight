# esp32-cam-ota Specification

## Purpose
Lets the ESP32-CAM's firmware be replaced over Wi-Fi from its setup
page, with no adapter, while keeping the stored settings and falling
back by itself when a new firmware does not start.

## Requirements

### Requirement: Setup mode accepts a firmware upload
The setup page SHALL let the user upload a firmware application file.
The device SHALL write it to the application slot it is not running
from, while the running firmware stays untouched, and on success SHALL
confirm on the page and restart into the new firmware.

#### Scenario: An update is installed from the setup page
- **WHEN** a valid application image for a board is uploaded on the
  setup page
- **THEN** the page confirms the update, the device restarts, and its
  boot log and `hello` report the new firmware's version

#### Scenario: The running firmware is not touched while uploading
- **WHEN** an upload is interrupted halfway
- **THEN** the device keeps running the firmware it had, which still
  boots after a power cycle

### Requirement: Only a Boresight firmware for this kind of device is accepted
The device SHALL refuse an upload that is not a complete, valid
application image, that is not a Boresight camera firmware, or that was
built for the other kind of target (an emulator image on a board, a
board image in the emulator). It SHALL say on the page why it was
refused, and SHALL leave the running firmware as the one that boots.

#### Scenario: A file that is not firmware is refused
- **WHEN** an arbitrary file is uploaded
- **THEN** the page says it is not a firmware image and the device keeps
  its firmware

#### Scenario: An emulator image is refused by a board
- **WHEN** an emulator build is uploaded to a board
- **THEN** the page says it is an emulator build and the device keeps its
  firmware

#### Scenario: A truncated image is refused
- **WHEN** a valid image is uploaded cut short
- **THEN** the page says the image is incomplete and the device keeps its
  firmware

### Requirement: Settings survive an update
An update over Wi-Fi, and the one-time move to the two-slot layout, SHALL
leave the settings stored on the device in place.

#### Scenario: Stored settings are kept across an update
- **WHEN** a device with settings stored through setup mode is updated
  over Wi-Fi
- **THEN** it starts the new firmware with the same stored settings

### Requirement: A firmware that does not start falls back
After an update, the new firmware SHALL be kept only once it has started
and reached normal operation or setup mode. If it resets before that,
the device SHALL return to the previous firmware by itself, and SHALL log
that it did.

#### Scenario: A firmware that crashes at boot is rolled back
- **WHEN** an uploaded firmware resets before reaching normal operation
  or setup mode
- **THEN** the next boot runs the previous firmware and its log says the
  update was rolled back

#### Scenario: A firmware that starts is kept
- **WHEN** an uploaded firmware reaches normal operation
- **THEN** it is marked good and still boots after a power cycle
