## MODIFIED Requirements

### Requirement: A seam can be read, recoloured and removed

Reading SHALL report every seam with both sides - each side an ordered list of
one or more spans, and each span a panel, an edge index, an edge label, a
position range and a direction flag - plus the colour, the stitch count and, for
a seam whose sides could not be matched, the unmatched remainder. A seam SHALL
be recolourable and removable by its index. Reading the seams of one panel SHALL
report the same entries with that panel's spans marked.

#### Scenario: The full list

- **WHEN** the seams are read
- **THEN** each entry carries both sides as span lists, the colour and the stitch count

#### Scenario: A seam is removed

- **WHEN** a seam is removed by its index
- **THEN** it is gone from the list and the panels are otherwise unchanged

#### Scenario: A one-to-one seam reads back unchanged

- **WHEN** a seam created from one edge on each side is read
- **THEN** each side reports exactly one span, with the edge, the position range and the direction flag it was created with

#### Scenario: A many-to-many seam reads back with its spans

- **WHEN** a seam created from several spans on each side is read
- **THEN** each side reports its spans in order, and the entry reports the stitch count and the unmatched remainder
