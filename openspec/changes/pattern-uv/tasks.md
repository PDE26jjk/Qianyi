## 1. UV write in the mesh rebuild

- [x] 1.1 Read the mesh's current UV into numpy before `mesh.clear_geometry()`
  (the `UVMap` layer, one value per vertex from its first loop) and verify a
  rebuild reads the layer that is on the mesh at that moment, by moving the UV
  in the UV editor and then rebuilding
- [x] 1.2 Write the new UV into the mesh's `UVMap` layer after the loops are
  written, reusing the `res_index` / `res_weight` the simulated-vertex mapping
  already computed, and verify a rebuild with no geometry change leaves every
  UV unchanged
- [x] 1.3 Seed the UV when there is no readable old UV or no readable old
  positions, and verify a pattern meshed for the first time has a `UVMap` layer
  whose values equal its pattern-space positions
- [x] 1.4 Verify the carry-over across a topology change with a divide-edge and
  a corner edit: a vertex whose pattern-space position did not move keeps its
  UV, and the changed point count does not raise
- [x] 1.5 Verify a rebuild still makes exactly one engine call and that the extra
  cost is one `foreach_get` plus one `foreach_set` over the loops, by profiling
  a fine pattern's rebuild before and after

## 2. Seed scale setting

- [x] 2.1 Add the global `uv_scale` float to the scene's Qianyi settings with a
  default of 1.0, and verify a file saved with a changed value reopens with it
- [x] 2.2 Verify the seed multiplies by the scale (2.0 doubles a pattern's UV
  span) and that changing the scale alone does not modify an existing mesh's UV

## 3. Mirror

- [x] 3.1 Negate `u` in the seed for a mirrored pattern, and verify a mirrored
  copy's UV is the negative of its source's and the texture reads the same
  direction rather than flipped
- [x] 3.2 Negate `u` of the current UV at the moment the mirror flag changes on
  an already-meshed pattern, and verify the rendered texture is not flipped
  after toggling mirror

## 4. Reset control

- [x] 4.1 Add a Qianyi panel in the UV editor's sidebar (a new IMAGE-space panel
  base) with a reset control that resolves the pattern from
  `context.active_object`, and verify it appears for a pattern mesh and not for a
  collider
- [x] 4.2 Implement the reset as a re-seed from the mesh's current positions and
  `uv_scale`, as one undo step, and verify one undo restores the previous UV and
  that no rebuild or resample is triggered
- [x] 4.3 Verify the reset changes nothing but the UV: vertices, triangles,
  pins, sewings and the payload the bridge builds are identical before and after

## 5. Documentation

- [x] 5.1 Document the `UVMap` contract, the per-vertex limitation and the
  `uv_scale` setting in the add-on's reference notes, in English, and verify a
  reader can tell what the reset does without reading the code
- [x] 5.2 Record the delivered UV half in the README roadmap while keeping the
  texture half open, and verify the entry does not claim a texture is displayed

## 6. Integration verification

- [x] 6.1 Build one scene with a pattern, a mirrored copy and a sewing (through
  `tools/make_probe_scene.py` or the same in-process construction), edit the UV
  by hand, rebuild every pattern through several edits, and verify the UV follows
  the fabric and the payload is unchanged
- [x] 6.2 Save, close and reopen the scene, rebuild, and verify the UV that was
  saved is the one carried over
