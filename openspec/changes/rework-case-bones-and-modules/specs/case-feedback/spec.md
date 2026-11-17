# Spec Delta

## Purpose

Defines the gun's optional feedback devices: the swappable carriers for a
vibration motor, a recoil solenoid and a haptic LRA, how each is held,
powered and wired, and how each stays inert until software drives it.

## ADDED Requirements

### Requirement: The feedback device is optional and swappable
A gun SHALL take no feedback device, or one of three: a vibration motor,
a recoil solenoid or a haptic LRA. Each SHALL ride on its own carrier
plate, and all three carriers SHALL fit the same place on the receiver's
rails. Changing the device SHALL replace only the carrier and its lead.
No other printed part, purchased part or setting SHALL change.

#### Scenario: Changing the vibration motor for the solenoid
- **WHEN** a builder takes the vibration carrier out of a battery gun
  and fits the solenoid carrier
- **THEN** only the carrier and its lead change, and the lead plugs into
  the same hub socket as before

#### Scenario: A gun without feedback
- **WHEN** a gun is built with no feedback carrier
- **THEN** a printed spacer takes the carrier's place, the gun aims and
  fires as it does with one, and no lead is left unplugged inside

### Requirement: A carrier sits next to the hub
The feedback carrier SHALL sit on the receiver's rails between the hub
and the receiver's front port, so its lead to the hub is at most 60 mm
and the device is as close to the shooter's hand as the receiver allows.

#### Scenario: The lead is short
- **WHEN** any carrier is fitted with either board kit
- **THEN** its lead reaches the hub's feedback socket without slack loops
  and is no longer than 60 mm

### Requirement: A carrier is held without screws or printed latches
A carrier SHALL slide along the rails with the rear cap or the barrel
removed, and be held lengthwise between the hub, printed spacers and the
next bone's tenon. No screw, glue, snap or printed latch SHALL hold it,
and it SHALL come out once the bone in front of it is removed.

#### Scenario: Fitting a carrier
- **WHEN** the barrel is removed, a carrier and its spacers are slid in,
  and the barrel is bolted back on
- **THEN** the carrier cannot move along the receiver, and the gun's bolt
  count is unchanged

### Requirement: The solenoid takes its power from the cells
The recoil solenoid SHALL be powered from the battery drawer after the
power switch, through the hub but not through its regulator, so that its
current pulses do not take the board's supply out of range.

#### Scenario: A kick while the Pi aims
- **WHEN** the solenoid is pulsed while the Pi gun runs on four NiMH AA
  cells
- **THEN** the Pi's supply stays within 4.75–5.25 V and the Pi keeps
  running

### Requirement: The motor and the LRA run from the gun's own supplies
The vibration motor SHALL run from the hub's 5 V. The LRA's driver SHALL
run from the board's 3.3 V, so that its signal lines never rise above
3.3 V.

#### Scenario: The LRA driver on the Pi's bus
- **WHEN** the LRA carrier is fitted to a Pi gun with I2C enabled and the
  Pi is switched on
- **THEN** the driver answers at address 0x5A on I2C bus 1, and its lines
  idle at no more than 3.3 V

#### Scenario: A vibration motor on a Pi on a host cable
- **WHEN** the vibration carrier is fitted to a Pi gun powered over its
  USB cable to a host
- **THEN** the motor's driver is powered from the hub's 5 V, which comes
  from the Pi, with no battery in the gun

### Requirement: Feedback is wired to pins nothing else uses
A carrier's signal SHALL reach the board only through the hub, on pins
that the trigger, status LED, power, camera and buttons do not use.
- **Pi:** GPIO22 (header pin 15) for the motor and the solenoid, and I2C1
  (pins 3 and 5) for the LRA's driver.
- **ESP32-CAM:** GPIO12 for the motor and the solenoid, and GPIO14 (SDA)
  and GPIO15 (SCL) for the LRA's driver.

#### Scenario: Nothing is moved to make room
- **WHEN** any carrier is fitted with either board kit
- **THEN** its signal uses only its own pins, and the trigger and status
  LED work on their existing pins

### Requirement: A fitted device stays still until software drives it
Each driver's input SHALL be held off whenever the board is not driving it
high. A device SHALL therefore never run at power-up or with today's
software, and an ESP32-CAM SHALL boot normally with any carrier fitted,
GPIO12 being one of its boot-strapping pins.

#### Scenario: Power-up with today's software
- **WHEN** a gun with the motor, solenoid or LRA carrier is switched on
  with the existing firmware or Pi gun software
- **THEN** the device does not run, and the gun boots and aims as it does
  without the carrier

#### Scenario: Bench check of a carrier
- **WHEN** the motor or solenoid carrier's drive line is touched to the
  hub's 5 V test pin and then released
- **THEN** the motor runs or the solenoid pulls in while it is touched,
  and stops when released

### Requirement: Feedback does not move the camera's aim
Running any feedback device SHALL NOT shift the camera, loosen a bolt or
move the carrier, so that a zeroed gun keeps its zero.

#### Scenario: Many kicks
- **WHEN** a zeroed gun's solenoid is pulsed 200 times
- **THEN** the aim point is unchanged, no nut has turned and the carrier
  has not moved
