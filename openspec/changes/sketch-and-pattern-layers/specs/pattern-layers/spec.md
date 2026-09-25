## Purpose

Splits a pattern into the Sketch a pattern maker draws and the Pattern that carries
it, so one Sketch serves every copy of a pattern and everything computed from a
Sketch - sections, samples, mesh, stitches - is rebuilt on demand instead of
being kept in step by hand.

## ADDED Requirements

### Requirement: An instance chain holds one Sketch

The authored vector geometry of a pattern - its vertices, edges, their handles and
spline points and its internal lines - SHALL be held in one Sketch per instance
chain, and every member of that chain SHALL reference that one Sketch. Reading
any member SHALL report the same Sketch identity, and an edit written through any
member SHALL be visible through every other member without touching them one by
one.

#### Scenario: A copy shows the same Sketch

- **WHEN** a pattern with a copy has one of its edges moved
- **THEN** the copy reports the moved edge and both members report the same Sketch identity

#### Scenario: Editing through the copy

- **WHEN** an edge is moved through the copy rather than through the source
- **THEN** the source reports the moved edge as well

#### Scenario: Two Sketches that are not linked

- **WHEN** two patterns were created independently
- **THEN** they report different Sketch identities and an edit to one leaves the other unchanged

#### Scenario: A geometry element does not name a pattern

- **WHEN** a caller that holds only a vertex, an edge, a control point or an internal line asks which pattern it belongs to
- **THEN** the element reports the Sketch it is stored in, and the pattern is the owner of that Sketch rather than something the element claims to be

#### Scenario: A new element has its own identity

- **WHEN** a point, an edge or a control point is written into a Sketch
- **THEN** it reports an identity of its own and the Sketch it was written into from that moment, and no lookup by identity can hand one element's place to another

#### Scenario: A collection a tool rewrote answers for what it holds now

- **WHEN** a tool rewrites a collection - a corner trims an edge into a spline, a split writes the pieces' control points - and a pick then names one of those points
- **THEN** the identity it reads back is an element the collection still holds, so the point can be selected and moved

#### Scenario: An element stays readable while its collection is written to

- **WHEN** an item is added to a collection whose elements an edit already holds - a tool that splits an edge holds that edge while it adds another
- **THEN** the element still answers which Sketch it is in, and the tool reads its elements back from the collection after each write rather than writing through a wrapper the collection has retired

#### Scenario: A snap is read against the shape it was taken on

- **WHEN** an outline is edited and the edge finder still holds the snapshot it took before that edit
- **THEN** the next snap checks the snapshot against the patterns as they are, takes the finder again from the pointer when it no longer fits, and answers an edge of the shape the pattern has now

### Requirement: A Sketch carries the first section stage, crossings included

Every Sketch SHALL carry the sections its edges are divided into at the first
stage: one section per edge to begin with, then the pieces a crossing cuts them
into. A crossing between the outline and an internal line, and a crossing between
two internal lines, SHALL split the sections of both curves, and the pieces of an
internal line that lie outside the outline SHALL be marked as outside. This stage
SHALL depend on the Sketch alone: the number of pieces and the inside/outside
marking of a Sketch MUST NOT change when a pattern's sampling granularity
changes.

#### Scenario: A line crosses the outline

- **WHEN** an internal line is drawn across the outline
- **THEN** the outline and the line each carry additional sections at the crossing, and the parts of the line outside the outline are marked outside

#### Scenario: A line inside the pattern

- **WHEN** an internal line lies entirely inside the outline
- **THEN** no piece of it is marked outside

#### Scenario: Two internal lines cross

- **WHEN** two internal lines cross each other
- **THEN** both lines carry additional sections at that crossing

#### Scenario: A cut narrows the piece it leaves behind

- **WHEN** a crossing cuts one edge into pieces
- **THEN** each piece spans only its own part of the edge, so a pattern samples it by its own length and no piece carries more samples than its length and the pattern's granularity ask for

#### Scenario: The stage does not follow the granularity

- **WHEN** the same Sketch is sampled by two patterns with different granularities
- **THEN** both report the same pieces and the same inside/outside marking

#### Scenario: A piece names what it was cut from

