## Purpose

Makes a copy of a pattern say what it brings with it - internal lines, the seams
inside the copied selection - and adds the one in-place transform a pattern
maker needs, flipping a pattern, which today can only be done by copying it.

## ADDED Requirements

### Requirement: A pattern can be flipped in place

The editor SHALL flip a selected pattern about an axis through its anchor
(horizontal, vertical, or the axis through two selected points), updating its
outline, internal lines and grain direction. Sewings that use the pattern's edges
SHALL stay attached, and the pattern's position, fabric, granularity and
simulation state SHALL be unchanged.

#### Scenario: Flip a pattern

- **WHEN** a pattern is flipped horizontally in place
- **THEN** the outline is the mirror image about its anchor's vertical axis, the
  grain direction is mirrored with it, the pattern's sewings still point at the
  same edges, and the pattern's area is unchanged

#### Scenario: Flip a generated pattern

- **WHEN** a pattern owned by a generator is flipped
- **THEN** the command is refused with the hint to detach the pattern first

### Requirement: A copy chooses whether it brings internal lines

Copying a pattern SHALL take internal lines with it by default, and the command
SHALL offer copying the outline only. Which of the two happened SHALL be in the
report.

#### Scenario: Copy with internal lines

- **WHEN** a pattern with two internal lines is copied
- **THEN** the copy has the same two internal lines at the same positions and
  the report says internal lines were copied

#### Scenario: Outline-only copy

- **WHEN** a pattern with two internal lines is copied with internal lines
  disabled
- **THEN** the copy has no internal lines and the report says so

### Requirement: A copy can carry the seams inside the copied selection

The editor SHALL duplicate every seam whose two sides both lie inside the copied
selection, re-pointing them at the copies' edges, and SHALL leave a seam that
crosses the selection boundary alone, reporting its name. A seam inside the
selection whose counterpart edge has no copy SHALL be reported and not
duplicated.

#### Scenario: Double-layer copy

- **WHEN** two sewn patterns are copied together with seams included
- **THEN** the copies carry a seam that mirrors the original's pairing and the
  original seam is untouched

#### Scenario: Crossing seam

- **WHEN** a seam joins a copied pattern to a pattern outside the selection
- **THEN** the copy does not carry that seam and the report names it

#### Scenario: Undo

- **WHEN** a copy with seams is undone once
- **THEN** the copied patterns and the duplicated seams are gone and the original
  patterns and seams are exactly as they were

### Requirement: An instance or mirror copy carries no seams

An instance copy and a mirror copy SHALL bring no seams with them: the copy
exists to be edited in step with its source, and a seam that appeared on every
member of the chain would multiply the stitches the user asked for. The command
SHALL report that no seams were copied and why.

#### Scenario: A linked copy of a sewn pattern

- **WHEN** a pattern that carries seams is copied as an instance or as a mirror
- **THEN** the copy carries no seam and the report says the copy is linked, so
  its patterns are sewn where the user sews them

#### Scenario: A plain copy still carries them

- **WHEN** the same pattern is copied as a plain copy or a flip with seams enabled
- **THEN** the seams inside the selection are duplicated as the copy requirement
  describes
