## Purpose

Lets one seam join several edge spans per side - a long edge to several short
ones - by mapping the two sides proportionally by length, which is how real
garments are sewn and how the section linker already works internally.

## ADDED Requirements

### Requirement: Each side of a seam is a set of spans

A seam SHALL have two sides. A span SHALL be a run of edges on one pattern - a
start edge with a start position, an end edge with an end position - together
with the direction it was drawn in, which is what today's one side already is.
Each side SHALL hold a set of one or more spans, in the order they were drawn,
so the spans of a set need not be geometrically contiguous or ordered. Both
sides SHALL be on one pattern each, so a seam joins exactly two patterns.

#### Scenario: One long edge to two short edges

- **WHEN** a side holding one 200 mm edge is sewn to a side holding two 100 mm
  edges
- **THEN** one seam is created with three spans, and the two short spans keep
  the order and the direction they were drawn with

#### Scenario: A one-to-one seam is a set of one

- **WHEN** a seam is created by clicking one edge and then another, as the
  sewing tool already does
- **THEN** each side holds exactly one span and the seam behaves as before

#### Scenario: A set on more than one pattern is refused

- **WHEN** a span is added to a set whose other spans are on a different pattern
- **THEN** the span is refused with the reason, because a seam joins two patterns

### Requirement: The two sides are matched by proportional section mapping

The seam SHALL build the sections of a side by concatenating the sections of its
spans in order, and SHALL match the two sides with the existing two-way
proportional merge: a point at fraction `t` of one side's own total length is
paired with the point at the same fraction of the other side's total length,
split at the section boundaries of both sides.

The merge works from progress along each side, and SHALL NOT compare the two
sides' lengths: the two sides need not be the same length, and a longer side is
not measured, reported, flagged or refused. Sewing a longer side to a shorter
one is how a garment is designed - a puff sleeve's cap to its armhole, a binding
or a band to the edge it trims, a gathered skirt to its waistband - and the seam
SHALL stitch whatever proportion it is given, the difference being taken up as
the material the longer side gathers. The seam SHALL report the resulting stitch
count.

The stitch pairs SHALL come from the pieces the linking run paired: a piece of
one side and the piece of the other it was linked to carry the same stretch of
the seam, and their samples SHALL be paired in order, from the start of that
stretch to its end. A piece a drawn run ends at carries the run's own end as a
sample of its own, at the end the walk reads it - after the piece's samples when
that run runs forwards, before them when it runs backwards - so a side drawn
backwards, or sewn in the opposite direction to the one it is sewn to, pairs one
to one like any other. The pairing SHALL NOT compute a ratio or a progress: the
correspondence IS the linked pieces, which is where the proportional cutting has
already happened, so no division stands between the two sides and no rounding
can move a stitch. A seam whose two sides the linking run did not pair - a piece
left without a partner, which is what another seam cutting the same edge leaves
behind - SHALL be reported and not stitched.

That is also what closes a join: where one side ends a run and starts another,
the piece that run ends at carries the run's own end as a sample, and it is
paired with the other side's end of the same piece - the point the two runs'
ends meet - while the next piece's first sample meets the same point of the other
side. The pair made twice that way is one stitch, and it is dropped once. The
runs of a set are usually the pieces a pattern was cut into, so they mostly do
not share a vertex, and the join between two of them is exactly this case.

#### Scenario: Uneven spans still match end to end

- **WHEN** a 200 mm side is sewn to spans of 120 mm and 80 mm
- **THEN** the point at 60% of the long side is paired with the end of the first
  short span, and both ends of the seam are paired

#### Scenario: A longer side is sewn to a shorter one

- **WHEN** a 200 mm side is sewn to a 120 mm one
- **THEN** the seam stitches, the point at fraction `t` of the long side is
  paired with the point at the same fraction of the short one, and neither the
  seam nor the report holds anything about how much longer the long side is

#### Scenario: A gathered side keeps the seam stitched

- **WHEN** a puff sleeve's cap is sewn to an armhole that is shorter, which is
  how a puff sleeve is made
- **THEN** the seam stitches through the whole difference, and the material the
  cap gathers is what the gather is, not something the seam measures

#### Scenario: A join is closed by two of one side's points meeting one

- **WHEN** two runs that do not share a vertex are sewn to one run, so the first
  side walks one more sample than the second
- **THEN** the seam stitches with one pair at every sample of the longer walk, and
  the sample on the other side at the join is in two pairs - the two facing
  samples of the join meeting it

#### Scenario: A join that falls on the other side's own piece joint

- **WHEN** two runs of one side meet at a place where the other side's pattern
  already has a piece of its own end, so the linking run aligns the two boundaries
  instead of cutting, and the runs' facing ends are two different vertices
- **THEN** the one point the other side has there is in two pairs - both facing
  ends are joined to it - and every sample of both sides' walks is in a pair, so
  nothing is left unstitched on either side

#### Scenario: A side sewn the other way round pairs one to one

- **WHEN** a one-to-one seam is created with the second side reversed, so its
  walk runs the other way along its chain
- **THEN** the first sample of each side meets the first sample of the other, the
  last meets the last, and every sample in between meets its counterpart - one
  pair per sample, with nothing shifted

