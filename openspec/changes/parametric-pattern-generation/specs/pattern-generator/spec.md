## Purpose

Let a project hold parameterized pattern sources that produce ordinary patterns,
keep them up to date automatically when their parameters change, and manage
them as one group.

## ADDED Requirements

### Requirement: Generator produces patterns from parameters

Creating a generator from a component and a parameter block SHALL create that
component's patterns in the project, named after the slots the component defines.

#### Scenario: Creating a generator creates its patterns

- **WHEN** the user adds a generator for a component
- **THEN** the project contains one pattern per slot the component produced, named after that slot

### Requirement: Parameter changes rebuild automatically

The system SHALL rebuild a generator's patterns as soon as one of its parameters
changes. No separate apply step SHALL be required.

#### Scenario: Editing a parameter updates the patterns

- **WHEN** the user changes a parameter value of an existing generator
- **THEN** the generator's patterns are rebuilt without any further user action

### Requirement: Stable slot names

Every pattern a generator produces SHALL keep its slot name across regeneration,
and regeneration SHALL reuse the existing pattern for that slot instead of
creating a new one.

#### Scenario: A component with more slots adds only new patterns

- **WHEN** a multi-pattern component regenerates with a higher pattern count
- **THEN** the existing patterns keep their identity and placement, and only the additional slots appear as new patterns

### Requirement: Regeneration preserves edge identity when it can

When a rebuild leaves a pattern's edge list unchanged, both in count and in order,
the system SHALL update the existing edges in place so that edge identity is
preserved and dependents keep referring to them.

#### Scenario: Shape-only change keeps edge identity

- **WHEN** only shape parameters change and the pattern's edge list is unchanged
- **THEN** the pattern keeps the same edges, with updated coordinates

### Requirement: Group lifecycle

Deleting any pattern that belongs to a generator SHALL delete the whole group: the
sibling patterns and the generator itself. Detaching SHALL convert the whole group
into ordinary patterns and remove the generator.

#### Scenario: Deleting one pattern deletes the group

- **WHEN** the user deletes one pattern produced by a generator
- **THEN** every pattern of that generator and the generator itself are removed

#### Scenario: Detach keeps the patterns

- **WHEN** the user detaches a generator
- **THEN** all of its patterns remain in the project as ordinary patterns, without an owning generator

### Requirement: Generated patterns are ordinary patterns elsewhere

A generated pattern SHALL take part in sewing, mesh generation, simulation,
fabric properties, collision layers, grain direction and 2D placement in the
same way a hand-drawn pattern does.

#### Scenario: Generated pattern is sewn to a hand-drawn pattern

- **WHEN** a generated pattern and a hand-drawn pattern are sewn together and simulated
- **THEN** both are stitched and simulated like any other pair of patterns

### Requirement: Invalid generator state is reported, not fatal

An unknown component or a parameter block the component cannot build MUST leave
every pattern of that generator untouched and report an error instead of
rebuilding anything. A pattern whose outline crosses itself is a different case:
like any edit, it SHALL be written, and the mesh stage SHALL decide - the
existing mesh is kept and the pattern is reported as invalid, exactly as the
interactive tools behave. Values outside a parameter's declared range SHALL be
pulled back to the nearest bound before building, and the stored value SHALL be
updated to match.

#### Scenario: A component that cannot build leaves the patterns untouched

- **WHEN** a parameter change cannot produce patterns at all
- **THEN** no pattern of that generator is modified and the user sees an error message

#### Scenario: A crossing outline is written but not meshed

- **WHEN** a parameter change produces a pattern whose outline crosses itself
- **THEN** the geometry is written, the previous mesh is kept, and the pattern is reported as invalid

#### Scenario: Out-of-range value is clamped

- **WHEN** a parameter is set outside the range its schema declares
- **THEN** the value is pulled back to the nearest bound and the stored value is updated to match

### Requirement: Instance copies stay in sync

Mirror and instance copies of a generated pattern SHALL be rebuilt and
re-anchored together with the pattern they were copied from.

#### Scenario: Mirrored copy follows the source

- **WHEN** a generated pattern is mirrored into an instance and a parameter of its generator changes
- **THEN** the mirrored copy is rebuilt as well and keeps its mirrored placement
