## MODIFIED Requirements

### Requirement: The data model is documented

The documentation SHALL describe the add-on's objects and their structure, and
how each one is reached from a session: the project that owns patterns, sewings
and fabrics; a pattern with its vertices, edges, spline points, internal lines,
fabric, granularity, collision layer, simulation state and mesh object; a sewing
as two sides, each one an edge plus a normalized position on that edge; a
fabric; and the mesh objects that take part in a simulation. For every object it
MUST name the supported way to read it and the supported way to change it.

The documentation SHALL also state that reading and writing Blender data
directly is permitted but discouraged, and MUST name what has to be re-resolved
after such a write and which failures follow from skipping it.

#### Scenario: An agent needs something the surface does not offer

- **WHEN** a client finds no entry point for a change it has to make
- **THEN** the documentation tells it which data to reach for, what to re-resolve after the write, and what can break

#### Scenario: The data model is reachable without the repository

- **WHEN** a client reads the data-model topic from the text index
- **THEN** it gets the same description as the shipped reference file

#### Scenario: A discouraged path is not a silent path

- **WHEN** a client changes patterns or sewings through Blender data instead of the surface
- **THEN** the documentation has already told it that the add-on's identity map and derived data must be refreshed, and which failure the missing refresh causes

#### Scenario: The pattern state is part of the documented model

- **WHEN** a client reads the data-model topic to find out what a pattern can be
- **THEN** the description names the simulation state and the stiffness multiplier as pattern attributes, says what each state value means for the solve and the collision, and names the calls that read and write them