#### Scenario: A seam the linking run did not pair is reported

- **WHEN** another seam cuts the same edge, so one side is left with pieces the
  linking run could not pair to the other side's
- **THEN** the seam reports that its two sides were cut into different numbers of
  pieces, and its patterns are held out of the mesh and the simulation

### Requirement: A many-span seam is one object

A seam SHALL remain one object in the project, the UI, the undo stack and the
script surface however many spans its sides hold. Because both sides are on one
pattern each, its stitches SHALL be handed to the engine as the existing
two-pattern stitch group, so no engine change is required. Removing a seam SHALL
leave nothing of it behind in the session: no stitch group, and no entry in the
identity map a side was looked up through, so a later lookup of the seam's or a
side's identity SHALL answer nothing rather than read the memory the removal
freed.

#### Scenario: One seam in the list

- **WHEN** a seam with three spans is created
- **THEN** the project lists one seam, and deleting it removes its stitches
  without affecting any other seam

#### Scenario: Undo and redo

- **WHEN** a seam with several spans is created and then undone
- **THEN** the seam is gone, the patterns and their sections are as they were, and
  redoing restores the same seam

#### Scenario: A selected many-span seam is removed

- **WHEN** a many-span seam is selected in the sewing mode and deleted
- **THEN** the seam and both of its sides are gone, and looking either of them up
  answers nothing - the ids the pick pass keyed on the sides go with them instead
  of reading the memory the removal freed

### Requirement: The editor joins each drawn run's ends to what they pair with

The pattern editor SHALL draw a seam's connecting lines at every place a drawn
run of either side begins or ends, so each run's two ends are joined to the
points they are paired with, and SHALL draw equally spaced lines between two such
places. A line at such a place SHALL start on the run's own end - the point the
run was drawn to - and SHALL NOT start on a point read across the place from the
side as a whole, because two runs that do not share a vertex put the same
fraction of a side on two different points. Where one point of a side meets two
faces of the other, every one of those ends SHALL be joined to that point, so the
middle of a long side sewn to two short ones is drawn to both of their facing
ends. The lines between two such places SHALL be drawn between the two sides at
the same fraction of each side's own length, which is the correspondence the
merge stitches. The lines SHALL be drawn from the patterns' own curve geometry
and SHALL NOT depend on the mesh a pattern was sampled into: the editor's drawing
is a view of the curves, so the same seam meshed coarsely and finely draws the
same lines.

#### Scenario: The join of a many-to-many side is drawn

- **WHEN** a 200 mm side sewn to runs of 120 mm and 80 mm is shown in the editor
- **THEN** the lines include the one at 60% of the long side, which is the join
  of the two short runs, and the lines are equally spaced either side of it

#### Scenario: A join the two runs do not share a vertex at

- **WHEN** a 205 mm side is sewn to runs of 120 mm and 80 mm whose facing ends
  are two different vertices, and the seam is shown in the editor
- **THEN** the point at 60% of the long side, 123 mm along it, is joined to both
  120 mm and 125 mm, each of which is the end of the run it came from

#### Scenario: A one-run seam draws what a single sampling drew

- **WHEN** a seam of one run on each side is shown
- **THEN** its lines are the equally spaced ones that sampling each side once
  produced, so a seam that has not changed does not look different

#### Scenario: The mesh the pattern was sampled into does not show in the lines

- **WHEN** a pattern's granularity changes, so its mesh is sampled coarsely or
  finely, and a seam on it is shown
- **THEN** the seam's drawn polylines and its connecting lines are the same ones
  as before, because they come from the curves

### Requirement: Drawing a seam builds its two sets in turn

The sewing tool SHALL take the spans of the first side in the order and the
direction they are drawn, and SHALL take Enter as the signal that the first set
is finished and the second set is starting. The seam SHALL be created when the
second set has at least one span, and the tool SHALL show the pairing direction
of both sets before it does. The place a drawn run begins at and the place it
ends at SHALL each snap to the points the seam can land on - the chain's own
points and the ends of runs already drawn along it - when the press or the
release is within the snap threshold of one, the threshold being measured on
screen at the pointer so it does not change with the zoom. A place away from all
of them SHALL be taken as the pointer's own, so a run may still begin or end
inside an edge.

#### Scenario: Two spans, then one

- **WHEN** two spans are drawn, Enter is pressed, and one span is drawn
- **THEN** the first set holds the two spans in drawing order and the second
  holds the one, and the seam is created

#### Scenario: The first set is abandoned

- **WHEN** the tool is cancelled after the first set was drawn
- **THEN** no seam is created and the patterns are unchanged

#### Scenario: A run drawn onto the end of another one

- **WHEN** a run is drawn along a chain and a second run is begun, or ended,
  within the snap threshold of a point of that chain or of an end of the first
  run
- **THEN** the second run begins or ends exactly on that point, so two runs can
  be made to meet at one vertex

#### Scenario: A run drawn away from every point

- **WHEN** a run is drawn with its press and its release further than the snap
  threshold from every point of the chain and from every end of a run on it
- **THEN** it begins and ends where the pointer was, so a run can be drawn to an
  arbitrary place on an edge

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
