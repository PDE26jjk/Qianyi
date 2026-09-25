## Purpose

Generate a garment component's patterns, edges and edge labels from a parameter
block alone, without Blender and without third-party dependencies, so that
components can be developed, tested and reused independently of the add-on.

## ADDED Requirements

### Requirement: Parameter-driven generation

The library SHALL produce a component's patterns from its parameter block alone,
without reading Blender data and without external state. The same parameter
block MUST always produce the same geometry and the same edge labels.

#### Scenario: Repeated generation is identical

- **WHEN** the same component is generated twice with the same parameter block
- **THEN** both results have identical vertices, identical curves and identical edge labels

#### Scenario: Library works without Blender

- **WHEN** a component is generated in a plain Python session that has numpy but no Blender
- **THEN** generation succeeds and returns patterns

### Requirement: Pattern and edge specification

A pattern SHALL be a closed counter-clockwise loop of edges over a vertex list.
Each edge SHALL carry a curve, an optional label and a sewability flag. A label
that is left empty MUST be replaced by a generated name derived from the edge's
position in the loop, and explicit labels MUST NOT collide with generated names
or with each other inside one pattern.

#### Scenario: Unnamed edges receive positional labels

- **WHEN** a pattern is generated with some edges left unlabelled
- **THEN** every unlabelled edge receives a positional name that follows the loop order of the pattern

#### Scenario: Duplicate labels are rejected

- **WHEN** a component assigns the same explicit label to two edges of one pattern
- **THEN** generation reports an error instead of producing an ambiguous pattern

#### Scenario: Decorative edges are marked not sewable

- **WHEN** a component marks an edge as not sewable
- **THEN** that edge is excluded as a sewing target everywhere the pattern is used

### Requirement: Curve primitives reduce to existing edge representations

Every curve primitive the library offers SHALL reduce to one of the three pattern
representations the editor already supports: a straight edge, a cubic Bezier
edge, or a sequence of straight edges forming a point list. The editor MUST NOT
need a new curve type for generated patterns.

#### Scenario: Straight and Bezier curves map exactly

- **WHEN** a pattern edge is a line, a quadratic curve or a cubic curve
- **THEN** it is emitted as a straight edge or as a cubic Bezier edge whose shape matches the source curve

#### Scenario: Arc is approximated within tolerance

- **WHEN** a pattern edge is a circular arc
- **THEN** it is emitted as a curve whose maximum deviation from the true arc stays far below the pattern's mesh granularity

#### Scenario: Point lists become multiple edges

- **WHEN** a pattern edge is given as a point list
- **THEN** it is emitted as consecutive straight edges that keep the same boundary shape

### Requirement: Deterministic decorative runs

The library SHALL provide a helper that turns a straight run into a decorative
point list from an explicit seed, and SHALL allow such runs to be marked not
sewable.

#### Scenario: Same seed, same ragged edge

- **WHEN** the same run is generated twice with the same seed and amplitude
- **THEN** both runs contain the same points

### Requirement: Stable local frame across parameter changes

When parameters change, the library SHALL keep a pattern's local frame stable: the
generated geometry MUST NOT be translated, rotated or flipped as a side effect
of a shape change, so that the newly sampled mesh stays close to the previous
one.

#### Scenario: Shape change keeps the anchoring region in place

- **WHEN** a component's length or width parameter changes
- **THEN** the pattern region that carries the component's meaning (for example its waist edge or its origin) stays within a small distance of its previous position

### Requirement: Library dependency budget

The library SHALL depend only on numpy, and MUST NOT import Blender modules.

#### Scenario: Import with numpy only

- **WHEN** the library is imported in an environment that provides only Python and numpy
- **THEN** the import succeeds
