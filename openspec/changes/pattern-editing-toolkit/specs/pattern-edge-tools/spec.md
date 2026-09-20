## Purpose

Gives the pattern editor the edge commands a pattern maker drafts with -
dividing an edge, reshaping a corner, opening a fan, and dragging a curve - so
panels can be built and corrected inside the add-on instead of being drafted
elsewhere and imported.

## ADDED Requirements

### Requirement: A curve is measured by arc length and written back as points

Every command in this capability SHALL measure positions along the sampled
curve, so dividing an edge into equal parts produces parts of equal arc length
whatever the curve looks like. Each resulting piece SHALL be written back
through one rule: a straight piece stays a straight two-point edge, a piece that
reproduces a circle exactly keeps the Bezier form that describes it, and every
other piece becomes a cubic spline fitted through control points within the
project's fitting tolerance. The written geometry SHALL stay within that
tolerance of the geometry that was there before the command ran, and the
command SHALL report when no fit reached the tolerance within the control point
cap, keeping the closest fit it found.

#### Scenario: Divide a straight edge into four

- **WHEN** a straight edge of 100 mm is divided into four parts
- **THEN** four straight pieces of 25 mm are written, the outline's shape and
  area are unchanged, and the panel meshes at the same granularity

#### Scenario: Divide a curved edge by arc length

- **WHEN** a curved edge is divided into three equal parts
- **THEN** the three pieces are within the fitting tolerance of the original
  curve and their arc lengths are equal within the same tolerance

#### Scenario: A Bezier piece becomes a spline

- **WHEN** a Bezier edge is divided
- **THEN** each piece is written as a spline fitted to its share of the original
  curve, unless that piece is exactly a circular arc

#### Scenario: The fit cannot reach the tolerance

- **WHEN** a curve is divided and no fit within the control point cap reaches
  the tolerance
- **THEN** the closest fit is written and the report says the tolerance was not
  reached

### Requirement: Points closer than the merge threshold are merged

The project SHALL carry one merge threshold, independent of any panel's
granularity, and a command SHALL merge a point it produced with an existing
point when the two are closer than that threshold instead of creating a second
point there. A division whose pieces would be shorter than the threshold SHALL
reduce its part count instead, and every such reduction SHALL be in the report.
Existing panels SHALL NOT be repaired by this rule; it applies only to the
geometry a command is producing.

#### Scenario: A cut point lands on a vertex

- **WHEN** a division's cut point falls within the merge threshold of a vertex
  that already exists
- **THEN** no second vertex is created, the existing vertex is used, and the
  report names the merge

#### Scenario: Too many parts for the edge

- **WHEN** a division is requested whose pieces would be shorter than the merge
  threshold
- **THEN** the part count is reduced to what fits, the division is applied with
  that count, and the report says the count was reduced

### Requirement: An edge or an edge chain can be divided into equal parts

The editor SHALL divide a selected edge, or a chain of consecutive edges, into a
requested number of equal-length parts by arc length, inserting the joining
points without changing the shape of the divided curve beyond the fitting
tolerance. Dividing the same curve twice SHALL give the same shape as dividing
it once, within the same tolerance.

#### Scenario: Divide into four

- **WHEN** an edge is divided into four parts
- **THEN** three vertices are added at the quarter points of its arc length, the
  outline's shape and area are unchanged, and the panel meshes at the same
  granularity

#### Scenario: Divide a chain

- **WHEN** three consecutive edges of an outline are divided into five parts
- **THEN** the cuts are placed at equal arc length along the whole chain, an
  edge that a cut falls inside is divided at that point, and no other edge moves

#### Scenario: Divide a whole closed outline

- **WHEN** the whole outline is selected and divided into ten parts
- **THEN** the ten parts are equal in arc length and the outline stays a single
  closed loop

#### Scenario: Instance chain follows

- **WHEN** a panel that has copies is divided
- **THEN** every member of the instance chain receives the same division and
  stays index-aligned with its source

### Requirement: A division can be driven by a target length and a cut count

The editor SHALL offer division by a target length, where the user gives the
distance and the number of cuts, the number of cuts defaulting to one and being
capped at what the selection can hold. It SHALL insert a point every target
length along the arc length until the requested number of cuts is reached or the
remaining length can no longer hold another piece, and the last piece SHALL
absorb the remainder. It SHALL report the number of pieces, the achieved lengths
and the remainder, and SHALL name the cap when the requested cut count exceeded
it.

#### Scenario: One cut at a target length

- **WHEN** a 100 mm edge is cut once at a target length of 30 mm
- **THEN** the edge becomes 30 mm and 70 mm, and the report names the 70 mm
  remainder

#### Scenario: Three cuts at a target length

- **WHEN** a 100 mm edge is cut three times at a target length of 30 mm
- **THEN** the edge becomes 30, 30, 30 and 10 mm, and the report names the 10 mm
  remainder

#### Scenario: More cuts than fit

- **WHEN** a 20 mm edge is asked for three cuts of 30 mm
- **THEN** the cut count is capped, the cap is reported as the maximum for that
  selection, and the edge is cut as many times as the length allows

