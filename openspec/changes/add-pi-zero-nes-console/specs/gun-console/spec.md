# Spec Delta

## Purpose

Lets the Raspberry Pi Zero 2 W gun be a complete light-gun console. It
runs a NES game on a TV through its own HDMI output, draws the markers
beside the game, and plays the emulated Zapper with its own camera aim
and trigger, with no other computer involved.

## ADDED Requirements

### Requirement: The gun runs in USB mode or console mode
The gun SHALL read its mode from its configuration file. In `usb` mode
it behaves as the USB absolute mouse, with no change. In `console` mode
it runs the game on its HDMI output and presents no USB mouse. Without a
`mode`, it SHALL run in `usb` mode. Any other value SHALL stop it at
startup, with an error that names the accepted values.

#### Scenario: No mode keeps today's behaviour
- **WHEN** the configuration file has no `mode`
- **THEN** the gun starts as a USB mouse exactly as before

#### Scenario: Console mode starts the game instead of the mouse
- **WHEN** `mode` is `console`
- **THEN** the game is shown on the HDMI output
- **AND** no USB HID gadget is configured

#### Scenario: Unknown mode is refused
- **WHEN** `mode` is any value other than `usb` or `console`
- **THEN** the gun exits at startup with an error naming `usb` and
  `console`

### Requirement: A NES game runs full screen at full speed
In console mode the gun SHALL run a NES ROM at the game's native frame
rate. It SHALL show the picture scaled to the HDMI output's height at
the NES pixel aspect, centred horizontally. Game sound SHALL play over
HDMI. Marker tracking SHALL NOT lower the game's frame rate: when the CPU
is short, tracking drops camera frames and the game keeps its pace.

#### Scenario: The picture is centred with side bars
- **WHEN** a game runs on a 1920×1080 output
- **THEN** the game picture fills the full height, keeps the NES aspect
  and is centred
- **AND** the areas left and right of it are bars that the game never
  draws into

#### Scenario: Tracking under load does not slow the game
- **WHEN** a game runs and tracking cannot keep up with the camera
- **THEN** the game still presents a new frame every display refresh at
  the game's native rate
- **AND** the tracking log shows camera frames dropped rather than game
  frames

#### Scenario: Sound plays over HDMI
- **WHEN** a game produces audio
- **THEN** it plays through the TV over the HDMI connection

### Requirement: Markers are drawn beside the game, not over it
In console mode the gun SHALL draw the marker tags inside the side bars,
each on an opaque quiet-zone patch. No tag or patch SHALL overlap the
game picture. The tags SHALL be drawn on every frame, whatever the game
shows, including the black frames a Zapper game flashes when the trigger
is pulled.

#### Scenario: No tag covers the game
- **WHEN** a game runs at any output resolution the gun accepts
- **THEN** every tag and its patch lie wholly inside the bars

#### Scenario: Tags survive a Zapper flash
- **WHEN** a game blanks its picture for a Zapper hit test
- **THEN** the tags are still drawn on those frames

#### Scenario: Bars too narrow for tags are refused
- **WHEN** the output's shape leaves bars too narrow to hold detectable
  tags
- **THEN** the gun stops at startup with an error that names the output
  resolution and the minimum bar width it needs

### Requirement: The drawn and solved layouts are one computation
The gun SHALL compute the tag positions it draws and the layout it gives
the solver with one function, from the HDMI output's actual pixel size.
No layout file or hand-measured value SHALL be needed in console mode.
Any `layout` file in the configuration SHALL be ignored, and the gun
SHALL log that it was ignored.

#### Scenario: Renderer and solver agree
- **WHEN** the gun starts on an output of a given size
- **THEN** each tag's drawn pixel position equals its position in the
  layout the solver uses

#### Scenario: A configured layout file is ignored
- **WHEN** console mode starts with `layout` set in the configuration
- **THEN** the layout derived from the output is used
- **AND** a log line says the file was ignored

### Requirement: The aim and trigger play the emulated Zapper
The gun SHALL feed its aim point to the emulated NES Zapper as the
position in the game picture it falls on. It SHALL feed the debounced
trigger as the Zapper trigger. An aim in the bars or off the screen, or
no current aim at all, SHALL be reported to the game as aiming
off-screen.

