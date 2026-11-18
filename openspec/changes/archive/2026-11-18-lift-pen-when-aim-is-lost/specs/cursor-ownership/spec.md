## ADDED Requirements

### Requirement: Only the shooter, or nobody, stops the aim
A session's report that it has stopped aiming SHALL reach the cursor
only while that session owns the cursor or no session does. When the
session that owns the cursor ends, the cursor SHALL be told that nothing
is aiming as it is freed, so the pen is not left at that session's last
aim.

#### Scenario: One session's dropout does not hide another's cursor
- **WHEN** session A owns the cursor and keeps aiming, and session B
  stops aiming
- **THEN** the cursor backend is not told that nothing is aiming

#### Scenario: A shooter that disconnects mid-aim stops the aim
- **WHEN** the session that owns the cursor disconnects while aiming
- **THEN** the cursor backend is told that nothing is aiming, and the
  cursor is free
