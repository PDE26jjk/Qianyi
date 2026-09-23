## Purpose

Splits a panel into the shape a pattern maker draws and the piece that carries
it, so one shape serves every copy of a panel and everything computed from a
shape - sections, samples, mesh, stitches - is rebuilt on demand instead of
being kept in step by hand.

## ADDED Requirements

### Requirement: An instance chain holds one shape

The authored vector geometry of a panel - its vertices, edges, their handles and
spline points and its internal lines - SHALL be held once per instance chain, and
every member of that chain SHALL reference that one shape. Reading any member
SHALL report the same shape identity, and a change written through any member
SHALL be visible through every other member without touching them one by one.

#### Scenario: A copy shows the same shape

- **WHEN** a panel with a copy has one of its edges moved
- **THEN** the copy reports the moved edge and both members report the same shape identity

#### Scenario: Editing through the copy

- **WHEN** an edge is moved through the copy rather than through the source
- **THEN** the source reports the moved edge as well

#### Scenario: Two shapes that are not linked

- **WHEN** two panels were created independently
- **THEN** they report different shape identities and an edit to one leaves the other unchanged

### Requirement: The shape carries the first section stage, crossings included

Every shape SHALL carry the sections its edges are divided into at the first
stage: one section per edge to begin with, then the pieces that crossings cut
them into. A crossing between the outline and an internal line, and a crossing
between two internal lines, SHALL split the sections of both curves, and the
pieces of an internal line that lie outside the outline SHALL be marked as
outside. This stage SHALL depend on the shape alone: the number of pieces and
the inside/outside marking of a shape MUST NOT change when a panel's sampling
granularity changes.

#### Scenario: A line crosses the outline

- **WHEN** an internal line is drawn across the outline
- **THEN** the outline and the line each carry additional sections at the crossing, and the parts of the line outside the outline are marked outside

#### Scenario: A line inside the panel

- **WHEN** an internal line lies entirely inside the outline
- **THEN** no piece of it is marked outside

#### Scenario: Two internal lines cross

- **WHEN** two internal lines cross each other
- **THEN** both lines carry additional sections at that crossing

#### Scenario: The stage does not follow the granularity

- **WHEN** the same shape is sampled by two panels with different granularities
- **THEN** both report the same pieces and the same inside/outside marking

### Requirement: A shape change raises one revision and nothing else

A write that changes a shape SHALL raise that shape's revision by one, and SHALL
do no other work: it MUST NOT sample a panel, rebuild a mesh, re-link a sewing
walk or touch the simulation payload. A write that leaves the shape as it was
SHALL leave the revision alone.

#### Scenario: A topology edit does no derived work

- **WHEN** a vertex is moved on a shape used by two panels with a mesh each
- **THEN** the write returns with the revision raised, and both panels still show the mesh they had

#### Scenario: Repeating the same value

- **WHEN** an edge is set to the handle type it already has
- **THEN** the revision is unchanged

### Requirement: Derived data is baked on demand

Everything a piece computes from its shape - sampled points, the mesh, the
stitch walk of its seams and the payload handed to the engine - SHALL record the
shape revision it was baked from. A consumer that needs derived data SHALL bake
the piece when its record is older than the shape revision, and baking SHALL be
idempotent: baking a piece that is already current MUST NOT compute again, and
baking twice after one edit SHALL leave the same result.

#### Scenario: One bake per edit

- **WHEN** two consumers ask a piece for its mesh after one shape edit
- **THEN** the piece bakes once and both consumers see the same mesh

#### Scenario: A fresh piece is not baked again

- **WHEN** a consumer reads a piece whose derived data is already current
- **THEN** no sampling or mesh rebuild happens

#### Scenario: Preparation bakes what is stale

- **WHEN** a simulation is prepared while a participating piece is stale
- **THEN** that piece is baked first and the engine receives the geometry the shape has now

### Requirement: A bake that cannot run keeps the last good result

