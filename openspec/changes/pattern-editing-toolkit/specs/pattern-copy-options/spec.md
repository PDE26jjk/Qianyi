## Purpose

Makes a copy of a panel say what it brings with it - internal lines, the seams
inside the copied selection - and adds the one in-place transform a pattern
maker needs, flipping a panel, which today can only be done by copying it.

## ADDED Requirements

### Requirement: A panel can be flipped in place

The editor SHALL flip a selected panel about an axis through its anchor
(horizontal, vertical, or the axis through two selected points), updating its
outline, internal lines and grain direction. Sewings that use the panel's edges
SHALL stay attached, and the panel's position, fabric, granularity and
simulation state SHALL be unchanged.

#### Scenario: Flip a panel

- **WHEN** a panel is flipped horizontally in place
- **THEN** the outline is the mirror image about its anchor's vertical axis, the
  grain direction is mirrored with it, the panel's sewings still point at the
  same edges, and the panel's area is unchanged

#### Scenario: Flip a generated panel

- **WHEN** a panel owned by a generator is flipped
- **THEN** the command is refused with the hint to detach the panel first

### Requirement: A copy chooses whether it brings internal lines

Copying a panel SHALL take internal lines with it by default, and the command
SHALL offer copying the outline only. Which of the two happened SHALL be in the
report.

#### Scenario: Copy with internal lines

- **WHEN** a panel with two internal lines is copied
- **THEN** the copy has the same two internal lines at the same positions and
  the report says internal lines were copied

#### Scenario: Outline-only copy

- **WHEN** a panel with two internal lines is copied with internal lines
  disabled
- **THEN** the copy has no internal lines and the report says so

### Requirement: A copy can carry the seams inside the copied selection

The editor SHALL duplicate every seam whose two sides both lie inside the copied
selection, re-pointing them at the copies' edges, and SHALL leave a seam that
crosses the selection boundary alone, reporting its name. A seam inside the
selection whose counterpart edge has no copy SHALL be reported and not
duplicated.

#### Scenario: Double-layer copy

- **WHEN** two sewn panels are copied together with seams included
- **THEN** the copies carry a seam that mirrors the original's pairing and the
  original seam is untouched

#### Scenario: Crossing seam

- **WHEN** a seam joins a copied panel to a panel outside the selection
- **THEN** the copy does not carry that seam and the report names it

#### Scenario: Undo

- **WHEN** a copy with seams is undone once
- **THEN** the copied panels and the duplicated seams are gone and the original
  panels and seams are exactly as they were