- **WHEN** an edit replaces the edge a copied pattern's piece was cut from and the copy has not been rebuilt
- **THEN** that piece reports no edge and no pattern, and every consumer skips it instead of following a wrapper that now names a different edge

### Requirement: A write marks the patterns that read the Sketch

A write that changes a Sketch SHALL mark every Pattern that reads it: that
Pattern's outline state, its own copy of the first stage, its samples, its render
line and the sewings that reach it. A write SHALL do no other derived work: it
MUST NOT sample a pattern, rebuild a mesh, re-link a sewing walk or touch the
simulation payload. A write that leaves the Sketch as it was SHALL mark nothing.

#### Scenario: A topology edit does no derived work

- **WHEN** a vertex is moved in a Sketch used by two patterns with a mesh each
- **THEN** the edit returns with both patterns marked, and both still show the mesh they had

#### Scenario: Repeating the same value

- **WHEN** an edge is set to the handle type it already has
- **THEN** the Sketch is unchanged and nothing is marked

### Requirement: Derived data is rebuilt when a marked pattern is read

A marked Pattern SHALL rebuild its copy of the first stage and its samples when a
consumer needs them - the mesh path, a simulation prepare, a read that promises
current samples - and a Pattern that is not marked MUST NOT compute again. A
rebuild that cannot run (crossing or degenerate outline) SHALL keep the last good
derived data, record the reason and stay marked, so the next reader tries again.

#### Scenario: One rebuild per edit

- **WHEN** two consumers ask a Pattern for its mesh after one Sketch write
- **THEN** the Pattern rebuilds once and both consumers see the same mesh

#### Scenario: A current Pattern is not rebuilt

- **WHEN** a consumer reads a Pattern that is not marked
- **THEN** no sampling or mesh rebuild happens

#### Scenario: Preparation rebuilds what was marked

- **WHEN** a simulation is prepared while a participating Pattern is marked
- **THEN** that Pattern is rebuilt first and the engine receives the geometry the Sketch has now

### Requirement: A rebuild that cannot run keeps the last good result

A Sketch that cannot be sampled - an outline that crosses itself, a degenerate
outline - MUST NOT reach the sampler. The Pattern SHALL keep the derived data it
had and SHALL record why the rebuild did not run, so the pattern is drawn as
invalid and a later consumer sees the reason. A later edit that makes the Sketch
samplable SHALL let the next rebuild succeed and SHALL clear the reason.

#### Scenario: A crossing outline

- **WHEN** an edit leaves the outline crossing itself
- **THEN** the Pattern keeps its previous mesh and records the crossing as the reason

#### Scenario: The Sketch is fixed

- **WHEN** the vertices are moved so the outline no longer crosses
- **THEN** the next rebuild builds the mesh and the reason is cleared

#### Scenario: The refusal does not undo the edit

- **WHEN** a rebuild refuses because the outline crosses
- **THEN** the Sketch keeps the geometry that was written

### Requirement: A copy shares the Sketch and a detach gives a Pattern its own

Copying a pattern SHALL NOT copy its vector geometry: the copy SHALL join the
source's instance chain and reference the same Sketch. Detaching a Pattern SHALL
give that Pattern a private copy of the Sketch in the state it is in, SHALL leave
the chain of the remaining members intact, and thereafter SHALL be the only way
two Patterns of one origin hold different Sketches. Detaching a Pattern that is
already alone in its chain SHALL be reported as having nothing to detach.

#### Scenario: A copy costs no geometry

- **WHEN** a pattern with an internal line is copied
- **THEN** the copy reports one Sketch shared with the source, and the Sketch's element counts are unchanged

#### Scenario: A chain is read from the Sketch

- **WHEN** a pattern and its copy are asked which patterns are in their chain
- **THEN** each names the patterns that read the same Sketch, and no separate list of members is stored or kept in step

#### Scenario: Detaching leaves the other members' chain alone

- **WHEN** one of three members of a chain is detached
- **THEN** the other two still read the Sketch they shared, and the detached pattern is the only one that reads its own

#### Scenario: Detach and diverge

- **WHEN** one of three members is detached and its outline is edited
- **THEN** that member reports its own Sketch, the other two still share theirs, and neither of them sees the edit

