## Purpose

Shows the body behind a panel in the pattern window, so a pattern maker can
align a panel to the avatar by eye - outline, surface and seams - at the same
1:1 scale the pattern is drafted in.

## ADDED Requirements

### Requirement: A project names the objects to project

The project SHALL name a collection of objects to project into the pattern
window and SHALL carry a display switch for the guide, which defaults to off.
Objects in that collection that are meshes SHALL be projected; other object
types SHALL be ignored. With no collection named, nothing SHALL be drawn and
the controls SHALL say so.

#### Scenario: Enabling the guide

- **WHEN** a project names a collection holding one mesh and the guide is
  switched on
- **THEN** the pattern window draws that mesh's projected silhouette behind the
  panels

#### Scenario: No collection named

- **WHEN** the guide is switched on and no collection is named
- **THEN** nothing is drawn and the controls report that a collection has to be
  picked

#### Scenario: Non-mesh objects

- **WHEN** the named collection holds an empty, a light and a mesh
- **THEN** only the mesh contributes to the silhouette

### Requirement: The projection is 1:1 with the pattern space

The silhouette SHALL be projected along a world axis the project selects, into
the pattern window's own space in millimetres, offset by the project's own
offset in millimetres, so that one metre in the scene corresponds to 1000
millimetres of pattern space and a panel can be aligned against the body by eye.
The projection axis and the offset SHALL both be display settings that are
stored with the project.

#### Scenario: A one metre edge measures one thousand

- **WHEN** a one metre edge of the selected collection is projected with no
  offset
- **THEN** the projected edge measures 1000 millimetres in the pattern window

#### Scenario: Changing the offset

- **WHEN** the offset is changed by (100, 200) millimetres
- **THEN** the silhouette moves by exactly that much and no panel data changes

#### Scenario: Changing the projection axis

- **WHEN** the projection axis is changed from front to side
- **THEN** the silhouette is redrawn for the new axis and no panel data changes

### Requirement: The silhouette can be drawn filled and as a mesh

The guide SHALL draw the projected triangles filled, with a colour and an
opacity the project selects, and SHALL be able to draw the projected mesh edges
over the fill with their own opacity. Both settings SHALL be display settings
stored with the project.

#### Scenario: Fill and mesh

- **WHEN** the mesh overlay is enabled and its opacity is above zero
- **THEN** the projected fill and the projected mesh edges are both drawn, the
  edges over the fill

#### Scenario: Fill only

- **WHEN** the mesh overlay is disabled
- **THEN** only the filled silhouette is drawn

### Requirement: The silhouette follows the avatar and is display-only

The silhouette SHALL follow the selected objects' transforms and shapes as they
change, SHALL never contribute to a panel's vertices, mesh or the engine
payload, and SHALL NOT require any panel to be regenerated when it changes.

#### Scenario: Moving the avatar

- **WHEN** a selected object is moved or rotated while the guide is on
- **THEN** the silhouette follows in the next redraw and the panels' vertices,
  meshes and sewings are unchanged

#### Scenario: A deforming avatar

- **WHEN** a selected object's mesh deforms while a simulation is running
- **THEN** the silhouette follows the deformation without any panel being
  resampled or re-meshed

### Requirement: The projection is cached

The projection SHALL be rebuilt only when the selected objects, their
transforms, the display settings or the simulation's frame change, and a
deforming selection SHALL be followed at a bounded rebuild rate rather than on
every redraw, so a dense body does not dominate the window's cost.

#### Scenario: A redraw that changed nothing

- **WHEN** the window is redrawn with the same selection, settings and frame
- **THEN** the projection and its batches are reused and no vertices are read
  again

#### Scenario: A dense body

- **WHEN** a body of tens of thousands of vertices is selected and deforms
  every frame
- **THEN** the projection is rebuilt at the bounded rate, and the window stays
  interactive rather than rebuilding once per redraw
