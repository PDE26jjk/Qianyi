## Purpose

Gives the pattern window and the 3D viewport the display modes a garment tool is
read by - solid, wireframe, mesh, stress, debug, seams - so a designer can see
the panel, the mesh and the simulation's own numbers in the same place.

## ADDED Requirements

### Requirement: The pattern window has selectable display modes

The pattern window SHALL offer the display modes `solid`, `wireframe`, `mesh`,
`stress` and `debug`, with the active mode stored in the scene and restored
when the file is reopened. Exactly one mode is active at a time.

#### Scenario: Switching modes

- **WHEN** the active mode is changed from `solid` to `mesh`
- **THEN** the panels are redrawn with their sampled mesh edges visible, and
  no panel's outline, mesh, sewing or simulation state is modified

#### Scenario: Mode survives a reload

- **WHEN** a file with `wireframe` active is saved and reopened
- **THEN** the pattern window draws in `wireframe`

### Requirement: Each mode draws a defined picture

`wireframe` SHALL draw the outline and internal lines only. `mesh` SHALL draw
the sampled panel mesh over the outline. `solid` SHALL fill the panel with the
fabric's display color, which SHALL be a per-fabric property with a neutral
default. `debug` SHALL color the panel mesh from the engine's per-vertex debug
colors. `stress` SHALL color it by a per-vertex strain the editor derives from
the panel's rest and simulated vertex sets, on a documented ramp with stated
saturation values, because the engine does not report a per-vertex stress
today.

#### Scenario: Solid uses the fabric color

- **WHEN** two panels use fabrics with different display colors and the mode is
  `solid`
- **THEN** each panel is filled with its own fabric's color

#### Scenario: Stress without simulation data

- **WHEN** the mode is `stress` and no simulation data has been produced yet
- **THEN** the panels are drawn as in `solid` and the panel says that no
  simulation data is available

#### Scenario: Strain is what is drawn

- **WHEN** a panel that has been stepped is shown in `stress`
- **THEN** a vertex whose edges are stretched relative to the flat pattern is
  drawn towards the hot end of the ramp, and a vertex whose edges are unchanged
  is drawn at the ramp's rest colour

### Requirement: Display modes never change the simulation

Changing the display mode SHALL NOT resample a panel, rebuild a mesh, change a
sewing or touch the engine. Switching between modes SHALL be a redraw, not a
recomputation.

#### Scenario: Mode switch is a redraw

- **WHEN** the mode is switched several times on a project with generated
  panels and sewings
- **THEN** the panel meshes, the sewing pairings and the last simulated frame
  are unchanged

### Requirement: The 3D viewport has matching overlays

The 3D viewport SHALL offer, behind one display panel, seams drawn as lines
between paired stitch vertices, the stress/debug vertex colors on the simulated
mesh, and the existing force/collision debug primitives. Every overlay SHALL
default to off, and the debug primitives SHALL no longer draw unconditionally.

#### Scenario: Overlays default to off

- **WHEN** a file is opened and nothing is enabled in the display panel
- **THEN** the 3D viewport draws no seam lines and no debug primitives

#### Scenario: Seams on demand

- **WHEN** the seam overlay is enabled for a project with sewings
- **THEN** the 3D viewport draws a line between each paired stitch vertex, and
  the lines follow the simulated positions

### Requirement: Stress and debug colors reach the viewport

The mesh SHALL receive the engine's per-vertex debug colors through the color
attribute the bridge already writes, and the add-on SHALL provide the material
that displays that attribute, so the 3D viewport shows the stress coloring
without the user building a shader.

#### Scenario: Colors shown after a step

- **WHEN** a simulation is stepped with the vertex-color display enabled
- **THEN** the simulated mesh is drawn with the colors the engine reported for
  that frame

### Requirement: The grain line is drawn vertically by default

The pattern window SHALL draw the fabric grain line rotated so that a panel
whose grain direction is at its default value shows the line running vertically
in the pattern's own space, which is the convention every other garment tool
uses for the default warp direction. Rotating a panel's grain direction SHALL
rotate the drawn line by the same angle. The drawn line's orientation SHALL be
a display convention only: the stored grain direction the engine receives MUST
NOT change when it is introduced.

#### Scenario: Default grain direction

- **WHEN** a panel with the default grain direction shows its grain line
- **THEN** the drawn line runs vertically through the panel in the pattern
  window

#### Scenario: Rotating the grain direction

- **WHEN** a panel's grain direction is rotated by 90 degrees from the default
- **THEN** the drawn line follows and becomes horizontal, and the value the
  engine receives is the rotated one the panel reports