#### Scenario: Detach reports what it did

- **WHEN** a member of a chain is detached
- **THEN** the report names the Pattern and the Sketch it received, and names the members that stayed linked

### Requirement: Placement and simulation state stay per Pattern

A Pattern SHALL own its name, anchor, rotation, mirror flag, grain direction,
fabric, collision layer, granularity, mesh object, simulation state and its place
in the instance chain, and changing any of them MUST NOT change a Sketch or mark
its geometry. Two Patterns that share a Sketch SHALL be able to differ in
every one of these, and SHALL be sampled, meshed and simulated independently.

#### Scenario: Two patterns of one Sketch with different settings

- **WHEN** two patterns that share a Sketch are given different fabrics and different granularities
- **THEN** each keeps its own fabric and granularity, and each mesh follows its own granularity

#### Scenario: Moving a copy

- **WHEN** a copy is moved or mirrored
- **THEN** no geometry is marked and the other members do not move

#### Scenario: The simulation state is per Pattern

- **WHEN** one pattern of a chain is excluded from the simulation
- **THEN** the other members still take part and the shared Sketch is unchanged

### Requirement: A Pattern picks its own elements

The editor's picking SHALL be per Pattern: a Pattern SHALL hold a temporary table
of the selectable things it draws - each edge, point, spline control point and
Bezier handle of its Sketch - with an id generated for the session, the id pass
SHALL draw those entries with those ids, and a pick SHALL answer with the element
and the Pattern the id was generated for. The table MUST NOT be saved with the
project, and picking MUST NOT sample or otherwise change the scene.

#### Scenario: Two members of one chain are told apart

- **WHEN** a pattern whose chain has a copy has one of its edges clicked
- **THEN** the pick answers with that edge and the Pattern that was clicked, not the other member

#### Scenario: The clicked member becomes the active pattern

- **WHEN** an element of one member of a chain is selected
- **THEN** that member is the project's active pattern, so a tool that works in pattern space works where the click was made

#### Scenario: A seam's side is the pattern that was clicked

- **WHEN** a seam is made by clicking one edge and then another
- **THEN** each side records the member its own click was made on, and two clicks on two members of one chain make a seam between those two

#### Scenario: The picked edge is highlighted where it was clicked

- **WHEN** the first edge of a seam is picked on one member of a chain
- **THEN** that edge is highlighted on that member, and the mark does not move to the member that owns the Sketch

#### Scenario: One edge of two members is a seam

- **WHEN** the second side of a seam is the same edge of another member of the same chain
- **THEN** the preview joins the two members' ends, and only the same edge of the same member - the first side still under the pointer - shows nothing

#### Scenario: A selected seam survives a mode switch

- **WHEN** a seam is selected in the sewing mode and the editor is then in another mode
- **THEN** that seam is drawn dimmed once, read from the side the selection holds, and no seam that is no longer there is drawn at all

#### Scenario: A drag acts on the clicked Pattern

- **WHEN** a point is dragged through the picked Pattern
- **THEN** the edit is written to the shared Sketch once and every member shows it

#### Scenario: A removal drops what it removed from the selection

- **WHEN** a command removes an element the selection names - a merged corner takes its vertex and the edge it consumes with it
- **THEN** the selection no longer holds those identities, so every reader of the selection resolves every entry it holds

#### Scenario: A tool's preview belongs to the tool

- **WHEN** a tool has drawn what a click would act on and another tool is then picked
- **THEN** the preview goes with the tool that drew it, instead of staying on screen for a tool that is no longer being used

#### Scenario: The merge keeps the halves it leaves

- **WHEN** a run of consecutive selected points is merged into one point
- **THEN** the merged point is at the centre of the run, the first of its points keeps the identity and takes that place, the rest go with the edges between them, and the two edges that remain at the ends are re-pointed at it, each moving only the control point at the end that moved, so the halves that stay have the shape they had

#### Scenario: Control points of a spline edge merge

- **WHEN** two or more control points of one spline edge are selected and merged
- **THEN** they become one control point of that edge, at the centre of the run, and the rest of the edge is untouched

### Requirement: An interactive edit is tested only while the switch says so

