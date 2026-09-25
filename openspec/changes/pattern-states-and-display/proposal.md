## Why

The add-on can simulate a garment, but it cannot yet express what a garment
designer says about a pattern *beyond its outline*: that a pattern is only a
reference, that it must hold its current shape, that it is stiff like leather
or buckram, or where the body sits behind it. Every competing tool carries
those statements as pattern state and as viewport display, and a pattern maker
who cannot find them reads the add-on as a simulator, not as a design tool.

## What Changes

- Add a per-pattern simulation state: **simulate**, **excluded** (not solved and
  not a collider), **frozen** (held where it is, still a collider) and
  **stiffened** (solved with a stiffness multiplier on a per-pattern fabric
  override). The state is a property of the pattern, so it survives copies,
  instance chains and generators, and it is visible in the 3D sidebar as well
  as the pattern list.
- Add pattern-window display modes: solid, wireframe, mesh, stress and debug,
  replacing the current fixed "fill plus mesh lines" drawing. Stress and debug
  consume the engine's per-vertex debug colors that the bridge already
  downloads, and ship with a material that shows them.
- Add 3D viewport overlays for the same data: seam lines, stress/debug vertex
  colors and the existing force/collision debug primitives behind one display
  pattern instead of the current always-on debug registration.
- Add an avatar silhouette guide: project the collider meshes into the pattern
  window along a per-pattern axis so a pattern can be aligned against the body by
  eye, with the silhouette following the collider as it moves.
- Expose the new state and display settings through `qyapi` so a script can
  read and write them, and record them in the scene capture.

## Capabilities

### New Capabilities

- `pattern-simulation-states`: the per-pattern simulate / excluded / frozen /
  stiffened state, its data model, its mapping to the engine mesh payload, its
  UI in the pattern list and the 3D sidebar, and its interaction with copies,
  instance chains, generators and simulation start/stop.
- `pattern-display-modes`: display modes for the pattern window (solid,
  wireframe, mesh, stress, debug), the matching 3D viewport overlays (stress,
  debug, seam lines), the color scale contract for stress/debug, and the
  material that renders the engine's per-vertex colors.
- `avatar-silhouette-guide`: projecting collider meshes into a pattern's 2D space
  and drawing the resulting silhouette in the pattern window as an alignment
  reference.

### Modified Capabilities

- `agent-scripting-surface`: the documented data model gains the pattern's
  simulation state and stiffness multiplier, so the documented description of a
  pattern and of what takes part in a simulation changes.

## Impact

- Model: `Qianyi/model/pattern.py` (new state and display properties),
  `Qianyi/model/fabric.py` (per-pattern override used by the stiffened state),
  `Qianyi/model/qianyi_project.py` (state propagation to copies and generators).
- Bridge: `Qianyi/simulation/simulation_data.py` /
  `Qianyi/simulation/simulation_manager.py` - excluded patterns leave the mesh
  list, frozen patterns arrive as fully pinned vertices, and only stiffened
  patterns carry an overridden fabric block.
- Drawing: `Qianyi/gizmos/temp_draw_manager.py` (the display-mode branch that
  the code currently marks as a TODO), `Qianyi/gizmos/pattern_renderer.py`,
  `Qianyi/gizmos/GizmosMeshRenderer.py`, and the 3D overlay in
  `Qianyi/debug_draw_3d.py`.
- UI: `Qianyi/ui/panels/patterns.py`, `Qianyi/ui/panels_3d/simulation_object.py`,
  a new display pattern, and `Qianyi/declarations.py`.
- Script surface: `Qianyi/qyapi/patterns.py` (state and display getters and
  setters) and `docs/agent-api.md`.
- Engine: no engine change is required. The pin weights, the collider object
  type and the per-object fabric block already exist; the stiffened state is a
  per-pattern fabric override, and the plasticity-based freeze is a separate
  change in the engine repository.
