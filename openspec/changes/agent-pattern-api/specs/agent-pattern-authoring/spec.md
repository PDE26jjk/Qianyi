## Purpose

Let a script or an agent create, change, place, copy, remove and read back a
panel through calls that validate before they write, so a broken outline never
reaches the mesh stage and a caller never has to know the add-on's internals.

## ADDED Requirements

### Requirement: Panels are addressed by name and a create reports the name

A panel SHALL be addressed by its name. Creating a panel whose name is taken
SHALL give the new panel a suffixed name in the add-on's existing format and
return both the requested and the final name. Addressing a name that does not
exist SHALL be refused with the names that do exist.

#### Scenario: A taken name is suffixed

- **WHEN** a panel is created with a name another panel already uses
- **THEN** the new panel gets the suffixed name and the result reports the requested name and the final name

#### Scenario: An unknown name

- **WHEN** a call names a panel that does not exist
- **THEN** it is refused and the reason names the panels the project does have

### Requirement: A panel is created from points in millimetres

Creating a panel SHALL take its outline as points in millimetres, close the loop
itself, and order it counter-clockwise. There SHALL be no variant that builds an
open outline: every panel in this add-on is a closed loop.

#### Scenario: Four points become a panel

- **WHEN** a panel is created from four points
- **THEN** it has four vertices and four edges, its mesh is built, and 1000 millimetres of outline measure one metre in world space

#### Scenario: The loop is closed and counter-clockwise

- **WHEN** a panel is created from points given clockwise
- **THEN** the stored outline runs counter-clockwise and the last point connects back to the first

### Requirement: A panel can be read back with its edges and its sewings

Reading a panel SHALL report its identity and summary - name, vertex, edge and
internal line counts, granularity, collision layer, fabric, mesh object, whether
it came from a generator, and the members of its instance chain - together with
an edge table. Each edge entry SHALL carry its index, label, kind (straight,
Bezier or spline), both endpoint indices and coordinates, its handles, its
spline point count and its length. The same read SHALL report every sewing that
touches the panel. The point coordinates SHALL be available from a separate
call, so a caller that only needs the topology does not pay for them.

#### Scenario: The edges of a panel

- **WHEN** a panel's edges are read
- **THEN** every edge appears once with its index, endpoints, kind and length, in outline order

#### Scenario: The sewings of a panel

- **WHEN** a panel's sewings are read
- **THEN** each one is reported with the side that belongs to this panel, the edge index and label of both sides, the positions, the direction flag, the colour and the stitch count

#### Scenario: The per-panel list agrees with the full list

- **WHEN** the sewings reported for a panel are compared with the sewings of the project filtered by that panel
- **THEN** the two sets are the same

### Requirement: Geometry can be edited point by point

The surface SHALL offer setting a vertex; adding a vertex by splitting an edge
and removing one by merging its two edges; setting an edge's handle position and
handle type; adding and removing a spline point; and adding and removing an
internal line. An edit SHALL leave the outline and the derived mesh in the state
the interactive tools would leave them in, and an edit that would leave an
unusable outline SHALL put the value it changed back before it reports the
refusal.

#### Scenario: A vertex is moved

- **WHEN** a vertex is moved and its mesh is regenerated
- **THEN** the new position is in the outline and in the mesh

#### Scenario: An edge is turned into a curve

- **WHEN** an edge's handles are given a position and a non-vector type
- **THEN** the edge reports that kind and its sampled outline follows the curve

#### Scenario: An internal line is added

- **WHEN** an internal line is added from points inside the outline
- **THEN** the panel reports one more internal line and its mesh reflects the cut

### Requirement: An edit reaches the whole instance chain

When the edited panel is a member of an instance chain, the edit SHALL be written
to every member, and the result SHALL list them. Copies hold the same local
geometry, so this is the same rule the interactive tools follow.

#### Scenario: Editing a panel that has a mirror copy

- **WHEN** a panel with a mirror copy is edited
- **THEN** the copy receives the same local geometry and the result names both panels

### Requirement: A panel can be placed, mirrored and copied

The surface SHALL set a panel's anchor (millimetres), rotation (radians), grain
direction and collision layer; mirror it in place; and copy it as an instance or
a mirror at a given anchor. A copy SHALL be part of the same instance chain as
its source and SHALL be reported by name.

#### Scenario: An instance copy is made

- **WHEN** a panel is copied as a mirror at an anchor
- **THEN** the copy exists with its own name and mesh, reports the source's chain membership, and both panels report each other as chain members

### Requirement: Removing panels reports what went with them

Removing a panel SHALL report the names it removed and the number of sewings
that were dropped because an element they used disappeared. It SHALL NOT ask for
confirmation. A panel a generator owns SHALL be refused here, pointing at the
generator's own detach or remove, so a group is never deleted by surprise.

#### Scenario: A sewn panel is removed

- **WHEN** a panel carrying a sewing is removed
- **THEN** the result names the panel and reports the sewing that went with it

### Requirement: A write validates before it writes and refuses with the reason

Every write SHALL check its inputs and the outline it would produce before
changing anything, and SHALL refuse - leaving the scene unchanged - when the
outline crosses itself, when two vertices would end up closer together than the
mesh tolerance, when the granularity is not positive, or when a named object
does not exist. A call that fails after it has written SHALL report what it
already changed.

#### Scenario: A crossing outline is refused

- **WHEN** a create or an edit would leave a self-intersecting outline
- **THEN** it is refused with the reason, and neither the panel nor its mesh changes

#### Scenario: A degenerate outline is refused

- **WHEN** an edit would put two vertices closer together than the mesh tolerance
- **THEN** it is refused with the distance and the tolerance

#### Scenario: The reason reaches the caller

- **WHEN** any of these refusals happen
- **THEN** the caller receives the reason and a next action, and no dialog is opened
