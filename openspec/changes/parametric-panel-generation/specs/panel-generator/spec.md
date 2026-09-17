## Purpose

Let a project hold parameterized panel sources that produce ordinary panels,
keep them up to date automatically when their parameters change, and manage
them as one group.

## ADDED Requirements

### Requirement: Generator produces panels from parameters

Creating a generator from a component and a parameter block SHALL create that
component's panels in the project, named after the slots the component defines.

#### Scenario: Creating a generator creates its panels

- **WHEN** the user adds a generator for a component
- **THEN** the project contains one panel per slot the component produced, named after that slot

### Requirement: Parameter changes rebuild automatically

The system SHALL rebuild a generator's panels as soon as one of its parameters
changes. No separate apply step SHALL be required.

#### Scenario: Editing a parameter updates the panels

- **WHEN** the user changes a parameter value of an existing generator
- **THEN** the generator's panels are rebuilt without any further user action

### Requirement: Stable slot names

Every panel a generator produces SHALL keep its slot name across regeneration,
and regeneration SHALL reuse the existing panel for that slot instead of
creating a new one.

#### Scenario: A component with more slots adds only new panels

- **WHEN** a multi-panel component regenerates with a higher panel count
- **THEN** the existing panels keep their identity and placement, and only the additional slots appear as new panels

### Requirement: Regeneration preserves edge identity when it can

When a rebuild leaves a panel's edge list unchanged, both in count and in order,
the system SHALL update the existing edges in place so that edge identity is
preserved and dependents keep referring to them.

#### Scenario: Shape-only change keeps edge identity

- **WHEN** only shape parameters change and the panel's edge list is unchanged
- **THEN** the panel keeps the same edges, with updated coordinates

### Requirement: Group lifecycle

Deleting any panel that belongs to a generator SHALL delete the whole group: the
sibling panels and the generator itself. Detaching SHALL convert the whole group
into ordinary panels and remove the generator.

#### Scenario: Deleting one panel deletes the group

- **WHEN** the user deletes one panel produced by a generator
- **THEN** every panel of that generator and the generator itself are removed

#### Scenario: Detach keeps the panels

- **WHEN** the user detaches a generator
- **THEN** all of its panels remain in the project as ordinary panels, without an owning generator

### Requirement: Generated panels are ordinary panels elsewhere

A generated panel SHALL take part in sewing, mesh generation, simulation,
fabric properties, collision layers, grain direction and 2D placement in the
same way a hand-drawn panel does.

#### Scenario: Generated panel is sewn to a hand-drawn panel

- **WHEN** a generated panel and a hand-drawn panel are sewn together and simulated
- **THEN** both are stitched and simulated like any other pair of panels

### Requirement: Invalid generator state is reported, not fatal

An unknown component or a parameter block the component cannot build MUST leave
every panel of that generator untouched and report an error instead of
rebuilding anything. A panel whose outline crosses itself is a different case:
like any edit, it SHALL be written, and the mesh stage SHALL decide - the
existing mesh is kept and the panel is reported as invalid, exactly as the
interactive tools behave. Values outside a parameter's declared range SHALL be
pulled back to the nearest bound before building, and the stored value SHALL be
updated to match.

#### Scenario: A component that cannot build leaves the panels untouched

- **WHEN** a parameter change cannot produce panels at all
- **THEN** no panel of that generator is modified and the user sees an error message

#### Scenario: A crossing outline is written but not meshed

- **WHEN** a parameter change produces a panel whose outline crosses itself
- **THEN** the geometry is written, the previous mesh is kept, and the panel is reported as invalid

#### Scenario: Out-of-range value is clamped

- **WHEN** a parameter is set outside the range its schema declares
- **THEN** the value is pulled back to the nearest bound and the stored value is updated to match

### Requirement: Instance copies stay in sync

Mirror and instance copies of a generated panel SHALL be rebuilt and
re-anchored together with the panel they were copied from.

#### Scenario: Mirrored copy follows the source

- **WHEN** a generated panel is mirrored into an instance and a parameter of its generator changes
- **THEN** the mirrored copy is rebuilt as well and keeps its mirrored placement