### Requirement: A corner can be rounded, chamfered or hollowed

The editor SHALL treat a corner when one vertex of the outline is selected - a
point in the middle of an edge is not a corner - and SHALL place two points on
the adjacent edges at the tangent length for the requested radius, joined by a
tangent arc in `ROUND`, by a straight edge in `CHAMFER`, and by the mirrored arc
in `CONCAVE`. `ROUND` and `CHAMFER` SHALL remove the corner material and
`CONCAVE` SHALL add it. The editor SHALL refuse a radius whose tangent length
does not fit the adjacent edges, naming the largest radius that fits, and SHALL
keep the outline a single closed loop.

#### Scenario: Fillet a corner

- **WHEN** a right-angle corner with 50 mm edges is rounded with a 10 mm radius
- **THEN** the corner is replaced by an arc of that radius tangent to both
  edges, the panel area decreases by the corner area, and the outline is still
  a single closed loop

#### Scenario: Chamfer the same corner

- **WHEN** the same corner is chamfered with the same radius
- **THEN** the corner is replaced by the straight edge between the same two
  tangent points

#### Scenario: Hollow the same corner

- **WHEN** the same corner is hollowed with the same radius
- **THEN** an arc is inserted on the other side of the chord and the panel area
  increases

#### Scenario: Radius too large

- **WHEN** a radius larger than the adjacent edges allow is requested
- **THEN** the command is refused, the largest fitting radius is reported, and
  the panel is unchanged

#### Scenario: Several corners in one run

- **WHEN** several vertices of the outline are selected and their tangent
  lengths do not overlap
- **THEN** each selected vertex is treated in one undo step

#### Scenario: Overlapping corners are refused

- **WHEN** several vertices are selected and two tangent lengths would overlap
  on the edge between them
- **THEN** the command is refused and names the vertex whose radius does not fit

### Requirement: An edge can be extended by rotating one half of the panel about a pivot

The editor SHALL take a pivot point and a target point on the outline, the
distance between them being the radius, and SHALL divide the panel by the chord
between them. It SHALL rotate the half on the chosen side of the radius rigidly
about the pivot by a requested angle that starts at zero and never closes, and
SHALL fill what opens with the sector that has the pivot as its apex, the radius
as its radius and the requested angle as its angle. The resulting outline SHALL
be the stationary half's outline, the rotated half's outline and a new arc edge
centred on the pivot with the radius, running from the target point to its
rotated image. The area SHALL increase by the sector's area. No internal line
SHALL be created for either radius.

#### Scenario: Open a measured fan

- **WHEN** the pivot is at the corner of a panel, the target is 60 mm along one
  edge and the fan is opened by 30 degrees
- **THEN** a new arc edge of radius 60 mm and 30 degrees is added, the half on
  the rotating side moves rigidly with it, no other vertex of that half is
  moved relative to its neighbours, and the report names the added area

#### Scenario: Zero angle

- **WHEN** the fan is opened by zero degrees
- **THEN** the panel is unchanged, other than being resewn where the split
  changed an edge

#### Scenario: Refusals

- **WHEN** the pivot or the target is not on the outline, or the chord between
  them crosses the outline, or the result crosses itself
- **THEN** the command is refused with the reason and the panel is unchanged

#### Scenario: The angle is adjustable afterwards

- **WHEN** the angle is changed in Blender's adjust-last-operation panel after a
  fan was opened
- **THEN** the panel is rebuilt from its pre-operation state with the new angle,
  rather than a second sector being added

### Requirement: A curve can be edited through points

The editor SHALL offer a tool that reshapes one edge by dragging it, where the
edge is fitted through the dragged position instead of the drag being a fixed
circle. The tool SHALL keep the two ends attached to their neighbouring edges,
and it SHALL store no centre, radius or sweep on the edge.

#### Scenario: Drag a straight edge into a curve

- **WHEN** a straight edge is dragged off its line
- **THEN** the edge becomes a curve through the dragged position, its ends stay
  where they were, and the panel area changes with the curve

#### Scenario: Drag an existing curve

- **WHEN** a curve is dragged near its middle
- **THEN** the curve follows the pointer and stays within the fitting tolerance
  of the shape the pointer described

#### Scenario: No arc parameters are stored

- **WHEN** an edge was created by a command that produced an exact arc
- **THEN** dragging it afterwards leaves it a spline through the dragged points,
  with no residual radius or sweep

### Requirement: A curve produced exactly keeps its exact form

A command SHALL write an edge as a Bezier when that Bezier reproduces the
intended curve exactly - a tangent arc from a corner, the outer arc of a fan -
and SHALL otherwise write a spline. A straight piece SHALL always stay a
straight two-point edge.

#### Scenario: Fillet keeps its circle

- **WHEN** a corner is rounded
- **THEN** the inserted edge is a Bezier that reproduces the requested circle
  within the sampling tolerance, not a spline approximation of it

#### Scenario: Fan keeps its circle

- **WHEN** a fan is opened
- **THEN** the outer arc edge reproduces the requested circle within the
  sampling tolerance
