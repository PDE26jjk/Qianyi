## Purpose

Gives the pattern editor the edge commands a pattern maker drafts with -
dividing an edge, rounding a corner, extending an edge by an arc and editing an
arc - so panels can be built and corrected inside the add-on.

## ADDED Requirements

### Requirement: An edge or an edge chain can be divided into equal parts

The editor SHALL divide a selected edge, or a chain of consecutive edges, into
a requested number of equal-length parts, inserting the joining points without
changing the shape of the divided curve. A two-point Bezier SHALL stay a Bezier
and a spline SHALL keep its interpolation points, so dividing a curve twice
gives the same shape as dividing it once.

#### Scenario: Divide a straight edge into four

- **WHEN** a straight edge is divided into four parts
- **THEN** three vertices are added at the quarter points, the outline's shape
  and area are unchanged, and the panel meshes at the same granularity

#### Scenario: Divide a curved edge

- **WHEN** a Bezier edge is divided into three parts
- **THEN** the sampled points of the three resulting edges lie on the original
  curve within the panel's sampling tolerance

#### Scenario: Instance chain follows

- **WHEN** a panel that has copies is divided
- **THEN** every member of the instance chain receives the same division and
  stays index-aligned with its source

### Requirement: An edge can be divided by a target segment length

The editor SHALL divide a selected edge or chain into parts of a requested
target length, producing as many whole parts as fit and one remainder part, and
SHALL report the number of parts, the achieved lengths and the remainder. It
SHALL refuse a target length that would produce fewer than two parts, naming
the minimum length for the selection.

#### Scenario: Target length that does not divide evenly

- **WHEN** a 100 mm edge is divided with a 30 mm target
- **THEN** four parts are created (30, 30, 30 and 10 mm) and the report names
  the 10 mm remainder

#### Scenario: Impossible target

- **WHEN** a 20 mm edge is divided with a 30 mm target
- **THEN** the command is refused with the minimum length for the selection and
  the panel is unchanged

### Requirement: A vertex can be filleted into an arc between two points

The editor SHALL replace a selected vertex with two points joined by an arc of
a requested radius, tangent to both adjacent edges, and SHALL remove the corner
material the fillet cuts away. It SHALL refuse a radius that does not fit the
two adjacent edges, naming the largest radius that fits.

#### Scenario: Fillet a corner

- **WHEN** a right-angle corner with 50 mm edges is filleted with a 10 mm
  radius
- **THEN** the corner is replaced by an arc of that radius tangent to both
  edges, the panel area decreases by the corner area, and the outline is still
  a single closed loop

#### Scenario: Radius too large

- **WHEN** a fillet radius larger than an adjacent edge allows is requested
- **THEN** the command is refused, the largest fitting radius is reported, and
  the panel is unchanged

### Requirement: An edge can be extended by an arc that follows its neighbours

The editor SHALL extend a selected edge by adding an arc whose start direction
continues the edge's tangent and whose sweep follows the angle of the
neighbouring edges, with the sweep available as an explicit override. The
extension SHALL be inserted as a new edge rather than by moving existing
vertices.

#### Scenario: Extend a hem by a measured arc

- **WHEN** an edge is extended by an arc with an explicit sweep of 30 degrees
  and a radius
- **THEN** a new arc edge is appended at that end, tangent-continuous with the
  edge it extends, and the panel's other edges are unchanged

#### Scenario: Self-intersection is refused

- **WHEN** an extension makes the outline cross itself and interactive checking
  is on
- **THEN** the command is refused with the crossing point and no vertex is
  added

### Requirement: An arc is a first-class curve

An arc SHALL be creatable as its own edge, either through three points or
through a centre, a radius and a sweep, and SHALL be editable afterwards by
dragging its points and by changing its radius and sweep. An arc SHALL mesh,
sew, render and export like any other edge: the sampling and the engine payload
see only points.

#### Scenario: Create an arc through three points

- **WHEN** an arc is created through three points on a panel
- **THEN** the arc passes through all three within the sampling tolerance and
  its radius and sweep are reported

#### Scenario: Editing keeps it an arc

- **WHEN** the radius of an existing arc is changed
- **THEN** the arc is redrawn with the new radius and its end points stay
  attached to the neighbouring edges

#### Scenario: Scripts use the same commands

- **WHEN** a script divides an edge by target length and then reads the panel
  back
- **THEN** the read reports the same vertices and edge lengths the editor's
  command produces for the same input
