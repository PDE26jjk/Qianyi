## MODIFIED Requirements

### Requirement: A seam can be read, recoloured and removed

Reading SHALL report every seam with both sides - each side a set of one or more
spans in drawing order, and each span a pattern, an edge index, an edge label, a
position range and a direction flag - plus the colour and the stitch count. The
read SHALL NOT compare the two sides' lengths: a seam whose sides are different
lengths is stitched by proportion, and nothing about the difference is reported.
A seam SHALL be recolourable and removable by its index. Reading the seams of one
pattern SHALL report the same entries with that pattern's spans marked.

#### Scenario: The full list

- **WHEN** the seams are read
- **THEN** each entry carries both sides as span lists, the colour and the stitch count

#### Scenario: A seam is removed

- **WHEN** a seam is removed by its index
- **THEN** it is gone from the list and the patterns are otherwise unchanged

#### Scenario: A one-to-one seam reads back unchanged

- **WHEN** a seam created from one edge on each side is read
- **THEN** each side reports exactly one span, with the edge, the position range and the direction flag it was created with

#### Scenario: A many-to-many seam reads back with its spans

- **WHEN** a seam created from several spans on each side is read
- **THEN** each side reports its spans in order, and the entry reports the stitch count

#### Scenario: A gathered seam reads back like any other

- **WHEN** a seam whose sides are different lengths is read
- **THEN** the entry reads back with its spans and its stitch count, and carries nothing about the difference between the sides

#### Scenario: Spans that are not adjacent read back as drawn

- **WHEN** a side was drawn from spans that are not geometrically contiguous
- **THEN** the read reports the spans in drawing order with the direction each was drawn in
