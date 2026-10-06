## Context

See `proposal.md` - Why. The current state that shapes the approach:

- A pattern's mesh is built in one place: `Pattern.generate_mesh` calls
  `generate_pattern_mesh` (`Qianyi/model/pattern_mesh.py`). Every editing tool,
  generator and agent call ends there, so one writer covers the whole add-on.
- The mesh is rewritten in full on every build (`mesh.clear_geometry()`),
  because the sampler returns its points in a different order each run. Nothing
  can be kept by index; an attribute survives a rebuild only by being mapped
  through the geometry.
- That mapping already exists. With the old sample positions (`QYBasis`) and the
  triangles written last time (`pattern.mesh_triangles`, falling back to
  `mesh.loop_triangles`), the rebuild calls
  `geometry.find_map_weight(old_points, triangles, new_points)` and interpolates
  the simulated vertex set (`QYSim`) with the returned barycentric weights.
- `find_map_weight` is a 2D-to-2D query: a 2D BVH over the old triangles returns,
  for each new point, the nearest triangle and that triangle's barycentric
  weights. Outside a triangle the weights are the affine extrapolation, not a
  clamped projection, so an affine UV edit (a move, a rotation, a scale) is
  reproduced exactly.
- The simulation drives the same mesh object the viewport shows (`QYSim` shape
  key), so a UV layer written on a pattern mesh is what a material would sample;
  the bridge and the engine are not involved.
- The UV editor is the image editor (`IMAGE_EDITOR`) working in its UV mode, and
  the add-on registers no panel there yet.
- Project rule: an operator-side task must not edit the protected model files
  (`pattern.py`, `sewing.py`, `section.py`, `internal_line.py`, `geometry.py`,
  `qianyi_project.py`, `simulation/**`). `pattern_mesh.py` is not protected, and
  the global scale lives in the settings layer, so this change needs none of
  them.

## Goals / Non-Goals

**Goals:**

- One UV layer on every pattern mesh, kept correct across every rebuild, at the
  cost of one read and one write per rebuild and no extra engine call.
- The mesh's UV layer is the single source of truth: what a user edits in the UV
  editor is what the next rebuild carries, and it is what the file saves.
- The seed is a plain, reproducible function of the pattern, so a reset always
  has one defined answer.

**Non-Goals:**

- The material, the texture asset, and the display of a texture.
- Any UV tool beyond seeding and reset: no unwrap, no pack, no projection
  operator, no UV selection tool.
- Sending the UV to the engine or exporting it. It is display data for now.
- Preserving per-loop UV seams across a remesh (recorded as a limitation).

## Decisions

### D1. The UV lives in the mesh's own layer; nothing is cached on the pattern

The rebuild reads the mesh's current UV layer into numpy before
`mesh.clear_geometry()` and writes the new one after the loops are written.
The layer is the thing the user edits and the thing the file saves, so a cached
copy on the pattern would go stale on the first edit in the UV editor and would
not survive a reload.

*Alternative:* keep the per-vertex UV on the pattern as a temp property, the way
`mesh_triangles` is kept. Rejected: it duplicates state, it cannot see the
user's edits, and it is lost on reload.

Note the ordering constraint this creates: reading must happen before the mesh
is cleared, and it must read the layer that is on the mesh at that moment.

### D2. Reuse the barycentric weights the rebuild already computes

The block that maps the simulated vertices already computes `res_index` and
`res_weight`; the UV is one more per-vertex attribute interpolated with them.
One `find_map_weight` call, not two, and the UV and the simulated vertices
cannot disagree about where a new point came from.

When that mapping did not run - the first build, or a mesh whose old positions
cannot be read - the UV is seeded instead (D3).

*Alternative:* a second `find_map_weight` call for the UV. Rejected: it doubles
the only engine call in the rebuild for no benefit.

*Alternative:* transfer by nearest vertex. Rejected: the texture would jump
along triangle edges instead of following the surface; barycentric
interpolation is the behaviour the simulated-vertex path already has.

### D3. The seed is pattern-space position times a global scale, applied only at seed time

