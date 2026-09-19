## Purpose

Lets a panel be selected once and seen everywhere: a selection made on the body
appears in the pattern editor and the other way round, and a selected panel is
outlined clearly in the pattern window whatever display mode is active.

## ADDED Requirements

### Requirement: One toggle controls the sync and it is off by default

The pattern editor's header SHALL carry a Sync Selection toggle, stored on the
scene's Qianyi settings with a default of off. Turning it on SHALL adopt the
selection that is current at that moment instead of changing either side, and it
SHALL stop syncing as soon as it is turned off.

#### Scenario: Default

- **WHEN** the add-on is used without touching the toggle
- **THEN** selecting a panel in either editor leaves the other selection as it was

#### Scenario: Turning it on does not move the selection

- **WHEN** the toggle is turned on while a panel is selected in the pattern
  editor and a different panel's mesh is selected in 3D
- **THEN** both selections are unchanged until one of them changes again

#### Scenario: Turning it off

- **WHEN** the toggle is turned off and a selection is then made in either editor
- **THEN** the other selection is not touched

### Requirement: Selecting a mesh selects the panel

With the sync on, selecting panel meshes in the 3D viewport SHALL select exactly
the corresponding panels in the pattern editor, and SHALL deselect the panels
whose meshes are not selected. Clearing the 3D selection SHALL clear the pattern
editor's selection.

#### Scenario: One panel

- **WHEN** a panel's mesh is selected in the 3D viewport
- **THEN** that panel is selected in the pattern editor, and a panel whose mesh
  is not selected is not

#### Scenario: An instance copy

- **WHEN** a panel that has an instance copy is selected in the 3D viewport
- **THEN** that panel is selected in the pattern editor and its copy is not:
  syncing mirrors the selection that was made and does not expand it to the
  panel's instance chain

#### Scenario: Clearing

- **WHEN** the 3D selection is cleared
- **THEN** no panel is selected in the pattern editor

### Requirement: Selecting a panel selects its mesh

With the sync on, selecting panels in the pattern editor SHALL select the meshes
of exactly those panels, and SHALL deselect the pattern meshes that are not
selected. Clearing the pattern editor's selection SHALL clear those meshes in
3D.

#### Scenario: From the pattern editor

- **WHEN** a panel is selected in the pattern editor
- **THEN** its mesh is selected in the 3D viewport and the mesh of an unselected
  panel is not

#### Scenario: Several panels

- **WHEN** several panels are selected in the pattern editor
- **THEN** the meshes of all of them are selected

### Requirement: Only panel meshes take part

The sync SHALL consider only meshes that belong to a panel. Colliders, the body
and every other object SHALL keep whatever selection they had, and a panel that
has no mesh yet SHALL contribute nothing in 3D.

#### Scenario: A collider is selected

- **WHEN** a collider object is selected in the 3D viewport while the sync is on
- **THEN** no panel's selection changes and the collider stays selected

#### Scenario: Mixing a collider and a panel

- **WHEN** a collider and a panel's mesh are selected together
- **THEN** that panel is selected in the pattern editor and the collider is left
  alone

### Requirement: The mirror does not loop and does not touch geometry

Applying one side's selection to the other SHALL NOT be applied back, SHALL NOT
change any panel's geometry, mesh, sewing or the engine payload, and SHALL NOT
push an undo step. A scene whose panels change while the sync is on SHALL keep
working: a mesh whose panel no longer exists SHALL be ignored rather than fail.

#### Scenario: The mirror settles

- **WHEN** the sync applies a selection from 3D to the pattern editor
- **THEN** the next poll applies nothing, and the selection stays as applied

#### Scenario: An edit is not disturbed

- **WHEN** a panel's vertex is moved while the sync is on
- **THEN** the geometry is unchanged by the sync and no undo step is added by it

#### Scenario: A stale mesh

- **WHEN** a selected mesh's panel has been removed
- **THEN** the sync ignores that mesh and still mirrors every other selection

### Requirement: A selected panel is outlined in the pattern window

A selected panel SHALL be drawn in the pattern window with an additional,
thicker outline in a dedicated highlight colour, over its ordinary outline and
in every display mode, so the selection is readable without switching to the
`mesh` mode. The highlight SHALL be a drawing effect only: it SHALL NOT change a
panel's geometry, selection flag or mesh.

#### Scenario: Solid mode

- **WHEN** the display mode is `solid` and a panel is selected
- **THEN** its outline is drawn in the highlight colour and is thicker than the
  outline of an unselected panel

#### Scenario: Wireframe mode

- **WHEN** the display mode is `wireframe` and a panel is selected
- **THEN** the highlight is visible on the same panel

#### Scenario: Deselecting

- **WHEN** a panel is deselected
- **THEN** its highlight is gone on the next redraw
