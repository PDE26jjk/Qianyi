# agent-sewing-control Specification

## Purpose
Let a script or an agent stitch two panel edges together with a known direction,
read back every seam including the ones that touch one panel, and hear the real
reason when a seam cannot be created.

## Requirements

### Requirement: A seam is created through the add-on's own sewing

Creating a seam SHALL take two edges, each named as a panel plus an edge index or
an edge label, one direction flag and an optional colour. It SHALL hand the two
edge points the flag selects to the add-on's own click-based sewing - the one
the editor calls - and SHALL derive no direction of its own: with the flag off,
each edge's first point is handed over; with the flag on, the first edge's first
point and the second edge's second point. An unknown edge label is refused with
the labels the panel has.

#### Scenario: The seam is the add-on's seam

- **WHEN** a seam is created between two edges
- **THEN** it is the seam the add-on's click-based sewing produces for the two edge points the flag selects

#### Scenario: The two directions are both expressible

- **WHEN** the same seam is created with the flag off and with it on
- **THEN** each seam carries the sides' positions and direction flags the add-on's own sewing recorded for it

#### Scenario: An edge named by label

- **WHEN** an edge is named by a label a component wrote
- **THEN** the seam uses that edge, and an unknown label is refused with the labels the panel has

### Requirement: A seam can be created from positions along the edges

Creating a seam SHALL also be possible from a position between 0 and 1 on each
edge, through the add-on's own click-based sewing: the positions are turned into
edge points and handed to that sewing, which decides the direction exactly as it
does when the editor clicks there.

#### Scenario: A seam from positions

- **WHEN** a seam is created from a position on each edge
- **THEN** it exists, and it is the seam the editor's own click-based sewing produces for those two points

### Requirement: A seam can be read, recoloured and removed

Reading SHALL report every seam with both sides - panel, edge index, edge label,
position range and direction flag - plus the colour and the stitch count. A seam
SHALL be recolourable and removable by its index. Reading the seams of one panel
SHALL report the same entries with that panel's side marked.

#### Scenario: The full list

- **WHEN** the seams are read
- **THEN** each entry carries both sides, the colour and the stitch count

#### Scenario: A seam is removed

- **WHEN** a seam is removed by its index
- **THEN** it is gone from the list and the panels are otherwise unchanged

### Requirement: A refused seam reports why

When a seam cannot be created - the two edges overlap, a side has no sections,
or an edge is missing - the caller SHALL receive the underlying reason, not a
generic failure.

#### Scenario: Overlapping edges

- **WHEN** a seam is created between two edges that overlap
- **THEN** the refusal names the overlap as the reason

### Requirement: A seam keeps its direction through a rebuild

When a generator rebuild keeps a panel's edge list, a seam on that panel SHALL
keep its edge identity, its positions and its direction flag.

#### Scenario: A parameter change that keeps the edges

- **WHEN** a generator's parameter changes and its panels' edge lists are unchanged
- **THEN** every seam on those panels is unchanged, including its direction flag
