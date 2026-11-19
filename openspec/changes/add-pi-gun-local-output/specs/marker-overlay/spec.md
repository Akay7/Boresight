# Spec Delta

## ADDED Requirements

### Requirement: Tags can be placed beside a centred picture
The overlay SHALL accept a picture aspect, such as 4:3. With one set, it
SHALL place six tags in the bars left and right of a full-height picture
of that aspect, centred on the display:
- markers 0–3 at the bar corners
- markers 7 and 5 at the middle of the left and right bars

Each tag is as large as the narrower bar allows with its quiet-zone
patch. No tag or patch may overlap the picture. Without a picture
aspect, placement SHALL be unchanged.

#### Scenario: Tags stay out of a 4:3 picture
- **WHEN** the overlay runs on a 1280×720 display with picture aspect 4:3
- **THEN** all six tags and their patches lie in the 160-pixel bars left
  and right of the centred picture
- **AND** the layout reported to the solver has the same six tags at the
  same positions

#### Scenario: Bars too narrow are refused
- **WHEN** the picture aspect leaves bars too narrow for a detectable tag
- **THEN** the overlay refuses to start with an error naming the display
  size and the bar width it needs

#### Scenario: No aspect keeps the full-screen placement
- **WHEN** no picture aspect is set
- **THEN** the overlay places its eight tags as before