An interactive edit SHALL test the outline it would write for a self-crossing
only while the scene's Check Self-Intersection switch is on. While the test is
on, a tool driven by the pointer SHALL keep the pointer inside the values that
pass it, so a drag is never answered with a refusal it could have clamped, and a
refusal that does come from the test SHALL name the switch. The switch SHALL
decide nothing else: a mesh and a simulation test the outline whatever it says.

#### Scenario: A corner drag never asks for a radius it cannot write

- **WHEN** a corner is dragged from no radius outward to well past the end of its edges
- **THEN** every radius the pointer reaches is one the command writes, and the gap between the largest radius that fits and the first radius that merges - which holds nothing that can be written at all - is passed by snapping to the nearer end of it

#### Scenario: A merge that would cross the outline

- **WHEN** the switch is on and the only merge a corner has would cross the outline
- **THEN** the drag stops at the largest radius that fits and the run writes that, without reporting a refusal

#### Scenario: The same merge with the switch off

- **WHEN** the switch is off
- **THEN** the merge is written like any other edit, and the mesh stage is what reports the crossing

#### Scenario: A drag previews every curve it moves

- **WHEN** the move gesture takes a point of the outline, of an internal line, or of a line's control points
- **THEN** the curve that point belongs to is drawn following the pointer, and a curve the gesture does not move is left without a preview

#### Scenario: A selected control point keeps its edge's handles

- **WHEN** a handle or a spline point of an edge is selected
- **THEN** that edge's handles are drawn and remain pickable, so the point is moved through the handle it is attached to instead of floating on its own

#### Scenario: A dragged handle is shown on every member

- **WHEN** a handle of one member of a chain is dragged
- **THEN** the preview draws that handle on every member, each with its own transform, so the hand follows the pointer wherever the chain is drawn

#### Scenario: A tool writes the shape it previewed

- **WHEN** a tool measures a plan and then writes it - the fan's pivot and target on two different edges
- **THEN** the outline it leaves is the shape its plan describes, with the measured points as vertices of it

#### Scenario: Picking draws nothing else

- **WHEN** the id pass runs for a pattern whose derived data is stale
- **THEN** it draws the pattern's elements without sampling it, and the staleness is left for the consumer that needs the samples

#### Scenario: The id pass does not take the display mark

- **WHEN** the id pass runs before the draw for a pattern whose display is marked for a rebuild
- **THEN** it draws that pattern's current lines and leaves the mark for the draw, which rebuilds the points and the spline points as well

### Requirement: A sewing change invalidates the patterns it links

Adding, removing or changing a seam SHALL mark the section copy, the samples and
the mesh of every Pattern in the chains the seam reaches as stale, and SHALL NOT
rebuild them. A stale Pattern SHALL be rebuilt from its Sketch - the first section
stage cloned again, never patched - when a consumer asks: the display path for
what it draws, the simulation when it prepares. A seam edit SHALL therefore be
one cheap operation, whatever the size of the connected component.

#### Scenario: A seam edit does not rebuild meshes

- **WHEN** a seam between two patterns is created, removed or moved
- **THEN** both patterns report their mesh as stale and neither mesh is rebuilt by the edit itself

#### Scenario: Preparing rebuilds what the seam invalidated

- **WHEN** a simulation is prepared after a seam change
- **THEN** every stale Pattern in the affected chains is rebuilt from its Sketch first, and the engine receives geometry that matches the seam graph

#### Scenario: A copy cut by an old linking run is not reused

- **WHEN** a Pattern whose section copy was cut by a linking run that has since changed is rebuilt
- **THEN** the copy is taken from the Sketch's first stage again, so the old cuts are gone

#### Scenario: A topology edit still meshes at once

- **WHEN** a tool moves a point, divides an edge, treats a corner or deletes an element
- **THEN** every pattern that reads the Sketch the tool wrote has its mesh rebuilt before the tool returns

#### Scenario: A topology tool asks the Sketch, not the chain

- **WHEN** any topology tool runs on a pattern whose chain has copies
- **THEN** it writes the Sketch once and asks the Sketch to rebuild the mesh of every pattern that reads it (`Sketch.rebuild_meshes`), so the tool itself walks no chain; only a tool that draws a preview of the whole chain - the move gesture - reads the members

