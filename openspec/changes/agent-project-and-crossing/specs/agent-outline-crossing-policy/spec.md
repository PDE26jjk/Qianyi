## Purpose

Let a caller building a shape pass through outlines that cross themselves, one
call at a time, while keeping a crossing outline away from the mesh sampler and
from a simulation.

## ADDED Requirements

### Requirement: Crossing is allowed per call, not by a setting

The geometry writes SHALL take an `allow_crossing` argument that defaults to off.
With it off, behaviour is unchanged: a write that would leave a crossing outline
is refused, and an edit whose crossing only appears after sampling is put back.
With it on, the write is applied even when the outline crosses. There SHALL be no
session-wide, scene-wide or otherwise global switch for this.

#### Scenario: The default still refuses

- **WHEN** a geometry write would leave a crossing outline and the flag is not given
- **THEN** it is refused and the scene is unchanged

#### Scenario: The caller opts in for one call

- **WHEN** the same write is made with the flag on
- **THEN** it is applied and the crossing outline is stored

#### Scenario: One call does not decide for the next

- **WHEN** a write with the flag on is followed by a write without it
- **THEN** the second write refuses a crossing outline again

### Requirement: The scene's own switch is not used

The surface MUST NOT read or write the scene's Check Self-Intersection switch,
which stays a switch for the interactive operators.

#### Scenario: The interactive switch is untouched

- **WHEN** the surface writes geometry with or without the flag
- **THEN** the scene's switch is left exactly as it was

### Requirement: An answer says when it left a crossing outline

An answer that produced a crossing outline SHALL report it: the panel, its
validity, and the crossing point when one is known. When the mesh stage therefore
did not rebuild the panel's mesh, the answer SHALL say the mesh is stale and
name the mesh it still has.

#### Scenario: The crossing is reported

- **WHEN** a write with the flag on leaves a crossing outline
- **THEN** the answer carries the validity as invalid, the crossing point, and that the mesh is stale

#### Scenario: Reading a panel that already crosses

- **WHEN** a panel whose outline crosses is read
- **THEN** its validity is reported as invalid and its mesh is reported as stale

### Requirement: The mesh and the simulation still refuse a crossing outline

A crossing outline MUST NOT be handed to the mesh sampler: the panel keeps the
mesh it had, and the answer says so. A simulation MUST NOT start while any
participating panel's outline crosses.

#### Scenario: No mesh for a crossing outline

- **WHEN** a crossing outline is stored with the flag on
- **THEN** the panel's mesh is the one it had, and the answer reports that it was not rebuilt

#### Scenario: A simulation is refused

- **WHEN** a simulation is prepared while a participating panel crosses
- **THEN** it is refused with the offending panels named

### Requirement: A generator rebuild is not gated by the flag

Changing a generator's parameters SHALL keep its own policy, which is already the
one this policy describes: the geometry is written, the mesh stage keeps the
previous mesh when the outline crosses or is degenerate, and the answer counts
those panels. A rebuild MUST NOT gain a refusal for crossing, and MUST NOT take
the per-call flag - a parameter change is not a step-by-step edit, so there is
nothing for a caller to opt into per call.

#### Scenario: A parameter change that crosses

- **WHEN** a parameter change leaves a panel's outline crossing
- **THEN** the rebuild is applied, that panel keeps its previous mesh, and the report counts it

#### Scenario: The report names the panels

- **WHEN** a rebuild leaves panels crossing or degenerate
- **THEN** the report names them and says their meshes were not rebuilt

### Requirement: The crossing can be fixed and the mesh rebuilt

A later edit that makes the outline valid again SHALL let the mesh rebuild, and
the answers SHALL stop reporting the panel as crossing or its mesh as stale.

#### Scenario: Fixing the outline

- **WHEN** the points are moved so the outline no longer crosses and a write without the flag succeeds
- **THEN** the mesh is rebuilt and the next read reports the panel as valid

#### Scenario: The read-only check still reports

- **WHEN** the outline check is called as a read
- **THEN** it reports the crossing panels and their crossing points without raising, whatever was allowed before
