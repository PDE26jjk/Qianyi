## Purpose

Turns the flat panel a pattern maker drew into a pleated panel in place - fold
lines marked, material taken up, and for a sewn pleat the seams that hold it -
instead of requiring the pleats to be drafted by hand or generated from scratch.

## ADDED Requirements

### Requirement: A pleat command folds a panel along marked lines

The editor SHALL apply a pleat command to a panel by pairing a set of fold lines
(internal lines or outline runs) with a pleat count, a pleat depth, a direction
and a fold type (knife or box). After the command the panel SHALL carry the
generated fold lines, the fold lines SHALL be visible in the pattern window,
and the command SHALL report the material taken up and the resulting
circumference along the pleated edge.

#### Scenario: Knife pleats on a skirt panel

- **WHEN** a skirt panel 600 mm wide is pleated with 6 pleats of 40 mm depth in
  one direction
- **THEN** the panel carries the fold lines for 6 knife pleats, the report says
  240 mm of material was taken up and the resulting circumference is 360 mm,
  and no outline vertex outside the pleated edge is moved

#### Scenario: Box pleats

- **WHEN** the same panel is pleated as box pleats
- **THEN** each pleat is a symmetric pair of folds around its line and the
  reported take-up is twice the depth per pleat

### Requirement: A sewn pleat is held by seams

A sewn pleat SHALL be created by pairing the fold lines with seams over the
requested depth, so the extra material folds in three dimensions instead of
lying flat, and the resulting seams SHALL be ordinary seams: listed, coloured,
deletable and rendered like any other.

#### Scenario: Sewn pleats produce seams

- **WHEN** a sewn pleat command is applied with 6 pleats
- **THEN** the project gains the seams that hold those pleats, each seam's
  stitches pair the marked lines over the given depth, and deleting one seam
  leaves the others intact

#### Scenario: Undo removes everything the command made

- **WHEN** a pleat command is undone once
- **THEN** the fold lines, the seams it created and any vertices it added are
  gone and the panel is exactly as it was

### Requirement: A pleat command is previewed and validated before it applies

The command SHALL show a preview of the fold lines and the reported take-up
before committing, and SHALL refuse the parameters that cannot be applied -
a pleat depth that would consume more than the available width, a pleat count
that would place fold lines closer than the mesh tolerance, or a panel whose
outline is invalid - naming the limit that was exceeded.

#### Scenario: Depth larger than the panel

- **WHEN** the requested count times the depth exceeds the available width
- **THEN** the command is refused, the maximum depth for that count is
  reported, and the panel is unchanged

#### Scenario: Generated panel

- **WHEN** a pleat command is requested on a panel owned by a generator
- **THEN** the command is refused with the hint to detach the panel first