#### Scenario: Aiming at a picture point hits that point
- **WHEN** the aim point lies in the game picture at a given NES pixel
- **THEN** the emulated Zapper points at that NES pixel

#### Scenario: Aiming at the bars is off-screen
- **WHEN** the aim point lies in a side bar or outside the screen
- **THEN** the emulated Zapper reports off-screen

#### Scenario: Lost tracking is off-screen
- **WHEN** no frame has solved for longer than the aim-hold time
- **THEN** the emulated Zapper reports off-screen

#### Scenario: One trigger pull is one Zapper pull
- **WHEN** the trigger is pressed and released, with contact bounce
- **THEN** the game sees exactly one Zapper trigger pull

### Requirement: Start and Select are available without a gamepad
The gun SHALL read two optional GPIO buttons as controller 1's Start and
Select, debounced and wired like the trigger. Their pins SHALL be
validated together with the trigger and LED pins. A USB gamepad on the
Pi's USB port, if present, SHALL act as controller 1, alongside the
buttons.

#### Scenario: Start begins a game
- **WHEN** the Start button is pressed on a game's title screen
- **THEN** the game sees controller 1 Start pressed

#### Scenario: Shared pin is refused
- **WHEN** the Start or Select pin equals another configured pin
- **THEN** the gun exits at startup naming the clashing pins

#### Scenario: A gamepad works as controller 1
- **WHEN** a USB gamepad is connected and its buttons are pressed
- **THEN** the game sees them as controller 1

### Requirement: Games come from user-supplied ROM files
The gun SHALL load games only from ROM files the user puts on the Pi,
and the project SHALL ship no ROM. The configuration SHALL name a ROM
file or a folder. With a folder, holding Select while the gun starts
SHALL step to the next ROM, in name order, and the choice SHALL persist
across restarts. A missing or unreadable ROM SHALL NOT stop the gun.

#### Scenario: A single ROM starts at power-up
- **WHEN** the configuration names a ROM file and the gun starts
- **THEN** that game runs with no further input

#### Scenario: Select at start picks the next game
- **WHEN** the configuration names a folder and Select is held at startup
- **THEN** the next ROM in name order runs
- **AND** it runs again on the next start without Select held

#### Scenario: No ROM still shows the markers
- **WHEN** no ROM is configured, or the named ROM is missing or does not
  load
- **THEN** the screen shows the markers and a message naming the
  problem
- **AND** aiming still works and is reported in the log

### Requirement: Power and heat problems are reported
The gun SHALL check the Pi's under-voltage and throttling flags while it
runs. It SHALL log each new under-voltage or throttling event once, with
advice: a stronger supply for under-voltage, a heatsink for throttling.
The LED SHALL show the error pattern while under-voltage is present.

#### Scenario: A weak supply is named
- **WHEN** the Pi reports under-voltage during play
- **THEN** a log line names under-voltage and asks for a 5 V 2.5 A supply
- **AND** the LED shows the error pattern until it clears

#### Scenario: Throttling is logged once
- **WHEN** the Pi starts throttling for heat
- **THEN** one log line names thermal throttling and suggests a heatsink

### Requirement: Console mode runs without a Pi
The gun SHALL run console mode on an ordinary computer with recorded
camera frames, injected button levels, a stand-in emulator core that
needs no ROM, and an off-screen display. This SHALL let tests check
each of the following without a Pi, a TV or a ROM:
- the layout the solver gets matches what is drawn
- the bars carry the tags and the game picture does not
- the aim reaches the Zapper as the right NES pixel
- the trigger reaches the Zapper once per pull

#### Scenario: Emulated aim reaches the Zapper
- **WHEN** console mode runs emulated with frames whose aim is known
- **THEN** the stand-in core receives Zapper positions that match the
  aim mapped into NES pixels

#### Scenario: Emulated frame shows tags only in the bars
- **WHEN** an emulated frame is rendered off-screen
- **THEN** the detector finds every tag at the positions the solver's
  layout gives
- **AND** finds none inside the game picture