The seed is `uv_scale * (x, y)`, where `(x, y)` is the vertex's pattern-space
position in metres, unmirrored. The positions come from the pattern's base shape
key, the same accessor the rebuild maps the carried UV from, with the mesh's own
vertex array as the fallback for a mesh whose keys are gone: a reset and a
rebuild then read one source, so neither can place a vertex in a space the other
does not know. The scale is a global setting on the scene's Qianyi settings,
because a texture's physical scale is a property of the material and the
project, not of one panel. It is read when the UV is seeded - the first build
and every reset - and never re-applied to a UV the user has since edited, so
editing UVs by hand and changing the scale do not fight.

*Alternative:* a per-pattern scale. Rejected: it adds a second number and a UI
where one project-wide scale is what a shared texture needs.

*Alternative:* rescale the existing UV whenever the setting changes. Rejected:
it silently overwrites the user's edits and needs a second, stored "base" UV to
stay reversible.

### D4. Mirror is applied to the UV, at two moments

The mesh geometry is written unmirrored and mirrored only by the object's
`scale.x = -1`, so a texture would read flipped unless the UV's `u` is negated.
The seed negates `u` for a mirrored pattern. Flipping the mirror flag on an
already-meshed pattern does not rebuild the mesh, so the flag's writers also
negate the current UV at that moment; the copy paths set the flag before the
first build, so their seed is already mirrored.

*Alternative:* mirror the geometry instead of the object. Rejected: it is a much
larger change and against how the pattern transform is modelled.

### D5. Reset is an operator in the UV editor's sidebar, addressed by the active object

The UV editor is where a user sees the UVs, and its sidebar is where a UV tool
belongs. The operator resolves the pattern from `context.active_object`'s
simulation properties - the object being looked at - rather than from the
pattern editor's active index, which removes the ambiguity about which pattern
the button acts on. It seeds from the rest positions D3 names, so a reset lands
where a rebuild would. It writes the seed straight into the UV layer: no
resample, no rebuild, no engine call, and one undo step.

*Alternative:* a button in the pattern Property panel. Rejected: it is further
from where the UV is seen, and the target pattern would be a second, different
notion of "active".

### D6. Per-vertex UVs, written by the one mesh writer

Every vertex's UV is copied to all of its loops. This matches how the mesh is
written (one array per vertex) and keeps the transfer well defined when the
topology changes: a new vertex has one position and therefore one UV. Preserving
per-loop seams would need a per-corner transfer and a rule for which old face's
UV a new corner takes, which is a different, larger piece of work.

*Alternative:* per-corner UVs. Deferred, recorded as a limitation and an open
question.

## Risks / Trade-offs

- [A rebuild can place a new point outside the mesh it is mapped from] ->
  `find_map_weight` extrapolates the nearest triangle's affine map instead of
  clamping, so the UV continues smoothly; reset recovers a clean seed. This is
  the same behaviour the simulated-vertex mapping already relies on.
- [Clearing the geometry would drop the UV] -> the UV is read into numpy before
  `mesh.clear_geometry()` and written back after the loops; a task verifies a
  rebuild keeps exactly one `UVMap` layer with the expected values.
- [A user's per-loop UV split is lost on the next rebuild] -> stated as the
  per-vertex contract in the spec; per-corner transfer is left open.
- [Mirror toggled on an already-meshed pattern skips the rebuild] -> the UV is
  mirrored at the moment the flag changes (D4), covered by a spec scenario.
- [The UV layer adds work to every rebuild] -> one `foreach_get` and one
  `foreach_set` over the loops, no engine call; a task measures the rebuild
  before and after on a fine pattern.

## Migration Plan

Purely additive and display-only. Existing files have no UV layer; the first
rebuild after this change, or a reset, seeds one, and every later rebuild
carries it. Nothing in the pattern data, the engine payload or the simulation
changes, so rollback is reverting the change (and deleting the layer if wanted).
The new `uv_scale` setting is a saved scene property defaulting to 1.0.

## Open Questions

- Whether a later change should preserve per-loop UV seams with a per-corner
  transfer; deferred, and it does not change this spec.
- Whether the seed should use a unit other than the mesh's metres once the
  material work fixes the texture's real-world scale; the global scale already
  covers it for now.
