# usb-hid-gun Specification

## Purpose
Lets a Raspberry Pi Zero 2 W act as a complete light gun: it aims with
its own camera and presents itself to any host as a USB mouse, with no
Boresight software or network on the host.

## Requirements

### Requirement: The Pi presents as a USB absolute mouse
The gun SHALL appear to the host over the Pi's USB device port as a
standard HID mouse reporting absolute positions and a primary button,
requiring no driver and no software on the host. The position the
aim pipeline produces, normalized 0..1 across the display, SHALL map to
the full range of the HID axes, so the host scales it to its own
display without the Pi knowing the resolution.

#### Scenario: The host sees a mouse
- **WHEN** the Pi is connected to a host by its device port and the gun
  is running
- **THEN** the host enumerates a HID pointing device with no driver
  installation

#### Scenario: A solved aim moves the host cursor to the matching place
- **WHEN** the pipeline solves an aim at the centre of the display
- **THEN** the HID report carries the middle of both axes, and 0 and 1
  map to the axes' minimum and maximum

### Requirement: Aiming reuses the existing pipeline unchanged
The gun SHALL derive its aim from camera frames with the same detection,
marker lookup, homography solve, lens correction, zero correction,
smoothing and aim-hold as the server, so the same marker layout and the
same frames yield the same aim point.

#### Scenario: Recorded frames give the server's positions
- **WHEN** the gun processes a recorded frame sequence with a layout
- **THEN** the positions it emits equal those the server's replay of the
  same frames and layout produces

#### Scenario: Unsolved frames emit nothing new
- **WHEN** no frame solves
- **THEN** no position is reported beyond what the aim-hold behavior
  allows

### Requirement: The trigger holds the primary button
The gun SHALL read a push button on a GPIO, wired active-low with the
internal pull-up, debounced, and report the primary button down on press
and up on release, so a tap is a click and holding while aiming is a
drag. A pending hold SHALL be released if the gun stops or loses its
camera.

#### Scenario: Press and release with contact bounce
- **WHEN** the button is pressed, held and released, with contact bounce
  on both edges
- **THEN** the host sees exactly one button down and then one button up

#### Scenario: Stopping releases the button
- **WHEN** the gun exits or its camera fails while the button is held
- **THEN** a button-up is sent before it stops

### Requirement: Configuration and calibration come from files
The gun SHALL read its marker layout, camera settings, pins and tuning
from files on the device, and SHALL use an optional lens calibration and
optional zero from files in the formats the server writes, so files made
on the server can be copied to the Pi. With no lens file it SHALL apply
no lens correction; with no zero file, none. Invalid files SHALL stop the
gun at startup with the reason on the log and status LED.

#### Scenario: A server-written lens file is used
- **WHEN** a lens calibration file the server wrote for this camera is
  configured
- **THEN** the gun corrects distortion with it

#### Scenario: An invalid layout is refused
- **WHEN** the marker layout file is invalid
- **THEN** the gun does not start aiming and reports why

### Requirement: Camera exposure is pinned
The gun SHALL turn off the camera's automatic exposure and gain and
apply configured fixed values before aiming, and log the values, the
resolution and the frame rate actually applied.

#### Scenario: Fixed exposure is applied at startup
- **WHEN** the gun starts the camera
- **THEN** automatic exposure and gain are off, the configured values
  apply and are logged

### Requirement: Stale frames are never processed late
The gun SHALL process only the newest captured frame and SHALL drop any
frame that arrives while it is still processing the previous one, rather
than build a backlog.

#### Scenario: Slow processing drops frames instead of lagging
- **WHEN** processing takes longer than the frame interval
- **THEN** frames are dropped and counted, and the delay between capture
  and emission does not grow

### Requirement: State is visible without a screen
The gun SHALL show on a status LED, with distinguishable patterns, at
least: starting, searching with no solved frame, aiming with the latest
frame solved, and an error. It SHALL work with no LED configured, and
SHALL log the frame rate, solve rate and dropped-frame count at least
every few seconds.

#### Scenario: Losing the markers changes the indication
- **WHEN** the gun is aiming and frames stop solving
- **THEN** the LED switches from the aiming pattern to the searching
  pattern

### Requirement: Pins are validated at startup
The gun SHALL refuse at startup a trigger or LED pin that is not a usable
GPIO on the 40-pin header or that is assigned to both, naming the pin on
the log and status LED, before it presents any HID device.

#### Scenario: A duplicate pin is refused
- **WHEN** the trigger and the LED are configured on the same pin
- **THEN** the gun reports it and does not start

### Requirement: The gun starts at boot and sets up its own USB identity
The project SHALL provide an installer that enables USB device mode,
creates the HID function, and installs a service that starts the gun at
power-up, restarts it on failure and runs it without a login. The device
SHALL identify itself with a configurable vendor and product name and
serial, and SHALL reconnect to the host without a reboot if the cable is
unplugged and replugged.

#### Scenario: The gun works after a power cycle
- **WHEN** an installed Pi is powered from the host's USB port
- **THEN** the host sees the mouse and aiming works with no command

#### Scenario: Replugging the cable
- **WHEN** the USB cable is unplugged and plugged back in
- **THEN** the host sees the mouse again with no reboot of the Pi

### Requirement: The gun runs without a Pi
The program SHALL provide a mode that replaces the camera with a
recorded video or frame sequence, the GPIO with injected button levels
and the HID device with a recording sink, running the otherwise unchanged
capture, aim and output paths, so it can be tested on an ordinary
computer.

#### Scenario: Fixture frames produce the expected reports
- **WHEN** the gun runs in this mode on the project's fixture frames
- **THEN** the reports it emits are those the server replay produces for
  the same frames, and an injected press and release produce one button
  down and one up
