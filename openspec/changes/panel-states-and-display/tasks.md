## 1. Panel state data model

- [ ] 1.1 Add `simulation_state` (`simulate` / `excluded` / `frozen` /
  `stiffened`) and `stiffness_scale` to `Pattern` with the documented defaults,
  and verify a scene saved and reopened reports the values that were set
- [ ] 1.2 Make copies, instance chains and generator rebuilds carry the state
  and the multiplier, and verify a copied panel inherits its source's state and
  a generator rebuild does not reset it
- [ ] 1.3 Add the per-fabric display color with a neutral default, and verify
  two panels on different fabrics draw in their own color in `solid`
- [ ] 1.4 Add the state and multiplier to the scene capture, and verify
  `scene.json` records the state of every panel

## 2. Engine payload mapping

- [ ] 2.1 Skip `excluded` panels when the bridge builds the mesh list, and
  verify the payload handed to the engine contains only the participating
  panels
- [ ] 2.2 Implement `frozen` as full pin weights in `QYPinFix`, recording the
  pinned vertex set per panel, and verify unfreeze removes exactly that set and
  leaves hand-made pins intact
- [ ] 2.3 Implement `stiffened` as a per-panel scale on the payload's stretch
  and bending, and verify the payload carries the scaled values while the
  shared fabric asset keeps its own
- [ ] 2.4 Refuse a simulation start when no panel participates, and verify the
  report names the reason and the engine is not called
- [ ] 2.5 Stop a running simulation when a participating panel's state or
  multiplier changes, and verify the change survives and the report says it
  applies from the next start
- [ ] 2.6 Verify a frozen panel does not move and a simulated panel drapes
  against it over a stepped run, using the existing per-frame data check

## 3. Panel state UI

- [ ] 3.1 Show and edit the state and multiplier in the pattern list and its
  property panel, and verify both places agree after one edit
- [ ] 3.2 Show and edit the same values in the 3D sidebar of the selected
  panel, including for panels the sidebar currently treats as non-pattern
  meshes
- [ ] 3.3 Make each state change one undo step, and verify one undo restores
  the previous state

## 4. Pattern window display modes

- [x] 4.1 Add the scene-level display mode property (`solid`, `wireframe`,
  `mesh`, `stress`, `debug`) and verify it survives save and reload
- [x] 4.2 Implement the display branch the current code marks as a TODO, with
  `wireframe` drawing outline and internal lines only and `mesh` adding the
  sampled mesh edges
- [x] 4.3 Implement `solid` from the fabric display color and verify each panel
  uses its own fabric's color
- [x] 4.4 Implement `debug` from the engine's per-vertex colors and `stress`
  from the per-vertex strain derived from the rest and simulated vertex sets,
  and verify the fallback to `solid` plus an explanation when no frame has been
  produced
- [ ] 4.5 Verify that switching modes never resamples a panel, rebuilds a mesh
  or changes a sewing, by stepping the simulation and switching modes
  repeatedly on a generated project
- [x] 4.6 Draw the grain line rotated so the default grain direction is
  vertical, and verify the stored value the engine receives is unchanged
- [ ] 4.7 Document the two colour sources in the shipped reference file: the
  strain ramp (its saturation values and the colour at each end) and the
  engine's debug buffer, so neither mode's colours have to be guessed
- [ ] 4.8 Engine (Qianyi_DP): expose a bulk per-vertex force/stress readout, so
  `stress` can show the engine's own quantity instead of the editor's strain

## 5. 3D viewport overlays

- [x] 5.1 Add one Overlays panel to the 3D sidebar that owns the vertex-colour
  mode, the seam overlay (its line width) and the HUD, with everything off by
  default except the HUD (which draws nothing until a frame has been timed)
- [x] 5.2 Draw the panels again with a colour per vertex - the strain ramp or
  the engine's debug values - with LESS_EQUAL depth and a shader-side lift
  towards the camera so it lands on the surface Blender already shaded without
  flickering, and no material is created or assigned
- [x] 5.3 Draw a line between each paired stitch vertex, in the seam's own
  colour and at the chosen width, depth tested, skipping a seam whose sides
  cannot be resolved
- [x] 5.4 Hide every overlay while Blender's own overlays are off, and bring it
  back with the same settings when they are shown again
- [x] 5.5 Add the HUD: the run state, the RTS line in the documented format, the
  solver name and the frame count, from frame timings the manager records
- [x] 5.6 Record the timings from every path that advances the simulation (the
  live run, the manual frame steppers and `qyapi.sim.step`)
- [x] 5.7 Stop `debug_draw_3d.py` from registering its draw handler at startup,
  so the retired scratchpad no longer runs on every redraw (its own operator
  still registers it on demand), and build the overlays in a new module instead
- [x] 5.9 Draw the seam preview from the scene (the sewing objects and the
  panels' current meshes) so it works with no simulation and whatever shape key
  is active, and invalidate it on the pose (shape key values and transforms) as
  well as on an engine frame
- [ ] 5.8 Verify in a live session that the overlays are hidden with Blender's
  overlays, that the stress and debug colourings land on the cloth without
  z-fighting, and that the seam lines are hidden behind it

## 6. Avatar silhouette guide

- [x] 6.1 Project the project's selected collection along a world axis into the
  pattern space in millimetres, with the project's offset, and verify a 1 m
  edge projects to 1000 mm and that the offset shifts it by exactly that much
- [x] 6.2 Draw the projected triangles filled behind the panels and the
  projected mesh edges over them, each with its own colour and opacity
- [x] 6.3 Add the project properties (collection, switch, axis, offset, colour,
  fill and mesh opacities) and the pattern editor panel that exposes them, with
  the guide off by default
- [x] 6.4 Cache the projection on the selection, the transforms, the settings
  and the engine's frame, with a bounded rebuild rate while the selection
  deforms
- [x] 6.5 Verify the guide is display-only: enabling it changes no panel
  vertex, mesh, sewing or payload entry
- [x] 6.6 Verify that a project with no collection named projects nothing and
  reports it in the controls

## 7. Script surface and documentation

- [ ] 7.1 Expose the state, the multiplier and the display mode through
  `qyapi`, and verify a write-then-read round trip for each
- [ ] 7.2 Update `docs/agent-api.md` with the new calls and the state meanings,
  in English
- [ ] 7.3 Update the README feature table so the delivered states and modes
  stop being listed as missing

## 8. Integration verification

- [ ] 8.1 Build one scene that uses all four states, every display mode, the
  silhouette and the overlays, step it, and verify: the frozen panel does not
  move, the excluded panel is absent from the payload, the stiffened panel
  deflects less than its unstiffened twin, and every frame is finite
- [ ] 8.2 Verify a full save, close and reopen of that scene reproduces the
  same payload and the same display mode
