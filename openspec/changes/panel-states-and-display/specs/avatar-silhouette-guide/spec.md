## Purpose

Shows the body behind a panel in the pattern window, so a pattern maker can
align a panel to the avatar by eye the way the 3D window shows it.

## ADDED Requirements

### Requirement: The pattern window can show a collider silhouette

The pattern window SHALL be able to draw the silhouette of the scene's collider
meshes as a translucent filled shape behind the panel outlines, projected into
each panel's own 2D space along a per-panel axis. The control SHALL be
available globally and per panel, and SHALL default to off.

#### Scenario: Silhouette appears behind the panel

- **WHEN** the silhouette guide is enabled for a panel and the scene contains a
  collider mesh
- **THEN** the pattern window draws the collider's projected outline behind
  that panel's outline, in the panel's own millimetre space

#### Scenario: No collider in the scene

- **WHEN** the guide is enabled and the scene contains no collider mesh
- **THEN** nothing is drawn and the control reports that there is no collider

### Requirement: The silhouette follows the avatar

The silhouette SHALL follow the collider's transform and shape as they change,
without regenerating any panel mesh, and it SHALL be display-only: it never
enters the panel mesh, the mesh payload handed to the engine, or the saved
panel data.

#### Scenario: Moving the avatar

- **WHEN** the collider object is moved or rotated while the guide is enabled
- **THEN** the silhouette moves with it in the next redraw, and the panels'
  vertices, meshes and sewings are unchanged

#### Scenario: Alignment is measurable

- **WHEN** a panel and the collider are drawn together
- **THEN** a distance measured in the pattern window between a panel point and
  the silhouette corresponds to the same distance in the 3D scene at the
  panel's scale

### Requirement: Projection axis is under the user's control

The axis used to project the collider into a panel's plane SHALL be selectable
per panel among the scene's axes and the panel's own normal, with a documented
default, and changing it SHALL be a display change only.

#### Scenario: Changing the projection axis

- **WHEN** the projection axis is changed from the default to the panel's
  normal
- **THEN** the silhouette is redrawn for the new axis and no panel data changes
