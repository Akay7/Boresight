## Purpose

Zeroes a camera-based light gun: the player shoots known on-screen
targets through the gun's sights, and the server fits and applies a
correction for camera-to-barrel misalignment and parallax, per client
and persistently.

## ADDED Requirements

### Requirement: A session can zero its aim by shooting targets
The server SHALL accept `{"type": "zeroing", "action": "start"}` on the
frame connection and begin a zeroing run for that session, presenting
one target at a time. Each target SHALL have a known position in
normalized full-screen coordinates and a human-readable label. When the
on-screen overlay is running the targets SHALL be the corners of its
available area inset toward the centre, then the centre, and the
overlay SHALL draw the current one; otherwise they SHALL be the
display's own four corners. The last target of either set SHALL be
optional and repeat an earlier one, to be shot from a noticeably
different distance. At most one session SHALL be zeroing at a time; a
start from a second session SHALL be refused and reported to that
session without affecting the run in progress.

#### Scenario: Starting a run presents the first target
- **WHEN** a session sends a zeroing `start`
- **THEN** its next stats message reports zeroing as active with the
  first target's label, its index, and the number of targets

#### Scenario: A second session cannot start a concurrent run
- **WHEN** session A is zeroing and session B sends a zeroing `start`
- **THEN** B's stats report zeroing as not active with a message saying
  another client is zeroing, and A's run continues unchanged

### Requirement: A trigger during zeroing records a shot at the current target
While a session is zeroing, each trigger press it sends (a plain trigger
or a `down`) SHALL be recorded as a shot pairing the current target with
the frame the trigger names, resolved the same way a real shot's frame
is resolved, and the run SHALL advance to the next target. A shot whose
frame did not solve SHALL NOT be recorded; the run SHALL stay on the
same target and report the miss. A zeroing shot SHALL NOT press, click
or release any button and SHALL NOT take ownership of the cursor.

#### Scenario: A shot advances to the next target
- **WHEN** a zeroing session sends a trigger naming a frame that solved
- **THEN** the shot count increases by one, the reported target is the
  next one, and the cursor backend receives no click or press

#### Scenario: A shot on an unsolved frame is a miss
- **WHEN** a zeroing session sends a trigger naming a frame in which no
  markers were found
- **THEN** no shot is recorded, the target stays the same, and the
  stats message says the shot missed

### Requirement: The correction models misalignment and parallax physically
Finishing a run SHALL fit, from its shots, an angular offset — the
image point the barrel aims at, relative to the image centre — and,
only when the shots were taken from distances that differ enough to
separate the two, a lateral camera-to-barrel parallax offset. When they
do not, the parallax offset SHALL be zero and the angular offset alone
SHALL account for the shots. The fit SHALL report the residual between
the corrected shots and their targets.

#### Scenario: A tilted camera is corrected at other distances
- **WHEN** a camera tilted relative to the barrel is zeroed from one
  distance and then aimed from a different distance and position
- **THEN** the corrected aim lands on the point the barrel is aimed at,
  within a few millimetres, where the uncorrected aim is centimetres off

#### Scenario: Parallax is fitted from shots at two distances
- **WHEN** a camera offset from the barrel line is zeroed with shots
  from two distances differing by at least a third
- **THEN** the fitted parallax offset matches the physical offset and
  the corrected aim is accurate at a third distance

#### Scenario: Shots from one distance fit no parallax
- **WHEN** every shot of a run is taken from the same distance
- **THEN** the fitted parallax offset is zero

### Requirement: The run can be finished, cancelled, or completes itself
`finish` SHALL fit and apply the correction from the shots recorded so
far and SHALL require at least one; `cancel` SHALL end the run and keep
the previous correction. A run SHALL finish by itself after its last
target is shot. Ending a run by any means, including the session
disconnecting, SHALL remove the target from the screen and free zeroing
for other sessions.

#### Scenario: Finishing with no shots changes nothing
- **WHEN** a session sends `finish` before recording any shot
- **THEN** the run stays active, no correction is applied, and the
  stats message says a shot is needed

#### Scenario: Cancelling keeps the old zero
- **WHEN** a zeroed session starts a new run, records shots, and sends
  `cancel`
- **THEN** its aim is corrected exactly as before the run

#### Scenario: Disconnecting mid-run frees zeroing
- **WHEN** a zeroing session disconnects
- **THEN** another session can start a run

### Requirement: The correction is applied to the solved aim before hold and smoothing
A zeroed session's correction SHALL be applied to every solved aim
point before normalization, clamping, the dropout hold and smoothing, so
the reported position, the cursor, and the aim a trigger fires at are
all corrected. A session with no correction SHALL be served exactly as
before.

#### Scenario: A zeroed session's cursor is corrected
- **WHEN** a session with a stored correction streams a solvable frame
- **THEN** the reported and emitted position differ from the
  uncorrected aim by that correction

### Requirement: The correction is stored per client and survives restarts
A finished run SHALL save the correction under the session's client
identity: the `id` its `hello` carried if it is 1–64 characters of
letters, digits, `-` or `_`, otherwise its client kind. The correction
SHALL be kept in a file under `.boresight/`, and a session that
identifies itself with a stored identity SHALL be corrected from its
first frame after `hello`, including after a server restart. A
`{"type": "zeroing", "action": "reset"}` SHALL delete the stored
correction for that identity and return the session to the raw aim. A
missing or unreadable file SHALL NOT prevent the server from starting.

#### Scenario: A zero survives a restart
- **WHEN** a client zeroes, the server restarts, and the client
  reconnects with the same `id`
- **THEN** its aim is corrected without zeroing again

#### Scenario: Reset returns to the raw aim
- **WHEN** a zeroed session sends `reset`
- **THEN** its aim is uncorrected from then on and the stored entry is
  gone

#### Scenario: A corrupt store is ignored
- **WHEN** the zeroing file is not valid JSON at startup
- **THEN** the server starts, and no session is corrected

### Requirement: Zeroing state is reported in telemetry
Every stats message SHALL carry a `zeroing` field saying whether a run
is active, whether the session is zeroed, the current target (label,
index, count, and whether it is optional) or none, the number of shots
recorded, the fit's residual when one exists, and a message describing
the last outcome (a miss, a refusal, a finished fit) or none.

#### Scenario: Telemetry shows a finished zero
- **WHEN** a run finishes
- **THEN** the next stats message reports zeroing inactive, zeroed, with
  the fit's residual
