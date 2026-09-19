## Context

See `proposal.md` - Why. Current state that shapes the approach:

- A pattern owns its outline, internal lines, fabric, collision layer,
  granularity, grain direction, mirror flag and generator link
  (`Qianyi/model/pattern.py`). Nothing on the pattern says whether it takes part
  in the simulation: the switch lives on the mesh object
  (`ObjectSimulationProperties.participate_in_simulation`) and the 3D sidebar
  only shows it for objects that are not pattern meshes.
- The bridge (`Qianyi/simulation/simulation_manager.py`) builds one payload per
  object from the mesh plus the pattern's fabric, and sends per-object
  `fixed_vertices` / `attached_vertices` weights read from the vertex groups
  `QYPinFix` / `QYPinAttach`. The engine already accepts pinned cloth vertices
  and a collider object type.
- The engine reports a per-vertex debug colour array, the bridge already
  downloads it and writes it into the mesh's `Color` attribute; nothing in the
  UI turns that into a picture.
- The pattern window draws through `Qianyi/gizmos/*` renderers; the fill is a
  fixed translucent colour and the mesh lines a fixed white, and
  `gizmos/temp_draw_manager.py` carries the comment
  `TODO different pattern rendering mode` at the branch that would choose.
- `Qianyi/debug_draw_3d.py` registers a 3D overlay at startup and exposes
  primitives (arrows, capsules, spheres) that only test code currently calls.

## Goals / Non-Goals

**Goals:**

- Panel behaviour and panel appearance become first-class, per-panel data that
  survives save, copy, generator rebuild and undo.
- All four states and all display modes are reachable from the UI the add-on
  already has (pattern list, 3D sidebar, tool settings) with no new window.
- Display and state changes never recompute geometry, and every state maps onto
  a payload the engine already accepts.

**Non-Goals:**

- Plasticity (baking the current drape into the rest shape). That needs the
  engine's rest-shape work; this change only prepares the panel state field and
  the UI that a later change will attach to.
- A physically rigid panel. `stiffened` is a stiffness multiplier, not a
  rigid-body solver.
- Skiving (thickness tapering along an edge) and bonding (fusing two panels
  without a seam); both need geometry and contact semantics that do not exist
  yet.
- Editing stress colours' numeric scale from the UI beyond the documented
  presets.

## Decisions

### D1. State is a single enum property on the pattern

`simulation_state` (`simulate` | `excluded` | `frozen` | `stiffened`) plus
`stiffness_scale` live on `Pattern`, next to `collision_layer` and `fabric_uuid`.
A single enum, not independent flags: the four states are mutually exclusive in
the competitor tools this mirrors, and independent flags would need a
precedence rule that the UI cannot explain.

*Alternative:* keep the existing mesh-level `participate_in_simulation` and add
three more booleans. Rejected: the flag is on the mesh, so it is lost when a
mesh is regenerated, it is invisible in the pattern list, and a generator
rebuild would silently reset it.

### D2. Excluded panels are dropped from the payload, not pinned

`setup_data()` skips excluded panels, so the engine never sees them. This is the
cheap and unambiguous meaning of "not solved": no contacts, no mass, no cost.

*Alternative:* send them and set every weight to zero. Rejected: it costs the
full simulation cost for a panel the user asked to ignore, and it still
collides.

### D3. Frozen is full pinning, not a collider object

Freezing writes weight 1.0 into `QYPinFix` for every vertex of the panel's mesh.
The panel stays cloth, keeps its sewings and its fabric, is still a collider,
and unfreezing is the removal of the weights the freeze added.

*Alternative:* hand the panel to the engine as a collider object (the payload
already has an object type for that). Rejected: a collider loses its cloth
identity - it would no longer hold a seam, it would be excluded from the
engine's cloth area and self-contact bookkeeping, and the frontend would have
to drop and re-add seams on every freeze.

The weights are written into the same group the user can edit by hand, so
freezing records which vertices it pinned (a per-pattern set) and unfreezing
removes only those.

### D4. Stiffened is a per-panel fabric override

The payload's `stretch` and `bending` are scaled by `stiffness_scale` for that
panel only, at the point where `build_object_payload` reads the fabric. The
fabric asset is untouched, so two panels sharing a fabric can differ.

*Alternative:* clone the fabric into a new asset per stiffened panel. Rejected:
it fills the fabric list with near-duplicates and makes "which fabric is this"
ambiguous; the scale is one number, not a material.

### D5. Display mode is scene state; per-panel overrides are not offered

The active mode is a scene property (like the existing
`interactive_self_intersection_check`), because a pattern maker switches the
whole window, not one panel at a time. The renderers take the mode as an
argument at draw time; nothing about a panel's data changes.

