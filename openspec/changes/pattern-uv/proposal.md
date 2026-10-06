## Why

A pattern's mesh is rebuilt from scratch on every geometry edit, and the sampler
returns its points in a different order each time, so nothing attached to a
vertex survives a rebuild by index. The add-on produces no UV layer at all,
which leaves a fabric texture with nothing to sample: UV is the prerequisite for
the material work that comes next.

## What Changes

- Every pattern mesh gains a `UVMap` UV layer, written as part of the existing
  rebuild in `generate_pattern_mesh`.
- The seed of the UV layer is the pattern-space position of each sample point,
  multiplied by a new global `uv_scale` setting on the scene's Qianyi settings.
  The seed is used on the first build and whenever the UV is reset.
- On a rebuild, the UV is carried over from the mesh's **current** UV layer -
  including the edits a user made in the UV editor - by the same barycentric
  mapping the bridge already uses to carry simulated vertices: the new sample
  points are located in the old triangulation and the old UVs are interpolated.
  The UV layer is read before the mesh is cleared.
- A mirrored pattern gets a mirrored seed (its `u` negated), so the texture is
  not flipped by the object's `scale.x = -1`.
- Add a Reset UV control, exposed in the UV editor's N-panel, that re-seeds the
  active pattern mesh's UV from the pattern-space positions the mesh holds now.
- UVs are per-vertex: one value per mesh vertex, copied to each of its loops. A
  UV seam a user cut by moving individual loops does not survive a rebuild;
  this is documented as a known limitation.

## Capabilities

### New Capabilities

- `pattern-uv`: the pattern mesh's UV layer - its seed from pattern space, the
  scale setting that sizes it, its carry-over across a mesh rebuild including a
  user's edits, the mirror convention, and the Reset UV control.

### Modified Capabilities

<!-- None: no existing capability's requirements change. The material and the
     display of the texture are deliberately out of scope. -->

## Impact

- `Qianyi/model/pattern_mesh.py`: the rebuild writes the UV layer and carries it
  over, inside the attribute-mapping block that already computes the
  `res_index` / `res_weight` used for simulated vertices.
- `Qianyi/model/qianyi_data.py`: the global `uv_scale` setting.
- A new UV editor panel and a Reset UV operator, with their ids in
  `Qianyi/declarations.py` and their registration in `Qianyi/ui/__init__.py`.
- No engine (Qianyi_DP) change, no simulation-bridge change, and no change to the
  model files the project marks as protected (`pattern.py`, `sewing.py`,
  `section.py`, `internal_line.py`, `geometry.py`, `qianyi_project.py`,
  `simulation/**`).
- The UV data itself lives in the mesh and is saved with the file; the only new
  add-on property is the global `uv_scale` setting. No material is created or
  assigned, and the UV is not sent to the engine.
