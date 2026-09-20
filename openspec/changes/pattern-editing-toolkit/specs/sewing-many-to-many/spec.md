## Purpose

Lets one seam join several edge spans per side - a long edge to several short
ones - by mapping the two sides proportionally by length, which is how real
garments are sewn and how the section linker already works internally.

## ADDED Requirements

### Requirement: Each side of a seam is a set of spans

A seam SHALL have two sides. A span SHALL be a run of edges on one panel - a
start edge with a start position, an end edge with an end position - together
with the direction it was drawn in, which is what today's one side already is.
Each side SHALL hold a set of one or more spans, in the order they were drawn,
so the spans of a set need not be geometrically contiguous or ordered. Both
sides SHALL be on one panel each, so a seam joins exactly two panels.

#### Scenario: One long edge to two short edges

- **WHEN** a side holding one 200 mm edge is sewn to a side holding two 100 mm
  edges
- **THEN** one seam is created with three spans, and the two short spans keep
  the order and the direction they were drawn with

#### Scenario: A one-to-one seam is a set of one

- **WHEN** a seam is created by clicking one edge and then another, as the
  sewing tool already does
- **THEN** each side holds exactly one span and the seam behaves as before

#### Scenario: A set on more than one panel is refused

- **WHEN** a span is added to a set whose other spans are on a different panel
- **THEN** the span is refused with the reason, because a seam joins two panels

### Requirement: The two sides are matched by proportional section mapping

The seam SHALL build the sections of a side by concatenating the sections of its
spans in order, and SHALL match the two sides with the existing two-way
proportional merge: a point at fraction `t` of one side's total length is paired
with the point at the same fraction of the other side's total length, split at
the section boundaries of both sides. It SHALL report the resulting stitch count
and the largest unmatched remainder, and it SHALL report the two sides as
unmatched, without stitching them, when their lengths differ by more than the
tolerance.

#### Scenario: Uneven spans still match end to end

- **WHEN** a 200 mm side is sewn to spans of 120 mm and 80 mm
- **THEN** the point at 60% of the long side is paired with the end of the first
  short span, and both ends of the seam are paired

#### Scenario: Lengths disagree beyond the tolerance

- **WHEN** the two sides differ in length by more than the tolerance
- **THEN** the seam is created but reported as unmatched, it does not stitch
  until the sides agree, and the report names the length difference

#### Scenario: The tolerance is one documented constant

- **WHEN** the tolerance is changed by the calibration experiment in the task
  list
- **THEN** the same value decides "matched" and "unmatched" for every seam, and
  the reports name it

### Requirement: A many-span seam is one object

A seam SHALL remain one object in the project, the UI, the undo stack and the
script surface however many spans its sides hold. Because both sides are on one
panel each, its stitches SHALL be handed to the engine as the existing
two-pattern stitch group, so no engine change is required.

#### Scenario: One seam in the list

- **WHEN** a seam with three spans is created
- **THEN** the project lists one seam, and deleting it removes its stitches
  without affecting any other seam

#### Scenario: Undo and redo

- **WHEN** a seam with several spans is created and then undone
- **THEN** the seam is gone, the panels and their sections are as they were, and
  redoing restores the same seam

### Requirement: Drawing a seam builds its two sets in turn

The sewing tool SHALL take the spans of the first side in the order and the
direction they are drawn, and SHALL take Enter as the signal that the first set
is finished and the second set is starting. The seam SHALL be created when the
second set has at least one span, and the tool SHALL show the pairing direction
of both sets before it does.

#### Scenario: Two spans, then one

- **WHEN** two spans are drawn, Enter is pressed, and one span is drawn
- **THEN** the first set holds the two spans in drawing order and the second
  holds the one, and the seam is created

#### Scenario: The first set is abandoned

- **WHEN** the tool is cancelled after the first set was drawn
- **THEN** no seam is created and the panels are unchanged

### Requirement: Editing a side re-runs the mapping and reports the change

Adding a span, removing a span, or editing the edges under a span SHALL re-run
the mapping, restitch the seam, and report how many stitch pairs changed. A span
whose edges no longer exist SHALL drop out of the seam, and a side left with no
spans SHALL be reported as incomplete rather than silently stitching nothing.

#### Scenario: Adding a span

- **WHEN** a span is added to one side of a two-span seam
- **THEN** the mapping is recomputed, the stitch count is reported, and the
  other side's spans are unchanged

#### Scenario: Edge removed under a span

- **WHEN** an edge used by a span is deleted
- **THEN** the span is removed and reported, the rest of the seam keeps
  stitching, and the user is told which span was dropped

#### Scenario: Degenerate side

- **WHEN** a side's spans have zero total length
- **THEN** the seam is reported as incomplete and no stitches are generated
