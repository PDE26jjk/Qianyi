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

### Requirement: The 3D viewport has its own overlay panel

The 3D viewport's sidebar SHALL carry an Overlays panel whose settings live on
the scene's Qianyi settings: a vertex-colour mode (`off`, `stress`, `debug`), a
seam overlay with a line width, and a simulation HUD. Every overlay SHALL
default to off except the HUD, which draws nothing until a frame has been
timed. The overlays SHALL be drawn by the add-on itself, over the material
Blender renders; the add-on MUST NOT create or assign a material for them.

#### Scenario: Defaults

- **WHEN** a file is opened and nothing is enabled in the Overlays panel
- **THEN** the vertex-colour mode is `off`, no seam lines are drawn, and no
  material is created or assigned by the add-on

#### Scenario: Vertex colours on demand

- **WHEN** the vertex-colour mode is `stress` and a frame has been simulated
- **THEN** the simulated panels are drawn in the viewport with the strain ramp
  of the pattern editor's stress display

#### Scenario: Debug on demand

- **WHEN** the vertex-colour mode is `debug` and a frame has been simulated
- **THEN** the panels are drawn with the engine's per-vertex debug values

### Requirement: The colouring does not fight the surface Blender rendered

The vertex-colour pass SHALL draw the same surface the viewport has already
shaded. Because the two surfaces would otherwise sit at the same depth and
flicker, the overlay SHALL lift its vertices towards the camera by a small
fraction of the drawn garment's size, and that lift SHALL be applied in the
vertex shader from the viewport's camera position, so orbiting the view changes
the drawing without rebuilding anything and without touching the panels.

#### Scenario: Orbiting the view

- **WHEN** the view is orbited while the vertex-colour mode is on
- **THEN** the colouring stays on the cloth without flickering, and no batch is
  rebuilt and no panel is modified

#### Scenario: The colouring still respects the scene

- **WHEN** a panel is behind another panel from the current viewpoint
- **THEN** the nearer panel hides it, because the pass is depth tested

### Requirement: Overlays follow Blender's own overlay switch

Every overlay the add-on draws in the 3D viewport SHALL be hidden while
Blender's own overlays are hidden, and SHALL come back when they are shown
again. Hiding the overlays SHALL NOT change any setting.

#### Scenario: Overlays hidden

- **WHEN** the viewport's overlays are switched off while vertex colours and
  seams are enabled
- **THEN** neither is drawn, and enabling the overlays draws them again with the
  same settings

### Requirement: Seams are drawn between paired stitch vertices

With the seam overlay enabled, the 3D viewport SHALL draw a line between each
paired stitch vertex of every seam, in that seam's own colour and at the chosen
width, depth tested so that a seam behind the cloth is hidden by it. A seam
whose sides cannot be resolved SHALL be skipped rather than fail the drawing.

The preview SHALL be drawn from the scene's own data - the sewing objects and
the panels' current meshes - and MUST NOT require a simulation: it SHALL be
visible before anything has been simulated and while any shape key is active,
and it SHALL follow the shape the viewport is showing.

#### Scenario: No simulation yet

- **WHEN** the seam overlay is enabled on a freshly sewn project that has never
  been simulated
- **THEN** the seams are drawn between the paired stitch vertices of the panels
  as they are placed now

#### Scenario: A shape key that is not the simulated one

- **WHEN** the panels are showing a shape key other than the simulated one
- **THEN** the seams follow that shape

#### Scenario: A seam's own colour

- **WHEN** two seams have different colours
- **THEN** each is drawn in its own colour

#### Scenario: Seams on demand

- **WHEN** the seam overlay is enabled for a project with sewings
- **THEN** the viewport draws a line between each paired stitch vertex, and the
  lines follow the simulated positions

#### Scenario: Depth

- **WHEN** a seam is behind a panel from the current viewpoint
- **THEN** the panel hides it

### Requirement: The HUD reports the run and its real-time speed

The HUD SHALL report, while a simulation is running or after frames have been
timed, whether a run is active and the real-time speed as simulated time over
wall-clock time, averaged over the last frames, in the form
`RTS: <ratio> = <simulated ms>ms / <wall ms>ms`. It SHALL also name the solver
in effect and the number of frames simulated.

#### Scenario: While a live run is active

- **WHEN** a live simulation is running and the HUD is enabled
- **THEN** the viewport shows that a simulation is running, the RTS line with
  the averaged frame timings, the solver name and the frame count

#### Scenario: Nothing timed yet

- **WHEN** no frame has been timed
- **THEN** the HUD draws nothing

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