A shape that cannot be sampled - an outline that crosses itself, a degenerate
outline - MUST NOT reach the sampler. The piece SHALL keep the derived data it
had, SHALL record why the bake did not run, and every later consumer and read
SHALL report that piece as stale with that reason until a bake succeeds again.
A later edit that makes the shape samplable SHALL let the next bake succeed and
SHALL clear the reason.

#### Scenario: A crossing outline

- **WHEN** an edit leaves the outline crossing itself
- **THEN** the piece keeps its previous mesh, and a read reports it as stale with the crossing as the reason

#### Scenario: The shape is fixed

- **WHEN** the vertices are moved so the outline no longer crosses
- **THEN** the next bake rebuilds the mesh and the reason is cleared

#### Scenario: The refusal does not undo the edit

- **WHEN** a bake refuses because the outline crosses
- **THEN** the shape keeps the geometry that was written and the revision stays raised

### Requirement: A copy shares the shape and a detach gives a piece its own

Copying a panel SHALL NOT copy its vector geometry: the copy SHALL join the
source's instance chain and reference the same shape. Detaching a piece SHALL
give that piece a private copy of the shape in the state it is in, SHALL leave
the chain of the remaining members intact, and thereafter SHALL be the only way
two pieces of the same origin hold different shapes. Detaching a piece that is
already alone in its chain SHALL be reported as having nothing to detach.

#### Scenario: A copy costs no geometry

- **WHEN** a panel with an internal line is copied
- **THEN** the copy reports one shape shared with the source, and the shape's element counts are unchanged

#### Scenario: Detach and diverge

- **WHEN** one of three members is detached and its outline is edited
- **THEN** that member reports its own shape, the other two still share theirs, and neither of them sees the edit

#### Scenario: Detach reports what it did

- **WHEN** a member of a chain is detached
- **THEN** the report names the piece and the shape it received, and names the members that stayed linked

### Requirement: Placement and simulation state stay per piece

A piece SHALL own its name, anchor, rotation, mirror flag, grain direction,
fabric, collision layer, granularity, mesh object, simulation state and its
place in the instance chain, and changing any of them MUST NOT change a shape or
raise a shape revision. Two pieces that share a shape SHALL be able to differ in
every one of these, and SHALL be sampled, meshed and simulated independently.

#### Scenario: Two pieces of one shape with different settings

- **WHEN** two pieces that share a shape are given different fabrics and different granularities
- **THEN** each keeps its own fabric and granularity, and each mesh follows its own granularity

#### Scenario: Moving a copy

- **WHEN** a copy is moved or mirrored
- **THEN** the shape revision is unchanged and the other members do not move

#### Scenario: The simulation state is per piece

- **WHEN** one piece of a chain is excluded from the simulation
- **THEN** the other members still take part and the shared shape is unchanged

### Requirement: A seam names the piece it belongs to

A seam SHALL be defined on the pieces it joins: each side SHALL name the piece,
the shape element it runs along and a position on that element. The stitch walk
of a seam - its sections, link identities and stitch pairs - is derived data of
those pieces and SHALL be rebuilt when either shape's revision moves. A side
whose named element no longer exists in the shape it was baked against SHALL be
dropped in the rebuild and reported, and the seam SHALL NOT be left pointing at
geometry that is gone.

#### Scenario: A seam survives a shape edit that keeps its edge

- **WHEN** the shape of a sewn piece is edited without removing the edge the seam names
- **THEN** the seam keeps its side and its stitch walk is rebuilt against the shape the piece has now

#### Scenario: A seam whose edge is deleted

- **WHEN** an edit removes the edge a seam side names
- **THEN** that side is dropped, the seam is reported, and no later read fails on it

#### Scenario: A seam between two pieces of one shape

- **WHEN** two pieces that share a shape are sewn to each other
- **THEN** each side reports its own piece and the walk is built per piece