*Alternative:* a per-panel mode. Rejected as a first cut: it doubles the UI and
the state for a case nobody asked for; the silhouette guide (D7) is the one
place where per-panel control is genuinely needed.

### D6. Debug reads the engine's buffer; stress is derived in the editor

`debug` uses what the bridge already produces: `get_debug_colors()` is
downloaded per frame and written to the mesh `Color` attribute, and the change
adds the draw path that uses it (plus a bundled material for the 3D viewport).

`stress` cannot use that buffer: measured on the engine side, it is the
*collision debug* colouring - grey (0.5, 0.5, 0.5) for an untouched vertex and
yellow where a contact pair was found - not a force or a stress. Painting it as
"stress" would be a lie about what the picture means. The editor therefore
derives its own quantity from the two vertex sets it already downloads: the rest
positions in `QYBasis` and the frame's positions in `QYSim`, as the mean
relative length change of each vertex's incident edges (`utilities/strain.py`).
That is the same measure the project reports as stretch when it compares
simulated area with the pattern's area, and it is computable in the frontend
with numpy in a few milliseconds per panel.

The engine's own per-vertex force would be better and is recorded as a follow-up
task: one bulk readout per frame, then `stress` switches source without changing
the display contract.

When no frame has been produced both modes fall back to `solid` with a message,
because a colour scale over an empty or zeroed buffer is worse than no colour.
What was derived from a frame is cached under the engine's frame key, so a
redraw that did not advance the simulation neither re-derives the strain nor
re-uploads a batch.

### D7. The silhouette is one projection of a named collection, drawn in the window's own space

The project names a collection and the guide projects it once into the pattern
window's space: world-space vertices, one world axis dropped, the remaining two
scaled from metres to millimetres and moved by the project's offset. Panels are
already drafted in that space (millimetres, each panel placed by its own
anchor), so the body lands next to them at 1:1 and every panel sees the same
backdrop - which is what a pattern maker aligns against, and why the projection
is per project rather than per panel.

The projected triangles are drawn filled, and the projected mesh edges over
them, because aligning a panel against a body needs its surface *and* its
seams; both have their own colour and opacity, and the mesh overlay can be
switched off.

The projection is cached in the draw path: the batches are rebuilt when the
selection, the objects' transforms, the settings or the engine's frame change,
and a deforming selection is followed at most every 50 ms. A redraw that
changed nothing costs one signature comparison, which is the answer to "will
this be slow?" - the expensive work (reading tens of thousands of vertices,
building two batches) happens on change, not per frame.

*Alternative:* project into each panel's own space, per panel. Rejected: a
panel's anchor would then decide where the body appears, so two panels could
show the body at different places and no shared alignment would exist.

*Alternative:* precompute the silhouette into the document and store it on the
panel. Rejected: it would be saved in the file, invalidated by every avatar
edit, and would leak a display aid into the document model.

### D8. One display panel for everything drawn over the viewport

The seam overlay, the stress colours and the debug primitives share one panel
in the 3D sidebar and all default to off. The current unconditional
registration in `debug_draw_3d.py` becomes a no-op unless the panel asks for it.

## Risks / Trade-offs

- [Freezing by weights fights a user's hand-made pins] -> the freeze records the
  vertex set it wrote; unfreeze removes only that set, and a test covers a panel
  with pre-existing pins.
- [A stiffened panel that shares a fabric drifts from the asset] -> the payload
  is the only consumer of the scale; the asset keeps its own values and the
  panel's UI shows both numbers (base and scaled).
- [Stiff enough to be called rigid becomes unstable at the engine's step] ->
  the multiplier's range is capped and the shipped default is conservative; the
  verification task measures a stiffened skirt at the shipped step before the
  cap is documented as final.
- [The silhouette costs draw time on a dense avatar] -> the projection runs
  over the collider's own triangles with numpy and caches by transform; the
  task list measures a 24k-vertex body before the guide is enabled by default
  for anyone.
- [Display modes and the stress path disagree about colour] -> one documented
  scale table in the spec file is the single source, and both paths read it.
- [Excluded panels surprise a user who expected them to collide] -> the state's
  UI text says "not solved and not a collider", and the frozen state is
  documented right next to it as the one that does collide.

## Migration Plan

Purely additive. Existing panels read as `simulate` (the enum default), so every
saved project and every generator rebuild behaves exactly as before until a user
changes a state. Rollback is reverting the change; no saved data needs
migration because the new properties are optional with defaults. The one
behavioural change for existing files is that the 3D debug primitives stop
drawing by default, which is the intended fix.

## Open Questions

- Whether `stress` and `debug` need more than one named scale each (for example
  stretch versus bending) or whether one engine-provided scale is enough; the
  answer changes only the panel, not the data model.
- Whether the silhouette should also snap or measure (a distance readout against
  the body). Deferred: the guide as specified is enough to align by eye.
