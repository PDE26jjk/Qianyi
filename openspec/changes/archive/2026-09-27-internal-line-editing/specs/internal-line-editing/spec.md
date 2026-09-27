## Purpose

Let the sewing and point tools work on the geometry a pattern really has: its
outline, and each internal line, with the rules an open line needs.

## ADDED Requirements

### Requirement: A sewing half runs on a chain, and an open chain does not wrap

A half SHALL be read in the space of the chain it was made on - the pattern's
outline, or one internal line. A closed chain SHALL keep the direction the half
was drawn in, and an end dragged past the other one SHALL keep going so the run
spans the long way round. An open chain SHALL keep the run between its two ends:
an end dragged past the other one SHALL turn the run round, and a run that would
have to leave the chain SHALL be refused. A side of a seam whose walk would leave
an open chain SHALL be refused rather than wrapped onto the other end of the line.

#### Scenario: An end dragged along an internal line

- **WHEN** one end of a half on an internal line is dragged to another place on
  the same line
- **THEN** the half runs between the two places the drag left, in the line's own
  length space

#### Scenario: An end dragged past the other one on an internal line

- **WHEN** that end is dragged past the end that stayed
- **THEN** the run turns round between them, and the half does not span the long
  way round as it would on a closed outline

#### Scenario: A pointer that leaves the line

- **WHEN** the pointer leaves the chain the half runs on
- **THEN** the half keeps the shape it last had, and the outline's own cases behave
  as they did before

### Requirement: The tools read the chain the pointer is on

The pointer's chain SHALL be found for the outline and for every internal line
alike. A point tool SHALL read the edge finder, whose snapshot carries the outline
and the internal lines of every pattern, so its snap answers with the chain
nearest the pointer - not only the chain the pointer is exactly on - and the
preview SHALL mark that answer. A half SHALL be found without that snapshot: the
sewing tools take their outline place from the finder and measure an internal line
from its own pieces. A half may be drawn or edited on either chain, its snapping
SHALL offer the points of that chain and the ends of the halves made on it, and a
point tool SHALL split or bend the piece the snap answered with, writing into the
chain that piece belongs to and leaving the other chains alone.

#### Scenario: A spline point on an internal line

- **WHEN** the add-spline-point tool is clicked on a piece of an internal line
- **THEN** that piece gains a control point where the click landed

#### Scenario: A vertex on an internal line

- **WHEN** the add-vertex tool is clicked near a piece of an internal line
- **THEN** that line is two pieces meeting at the new Sketch vertex, and the
  outline is untouched

#### Scenario: A click near a line

- **WHEN** the pointer is within the snap radius of a line but not on it
- **THEN** the snap names that line, its edge and the place the pointer is
  nearest, and the preview marks that place

#### Scenario: A chain the sampler answered nothing for

- **WHEN** a chain has no samples - a piece the linking run has not cut, an edit
  that left one behind - and the pointer is near another one
- **THEN** the chains that do answer are still there to snap to, and the tool that
  asked is not told the finder failed

#### Scenario: A file just opened

- **WHEN** a file is opened, so no pattern has sections or samples yet, and a tool
  asks the finder for a place
- **THEN** the finder takes the samples it needs and answers, instead of holding
  an empty snapshot that describes itself as current

#### Scenario: A snapshot an undo or a reload dropped

- **WHEN** the snapshot is gone and the tool's cursor draws again
- **THEN** the cursor rebuilds it and the preview comes back without the pointer
  having to leave and re-enter the editor

### Requirement: A new point is handed to the tool that follows

After a point is added, SHALL the point and the edge selection be cleared, the
added point be the selected one, and the member the click was made on become the
active pattern - so a move that runs immediately afterwards acts on that point,
in that member's own space. A mirrored instance carries the same point in a space
of its own, so naming the member is what keeps a move from going the other way.

#### Scenario: Adding a point and then moving it

- **WHEN** a vertex or spline point is added on one member of a chain and the move
  tool is used straight after
- **THEN** the move acts on the point that was added, with the transform of the
  member it was added on

#### Scenario: A seam drawn along an internal line

- **WHEN** a half is drawn with the free-sewing tool while the pointer is over an
  internal line
- **THEN** the half is stored in the internal line's own space, and the second
  half is drawn the same way as for an outline half

#### Scenario: The pointer over a seam

- **WHEN** the pointer is over a half of a seam in the sewing mode
- **THEN** that seam is drawn again, thicker, and with its stitch connectors when
  it is the selected seam, so what a click would take is visible before it does
