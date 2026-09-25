## Purpose

Keep generated geometry trustworthy by refusing the hand edits that regeneration
would overwrite, while leaving every operation that does not conflict with
regeneration available to the user.

## ADDED Requirements

### Requirement: Geometry editing is refused on generated patterns

The system SHALL refuse geometry editing on a pattern owned by a generator:
adding, moving or deleting vertices and spline points, moving edges, creating
internal lines, and scaling. The refusal MUST be visible to the user instead of
silently doing nothing. The whole instance chain counts: when any pattern in the
chain of the pattern being edited is generated, the edit MUST be refused, because
the editing tools keep copies in sync and the edit would otherwise reach the
generated pattern.

#### Scenario: Vertex edit is refused

- **WHEN** the user tries to add a vertex to a pattern owned by a generator
- **THEN** the operation is refused with a message and the pattern geometry is unchanged

#### Scenario: Editing a copy that belongs to a generated pattern is refused

- **WHEN** the user tries a geometry edit on a copy whose instance chain contains a generated pattern
- **THEN** the operation is refused with a message, so the generated pattern cannot be changed through the copy

### Requirement: Operations that do not conflict stay available

On a pattern owned by a generator the system SHALL keep available: creating
sewings (including to hand-drawn patterns), running the simulation, editing fabric
properties, collision layer, grain direction and 2D placement, creating mirror
and instance copies, and deleting the pattern.

#### Scenario: Sewing a generated pattern is allowed

- **WHEN** the user creates a sewing between a generated pattern and a hand-drawn pattern
- **THEN** the sewing is created normally

#### Scenario: Mirroring a generated pattern is allowed

- **WHEN** the user creates a mirrored copy of a generated pattern
- **THEN** the copy is created as an instance of the generated pattern

### Requirement: Detached patterns accept every edit

After a group has been detached, its patterns SHALL accept all editing operations.

#### Scenario: Detached pattern can be edited by hand

- **WHEN** the user edits the vertices of a pattern whose group was detached
- **THEN** the edit is applied
