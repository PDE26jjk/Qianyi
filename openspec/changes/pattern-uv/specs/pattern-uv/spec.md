## Purpose

Gives every pattern mesh a UV layer that a fabric texture can sample, seeded
from the pattern's own space and carried across the mesh rebuilds the editor
performs, so a texture stays on the cloth while the pattern is edited.

## ADDED Requirements

### Requirement: Every pattern mesh carries a `UVMap` UV layer

A pattern mesh SHALL carry a UV layer named `UVMap` with one UV value per mesh
loop, and the mesh SHALL keep that layer present and up to date across every
rebuild. An existing layer of that name SHALL be reused rather than duplicated.
A mesh that has never been built has no UV layer, and the layer SHALL NOT be
created for any object that is not a pattern mesh.

#### Scenario: First mesh build

- **WHEN** a pattern is meshed for the first time
- **THEN** its mesh has a UV layer named `UVMap` with one value per loop

#### Scenario: A rebuild keeps exactly one layer

- **WHEN** a pattern whose mesh already has a `UVMap` layer is rebuilt
- **THEN** the mesh still has exactly one UV layer, still named `UVMap`

#### Scenario: A non-pattern object

- **WHEN** a collider or any other object is present
- **THEN** the add-on leaves its UV layers untouched

### Requirement: UVs are per-vertex and written to every loop of that vertex

The UV of a loop SHALL be the UV of the mesh vertex the loop references, so all
loops of one vertex carry the same UV. A UV split a user made by moving
individual loops of a vertex does not survive a rebuild: after a rebuild the
vertex has one UV in every loop again.

#### Scenario: A per-loop split is flattened by a rebuild

- **WHEN** a user moves the loops of one face in the UV editor, giving a vertex
  two different UVs, and the pattern is then rebuilt
- **THEN** that vertex carries a single UV again in every loop

### Requirement: The UV is seeded from pattern space

When a pattern mesh is first built, and whenever its UV is reset, each vertex's
UV SHALL be seeded from that vertex's pattern-space position in the mesh's own
local space, multiplied by the global `uv_scale` setting on the scene's Qianyi
settings. The setting SHALL be saved with the file and SHALL be a single float
that defaults to 1.0. The positions SHALL be the pattern's rest positions - the
same ones a rebuild maps the carried UV from, not the mesh's current vertex
array and not the simulated shape - so a reset and a rebuild cannot place a
vertex in two different spaces.

#### Scenario: Default scale

- **WHEN** a pattern is meshed with `uv_scale` at its default
- **THEN** each vertex's UV equals its pattern-space position, so a pattern one
  metre across spans one unit of UV

#### Scenario: A non-default scale

- **WHEN** `uv_scale` is 2.0 and a pattern is meshed
- **THEN** each vertex's UV is twice its pattern-space position

#### Scenario: The setting survives a reload

- **WHEN** a file is saved with `uv_scale` changed and reopened
- **THEN** the setting reports the saved value

### Requirement: A rebuild carries the mesh's current UV over

When an existing pattern mesh is rebuilt, the new mesh's UV SHALL be carried
over from the UV layer the mesh holds at that moment - including edits the user
made in the UV editor - and not from any value captured at an earlier build. A
new sample point SHALL take the UV that the mesh being replaced assigns to that
point's location, so a vertex whose pattern-space position did not move keeps
its UV and a user's move, rotation or scale of the UV is preserved. A rebuild
that does not change the geometry SHALL leave the UV unchanged.

#### Scenario: Nothing moved

- **WHEN** a pattern is rebuilt and its outline samples land where they were
- **THEN** every vertex's UV is unchanged

#### Scenario: The user moved the UV

- **WHEN** a user translates, rotates or scales a pattern's UV in the UV editor
  and the pattern is then rebuilt
- **THEN** the result carries that same translation, rotation or scale

#### Scenario: The point order changed

- **WHEN** an edit changes the number and order of a pattern's sample points
  and the pattern is rebuilt
- **THEN** the UV follows the fabric: points that land on the same spot of the
  old mesh receive the UV the old mesh assigned there

### Requirement: A mirrored pattern gets a mirrored UV

When a pattern is mirrored, its seeded UV SHALL be mirrored as well, so that the
object's mirrored scale does not flip the texture. The carried-over UV of an
already-meshed pattern SHALL be mirrored at the moment its mirror flag changes,
because turning mirror on or off does not rebuild the mesh.

#### Scenario: Seeding a mirrored copy

- **WHEN** a pattern is copied as a mirror and meshed for the first time
- **THEN** each vertex's `u` is the negative of the source's seed `u`, and the
  texture reads the same as on the source rather than flipped

#### Scenario: Turning mirror on for a meshed pattern

- **WHEN** the mirror flag of an already-meshed pattern is turned on
- **THEN** its current UV is mirrored at that moment

### Requirement: The UV is reset from the UV editor

The UV editor's sidebar SHALL carry a Qianyi panel that offers a reset control
for the active pattern mesh's UV. Using it SHALL re-seed that mesh's UV from the
positions the mesh holds now and the current `uv_scale`, discarding any
carried-over or user-made UV, and it SHALL be a single undo step. The control
SHALL be unavailable while the active object is not a pattern mesh.

#### Scenario: Reset after a user edit

- **WHEN** a user moves a pattern's UV and then uses the reset control
- **THEN** every vertex's UV is back to its pattern-space position times
  `uv_scale`

#### Scenario: Reset with a changed scale

- **WHEN** `uv_scale` is changed and the reset control is used
- **THEN** the new UV is seeded with the new scale, and no mesh rebuild or
  resample is triggered

#### Scenario: Not a pattern mesh

- **WHEN** the active object is a collider
- **THEN** the reset control is not available

#### Scenario: One undo step

- **WHEN** the reset control is used and then undone once
- **THEN** the UV returns to the values it had before the reset

### Requirement: The UV never changes geometry, sewings or the simulation

Writing, carrying or resetting a UV SHALL NOT change a pattern's vertices, its
triangles, its pins, its sewings, the mesh the pattern samples, or the payload
the engine receives; it SHALL NOT start, stop or advance a simulation.

#### Scenario: Reset changes only the UV

- **WHEN** the reset control is used on a pattern of a project with sewings
- **THEN** its vertices, triangles, pins and the sewing pairings are unchanged,
  and the payload the bridge would build is identical

#### Scenario: A mirrored seed does not touch the geometry

- **WHEN** a mirrored copy is meshed
- **THEN** its vertices and triangles are the source's, mirrored only by the
  object's scale, and only the UV differs
