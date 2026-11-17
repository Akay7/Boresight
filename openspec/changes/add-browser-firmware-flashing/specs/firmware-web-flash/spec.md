# Spec Delta

## Purpose

Lets a person put Boresight firmware on an ESP32-CAM from a desktop
browser over the USB-serial adapter, with no toolchain, container or
command-line flasher installed, using either the published generic image
or a build from their own checkout.

## ADDED Requirements

### Requirement: A browser can flash a complete image over the adapter
The project SHALL provide a flashing page that writes a complete
firmware image (bootloader, partition table, update bookkeeping and
application) to an ESP32-CAM through a USB-serial adapter, using the
browser's Web Serial interface, and shows progress and the outcome. It
SHALL NOT require anything installed on the computer beyond a browser
with Web Serial.

#### Scenario: A board is flashed from the browser
- **WHEN** a board in download mode is connected through the adapter and
  the user chooses an image and its serial port on the flashing page
- **THEN** the page writes the image, reports progress and success, and
  the board runs that firmware after the jumper is removed and RST is
  pressed

### Requirement: The page explains what the adapter cannot do
The flashing page SHALL tell the user, before connecting, to fit the
IO0-to-GND jumper and press RST, since the adapter cannot put an
ESP32-CAM into download mode itself, and to remove the jumper and press
RST afterwards. When the board does not answer, it SHALL say that the
board is probably not in download mode rather than only report a
failure.

#### Scenario: A board not in download mode is explained
- **WHEN** the user connects to a board that is running its firmware
  rather than waiting in download mode
- **THEN** the page reports that the board did not answer and repeats
  the jumper-and-RST steps

### Requirement: Browsers without Web Serial are told so
In a browser without Web Serial, or on a page not served from a secure
context, the flashing page SHALL say that flashing needs desktop Chrome
or Edge, opened over HTTPS or on `localhost`, and SHALL offer the image
files for download instead of a flash button.

#### Scenario: Firefox gets an explanation and the files
- **WHEN** the flashing page is opened in a browser without Web Serial
- **THEN** it explains which browsers can flash and links the image
  files for download

### Requirement: Flashing keeps the device's settings unless asked not to
Flashing from the page SHALL leave the settings stored on the device in
place, unless the user explicitly chooses to erase the whole device
first, which the page SHALL offer with a statement that it also erases
the stored settings.

#### Scenario: Reflashing keeps the stored settings
- **WHEN** a board with settings stored through setup mode is flashed
  from the page without choosing to erase
- **THEN** it starts with the same stored settings as before

#### Scenario: Erasing is explicit
- **WHEN** the user chooses to erase the device before flashing
- **THEN** the stored settings are gone and the board starts in setup
  mode

### Requirement: The site served locally offers this checkout's build
When the project site is served locally, its flashing page SHALL offer
the device firmware last built in the checkout it is served from, naming
its version and build time. When no such build exists, the page SHALL
say how to build one and point to the published flashing page. The
Boresight server SHALL NOT serve the flashing page or firmware files:
flashing and aiming are separate programs.

#### Scenario: The local build is offered
- **WHEN** the device firmware has been built in this checkout and the
  site is served locally
- **THEN** its flashing page offers that build, naming its version and
  build time

#### Scenario: No local build
- **WHEN** the site is served locally from a checkout where the device
  firmware has not been built
- **THEN** the flashing page says how to build it and points to the
  published flashing page

#### Scenario: The Boresight server does not flash
- **WHEN** `/flash/` is requested from a running Boresight server
- **THEN** no flashing page or firmware file is served

### Requirement: A generic image is built and published
The project's CI SHALL build a device image with no Wi-Fi network,
password, server address or token compiled in, which boots into setup
mode. It SHALL build it on every push, SHALL publish it as a release
download for every version tag, and the published flashing page SHALL
offer the latest released image, with its version.

#### Scenario: The published image needs no rebuild to use
- **WHEN** the published image is flashed onto a board
- **THEN** the board boots into setup mode and can be configured there,
  with no build of its own

#### Scenario: The published image carries no secrets
- **WHEN** the published image's files are inspected
- **THEN** they contain no Wi-Fi password, token or server certificate
