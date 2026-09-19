## Purpose

Lets one seam join several edge spans - a long edge to several short ones, or a
yoke to two fronts - by mapping the two sides proportionally by length, which is
how real garments are sewn and how the section linker already works internally.

## ADDED Requirements

### Requirement: Each side of a seam holds one or more spans

A seam SHALL have two sides, and each side SHALL hold an ordered list of one or
more spans. A span is a run of consecutive edges on one panel - outline edges or
an internal line - with a start and an end position. Spans of one side SHALL be
ordered end to end, and the same side MAY span more than one panel so a
three-panel junction can be sewn as one seam.

#### Scenario: One long edge to two short edges

- **WHEN** a side holding one 200 mm edge is sewn to a side holding two 100 mm
  edges
- **THEN** one seam is created with three spans, and the two short spans are
  ordered so the seam's direction is continuous

#### Scenario: Three-panel junction

- **WHEN** side A holds one span on panel X and one span on panel Y, and side B
  holds one span on panel Z
- **THEN** the seam is one seam in the list, and its stitches pair X with Z and
  Y with Z

### Requirement: The two sides are matched by proportional section mapping

The seam SHALL match the two sides by cumulative length ratio: a point at
fraction `t` of one side's total length is paired with the point at the same
fraction of the other side's total length, split into sections at the section
boundaries of both sides. The tolerance SHALL be a documented fraction of the
side length, and the seam SHALL report the resulting stitch count and the
largest unmatched remainder.

#### Scenario: Uneven spans still match end to end

- **WHEN** a 200 mm side is sewn to spans of 120 mm and 80 mm
- **THEN** the point at 60% of the long side is paired with the end of the first
  short span, and both ends of the seam are paired

#### Scenario: Lengths disagree beyond the tolerance

- **WHEN** the two sides differ in length by more than the tolerance
- **THEN** the seam is created but reported as unmatched, it does not stitch
  until the sides agree, and the report names the length difference

### Requirement: A many-sided seam is one object with one payload decomposition

A seam SHALL remain one object in the project, the UI, the undo stack and the
script surface, however many panels it touches. Its stitches SHALL be handed to
the engine as one stitch group per pair of panels, each using the existing
two-pattern payload, so no engine change is required.

#### Scenario: Payload for a junction

- **WHEN** a seam joins one span on X and one on Y to one on Z
- **THEN** the payload contains two stitch groups, (X, Z) and (Y, Z), and the
  project lists one seam

#### Scenario: Deleting the seam

- **WHEN** a junction seam is deleted
- **THEN** every stitch group it contributed is removed and no other seam is
  affected

### Requirement: Editing a side re-runs the mapping and reports the change

Adding a span, removing a span, or editing the edges under a span SHALL re-run
the mapping, restitch the seam, and report how many stitch pairs changed. A
span whose edges no longer exist SHALL drop out of the seam, and a seam left
with fewer than two sides SHALL be reported as incomplete rather than silently
stitching nothing.

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
