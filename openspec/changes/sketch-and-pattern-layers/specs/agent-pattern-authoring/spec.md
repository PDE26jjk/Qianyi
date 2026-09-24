## MODIFIED Requirements

### Requirement: An edit reaches the whole instance chain

The members of an instance chain SHALL hold one Sketch between them, so an edit
written through any member SHALL be the Sketch's new state for every member, and
the result SHALL list them. The edit SHALL be one write to the Sketch, not one
write per member, and no member SHALL be able to hold geometry the others do not
have. A member that is to diverge SHALL be detached first, which gives it its own
copy of the Sketch.

#### Scenario: Editing a panel that has a mirror copy

- **WHEN** a panel with a mirror copy is edited
- **THEN** the copy receives the same local geometry, the result names both panels, and both report the one Sketch

#### Scenario: Members cannot drift

- **WHEN** the members of a chain are read after any number of edits
- **THEN** every member reports the same Sketch and the same element counts, and no refusal about a copy with a different shape is reachable

#### Scenario: A detached pattern stops following

- **WHEN** a pattern is detached from its chain and the Sketch is then edited
- **THEN** the detached pattern keeps the Sketch it was given and only the remaining members change

### Requirement: A panel can be placed, mirrored and copied

The surface SHALL set a panel's anchor (millimetres), rotation (radians), grain
direction and collision layer; mirror it in place; and copy it as an instance or
a mirror at a given anchor. A copy SHALL be part of the same instance chain as
its source, SHALL reference the source's Sketch rather than a duplicate of it,
and SHALL be reported by name. Placing, mirroring or copying a panel MUST NOT
change the Sketch.

#### Scenario: An instance copy is made

- **WHEN** a panel is copied as a mirror at an anchor
- **THEN** the copy exists with its own name, mesh and placement, reports the source's chain membership and the source's Sketch, and both panels report each other as chain members

#### Scenario: The copy's placement is its own

- **WHEN** a copy is rotated while its source is left alone
- **THEN** only the copy's placement changes and the Sketch is untouched
