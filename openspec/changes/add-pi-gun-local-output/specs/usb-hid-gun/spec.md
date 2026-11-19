# Spec Delta

## ADDED Requirements

### Requirement: The gun installs like the rest of the project
The gun SHALL install with the project's normal Python packaging
commands, the same on a Pi as on any other system. No script in the
project SHALL install a system package. The documentation SHALL list
every system dependency the user installs by hand, for each output and
each camera source.

#### Scenario: Installing on a Pi
- **WHEN** a user follows the guide on a Pi
- **THEN** the gun is installed with the same `uv sync` command, with
  extras, used on other systems

#### Scenario: No package manager is run
- **WHEN** any script in `deploy/` runs
- **THEN** it runs no system package manager

### Requirement: The camera is a USB webcam or a Pi CSI camera
The gun SHALL read `[camera] source`:
- **`webcam`** opens a camera through OpenCV by index or path.
- **`rpicam`** reads raw frames from `rpicam-vid`.
- **`picamera2`** uses the Picamera2 library.

Each SHALL pass the gun greyscale frames of the configured size. An
unknown source SHALL stop the gun at startup with an error naming the
accepted values.

#### Scenario: A USB webcam on any system
- **WHEN** `source` is `webcam` and a camera is attached
- **THEN** the gun aims from that camera's frames, in greyscale

#### Scenario: A CSI camera through rpicam-vid
- **WHEN** `source` is `rpicam` on a Pi with a CSI camera
- **THEN** the gun runs `rpicam-vid` with raw output and aims from its
  frames

#### Scenario: rpicam-vid stops
- **WHEN** `rpicam-vid` exits or cannot be started
- **THEN** the gun stops with the camera failure and its error output
  logged, releasing a held button

#### Scenario: A size rpicam-vid would pad is refused
- **WHEN** `source` is `rpicam` and the width is not a multiple of 64,
  or the height not a multiple of 16
- **THEN** the gun exits at startup naming the size and the rule

### Requirement: The camera source is chosen automatically by default
With `source` set to `auto`, which is the default, the gun SHALL use
`rpicam` when `rpicam-vid` is on the path, and `webcam` otherwise.

#### Scenario: Auto picks the CSI camera on a Pi
- **WHEN** `source` is `auto` and `rpicam-vid` is on the path
- **THEN** the `rpicam` source is used

#### Scenario: Auto picks a webcam elsewhere
- **WHEN** `source` is `auto` and there is no `rpicam-vid`
- **THEN** the `webcam` source is used

## MODIFIED Requirements

### Requirement: Camera exposure is pinned
The gun SHALL turn off the camera's automatic exposure, gain and white
balance and apply the configured fixed values, as far as the camera
source allows, before aiming. It SHALL log the values, the resolution
and the frame rate actually applied. A webcam that does not take a
fixed exposure SHALL be reported in the log, rather than silently left
on automatic.

#### Scenario: Fixed exposure is applied at startup
- **WHEN** the gun starts the camera
- **THEN** automatic exposure and gain are off, the configured values
  apply and are logged

#### Scenario: A webcam ignores the fixed exposure
- **WHEN** a webcam reports that automatic exposure is still on after
  the gun asked for manual exposure
- **THEN** a warning names the camera and says exposure is not fixed

### Requirement: The Pi presents as a USB absolute mouse
With the `usb` output, which is the default, the gun SHALL appear to the
host over the Pi's USB device port as a standard HID mouse reporting
absolute positions and a primary button, requiring no driver and no
software on the host. The position the aim pipeline produces, normalized
0..1 across the display, SHALL map to the full range of the HID axes, so
the host scales it to its own display without the Pi knowing the
resolution.

#### Scenario: The host sees a mouse
- **WHEN** the Pi is connected to a host by its device port and the gun
  is running with the `usb` output
- **THEN** the host enumerates a HID pointing device with no driver
  installation

#### Scenario: A solved aim moves the host cursor to the matching place
- **WHEN** the pipeline solves an aim at the centre of the display
- **THEN** the HID report carries the middle of both axes, and 0 and 1
  map to the axes' minimum and maximum

### Requirement: The gun starts at boot and sets up its own USB identity
For the `usb` output, the project SHALL provide a setup script that
enables USB device mode, creates the HID function, and installs a
service that starts the already-installed gun at power-up, restarts it
on failure and runs it without a login. The script SHALL install no
packages. The device SHALL identify itself with a configurable vendor
and product name and serial, and SHALL reconnect to the host without a
reboot if the cable is unplugged and replugged.

#### Scenario: The gun works after a power cycle
- **WHEN** a Pi set up for the `usb` output is powered from the host's
  USB port
- **THEN** the host sees the mouse and aiming works with no command

#### Scenario: Replugging the cable
- **WHEN** the USB cable is unplugged and plugged back in
- **THEN** the host sees the mouse again with no reboot of the Pi
