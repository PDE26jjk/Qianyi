## Purpose

Keep user-made seams pointing at the right edges when a generator rebuilds its
panels, and remove only those seams that no longer have a counterpart.

## ADDED Requirements

### Requirement: Sewing storage stays as it is

Sewings SHALL keep being stored as an edge identity plus a normalized position
on that edge. Generated panels MUST NOT require a different sewing
representation, so that generated and hand-drawn panels remain interchangeable.

#### Scenario: Existing sewing data is unchanged

- **WHEN** a sewing is created between a generated panel and a hand-drawn panel
- **THEN** it is stored in the same form as a sewing between two hand-drawn panels

### Requirement: Unchanged panels keep their sewings untouched

When a rebuild preserves a panel's edge list, every sewing on that panel SHALL
keep its edge identities and positions.

#### Scenario: Shape-only parameter change

- **WHEN** a parameter changes and the panel's edges are updated in place
- **THEN** all sewings on that panel keep the same edges and positions

### Requirement: Edges are matched when the topology changes

When a rebuild changes a panel's edge list, the system SHALL match each previous
edge to a new edge of the same panel, using the edge label first and geometry
second.

#### Scenario: Labelled edge is matched by label

- **WHEN** a rebuild changes the edge order but the same edge label is still present
- **THEN** the previous edge is matched to the new edge carrying that label

#### Scenario: Unlabelled edge is matched by geometry

- **WHEN** a previous edge has no label or its label no longer exists
- **THEN** the system matches it to the new edge nearest to its previous position on the panel boundary

### Requirement: Sewings are re-anchored, unmatched sewings are removed

Matched sewings SHALL be re-anchored to the matched edges with their positions
preserved. Sewings whose edges have no match SHALL be removed. The system MUST
NOT introduce a suspended or invalid sewing state.

#### Scenario: Re-anchoring after a topology change

- **WHEN** a rebuild splits an edge that carries a sewing
- **THEN** the sewing points at the new edge that replaced it, or is removed when no replacement exists

### Requirement: Remapping is scoped to the rebuilt generator

Matching and re-anchoring SHALL consider only the sewings that touch the panels
of the generator being rebuilt.

#### Scenario: Unrelated sewings are not touched

- **WHEN** a generator rebuilds and a sewing elsewhere in the project exists
- **THEN** that unrelated sewing is left unchanged

### Requirement: Optional component hook overrides matching

The system SHALL call a hook after a component's panels have been rewritten,
whenever that component provides one. The hook SHALL be able to return nothing,
which means the default matching is used; a mapping from previous edges to new
edges, which the system MUST use instead of matching; or a handled marker, which
means the component already adjusted the sewings and the system MUST NOT touch
them.

#### Scenario: Hook provides an edge mapping

- **WHEN** a component's hook returns a mapping for an edge it split
- **THEN** the system reconnects the sewings according to that mapping instead of matching by itself

#### Scenario: Hook takes over

- **WHEN** a component's hook reports that it handled the sewings
- **THEN** the system leaves the sewings as the hook left them

### Requirement: Instance chains are covered

Matching and re-anchoring SHALL also cover the mirror and instance copies of the
rebuilt panels.

#### Scenario: Instance copy of a rebuilt panel

- **WHEN** a rebuilt panel has instance copies and those copies carry sewings
- **THEN** those sewings are matched and re-anchored as well
