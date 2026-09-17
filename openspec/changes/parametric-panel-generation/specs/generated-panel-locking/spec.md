## Purpose

Keep generated geometry trustworthy by refusing the hand edits that regeneration
would overwrite, while leaving every operation that does not conflict with
regeneration available to the user.

## ADDED Requirements

### Requirement: Geometry editing is refused on generated panels

The system SHALL refuse geometry editing on a panel owned by a generator:
adding, moving or deleting vertices and spline points, moving edges, creating
internal lines, and scaling. The refusal MUST be visible to the user instead of
silently doing nothing. The whole instance chain counts: when any panel in the
chain of the panel being edited is generated, the edit MUST be refused, because
the editing tools keep copies in sync and the edit would otherwise reach the
generated panel.

#### Scenario: Vertex edit is refused

- **WHEN** the user tries to add a vertex to a panel owned by a generator
- **THEN** the operation is refused with a message and the panel geometry is unchanged

#### Scenario: Editing a copy that belongs to a generated panel is refused

- **WHEN** the user tries a geometry edit on a copy whose instance chain contains a generated panel
- **THEN** the operation is refused with a message, so the generated panel cannot be changed through the copy

### Requirement: Operations that do not conflict stay available

On a panel owned by a generator the system SHALL keep available: creating
sewings (including to hand-drawn panels), running the simulation, editing fabric
properties, collision layer, grain direction and 2D placement, creating mirror
and instance copies, and deleting the panel.

#### Scenario: Sewing a generated panel is allowed

- **WHEN** the user creates a sewing between a generated panel and a hand-drawn panel
- **THEN** the sewing is created normally

#### Scenario: Mirroring a generated panel is allowed

- **WHEN** the user creates a mirrored copy of a generated panel
- **THEN** the copy is created as an instance of the generated panel

### Requirement: Detached panels accept every edit

After a group has been detached, its panels SHALL accept all editing operations.

#### Scenario: Detached panel can be edited by hand

- **WHEN** the user edits the vertices of a panel whose group was detached
- **THEN** the edit is applied