### Requirement: Editing only what has to be recomputed

An edit SHALL recompute only what its own kind requires. A topology edit, and a
change of a pattern's granularity, SHALL rebuild the mesh of the patterns they changed
before they return. A change that can move the pieces a mesh is built from without
being a topology edit - a seam edit, whose linking run cuts sections in the patterns
it reaches - SHALL mark that work stale instead of doing it, and SHALL NOT
rebuild anything itself. A change that can do neither - a fabric, a placement, a
display setting, a collision layer, a grain direction, a simulation state -
SHALL NOT rebuild a section or a mesh, and SHALL NOT mark one stale: the engine
payload that carries those fields is assembled when a simulation prepares.

A derived rebuild SHALL happen when a consumer asks for the derived data, and the
work it does SHALL be the same whether it was asked for by the editor or by a
simulation.

A pattern SHALL keep a copy of the boundary samples its last mesh was built from,
written when that mesh is built, so a check that runs without opening the add-on
can read the pattern's shape out of the saved file. That copy SHALL NOT be read back
as the samples a mesh is built from: those are taken from the Sketch again.

#### Scenario: A fabric change does not mesh anything

- **WHEN** a pattern's fabric is changed
- **THEN** no section is rebuilt, no mesh is regenerated and nothing is marked stale, and the pattern reports the change

#### Scenario: Moving a pattern does not mesh anything

- **WHEN** a pattern is moved, rotated or mirrored
- **THEN** only its placement changes: no section, sample or mesh is rebuilt or marked stale

#### Scenario: A granularity change meshes that pattern

- **WHEN** a pattern's granularity is changed
- **THEN** that pattern is sampled and meshed again before the change returns, and the other members of its chain are left as they are

#### Scenario: The editor draws a stale pattern without meshing it

- **WHEN** a stale pattern is drawn in a display mode that needs its mesh
- **THEN** the mesh is rebuilt for that pattern (and only if its mesh is what is missing), not for every pattern of its chain

#### Scenario: The saved samples are the ones the mesh was built from

- **WHEN** a pattern's mesh is generated
- **THEN** the copy kept on the pattern holds that mesh's boundary samples, and the next mesh is generated from the Sketch rather than from the copy

### Requirement: A seam names the Pattern it belongs to

A seam SHALL be defined on the patterns it joins: each side SHALL name the
Pattern, the Sketch element it runs along and a position on that element. The
stitch walk of a seam - its sections, link identities and stitch pairs - is
derived data of those patterns and SHALL be rebuilt when either pattern is marked.
A side whose named element no longer exists in the Sketch it reads SHALL be
dropped in the rebuild and reported, and the seam SHALL NOT be
left pointing at geometry that is gone.

#### Scenario: A seam survives an edit that keeps its edge

- **WHEN** the Sketch of a sewn pattern is edited without removing the edge the seam names
- **THEN** the seam keeps its side and its stitch walk is rebuilt against the Sketch the pattern has now

#### Scenario: A seam whose edge is deleted

- **WHEN** an edit removes the edge a seam side names
- **THEN** that side is dropped, the seam is reported, and no later read fails on it

#### Scenario: A seam between two patterns of one Sketch

- **WHEN** two patterns that share a Sketch are sewn to each other
- **THEN** each side reports its own Pattern and the walk is built per pattern

### Requirement: The two layers are what is stored

A Sketch and the Patterns that reference it SHALL be stored with the project, so
that saving and reopening a file keeps one Sketch per chain and every Pattern
attribute. A scene saved by an earlier build SHALL NOT be converted: a pattern that
carries no Sketch has no geometry, and the add-on MUST NOT invent a Sketch for it
or link patterns that were copies before.

#### Scenario: A saved file reopens with its layers

- **WHEN** a project with a chain of two patterns, an internal line and a seam is saved and reopened
- **THEN** the chain reports one Sketch with the same elements, and each Pattern reports its own placement, granularity and seam

#### Scenario: A file from an earlier build

- **WHEN** a scene saved before this change is opened
- **THEN** its patterns carry no Sketch and no geometry is invented for them
