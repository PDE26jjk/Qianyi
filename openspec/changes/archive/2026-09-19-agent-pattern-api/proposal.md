## Why

The script surface covers the simulation and nothing else, so a client that has
to add or change a pattern today reaches into Blender data by hand and meets every
sharp edge of the add-on at once: the identity map that undo and file loading
clear, the mesh and the sewing stitches that are derived from the outline, the
instance list that is a linked list, and the sewing remap a rebuild runs. It is
measured, not theoretical: building one generator from a fresh session fails with
`'NoneType' object has no attribute 'pattern'` until the identities are
refreshed. An agent cannot be asked to know that.

## What Changes

- Add pattern authoring to the surface: create a pattern from points, edit its
  points, edge handles, spline points and internal lines, place it, copy it as an
  instance or a mirror, remove it, and read it back.
- Add a read-back that answers the question an agent actually asks: a pattern's
  edges (index, label, type, endpoints, handles, spline points, length) and every
  sewing that touches it, plus a separate call for the point coordinates.
- Add sewing control: create a seam between two edges with a direction flag,
  create one at explicit positions along the edges, recolour, remove and list.
- Add parametric patterns: create a generator from a library component with its
  parameters, change several parameters in one rebuild, detach, remove, and read
  the parameter table and the patterns a generator owns.
- Add the component library surface: list what the library offers, describe one
  component's parameters, build a component's outlines **without touching the
  scene**, and reload the user component folders. This is the environment the
  next change needs so an agent can write and debug its own components.
- Add fabric assignment by name, with the project default when none is given.
- Make the whole group safe by construction: every write validates before it
  writes, refuses with the reason instead of half-applying, resolves names from
  the scene at the start of the call, and leaves one undo step behind.
- Document the group in the module and in the shipped reference file, with the
  millimetre rule and one worked example: create a collar, sew it to the torso,
  change the torso's parameters, and settle the result with a few simulation
  frames.

Not in this change: writing GC component code and exposing its parameters to the
user (the next change - this one only builds the environment it needs), semantic
edge labels on the shipped GC presets, measurement sources and body fitting,
m-to-n sewing, any new UI, and any engine or DP backend change.

## Capabilities

### New Capabilities

- `agent-pattern-authoring`: creating, editing, placing, copying, removing and
  reading back patterns, and the validation that keeps a broken outline away from
  the mesh and the engine.
- `agent-sewing-control`: creating, removing and listing sewings, the direction
  flag, and reading the sewings of one pattern.
- `agent-pattern-generators`: parametric patterns from library components - the
  component library surface, creating and rebuilding generators, detaching and
  removing their groups, and fabric assignment.

### Modified Capabilities

None. This repository has no capability in `openspec/specs/` yet, so no existing
requirement changes.

## Impact

- New code: four submodules of the existing `qyapi` package (`patterns`,
  `sewings`, `generators`, `components`), the documentation they ship, and the
  reference file that mirrors it.
- Extracted code, needed because it lives in modal operators today:
  `Pattern.copy_pattern()` is an empty stub while the real copy / mirror /
  instance logic sits in `Qianyi/operators/_2d_pattern_copy_instance.py`; the
  internal-line-from-a-polyline path and the curve write path (handle types and
  spline points) have no model-level function either. The operators keep working
  and call the extracted functions, so there is one implementation.
- Unchanged: the pattern, sewing and mesh data models, the `.blend` format, the
  simulation surface, every pattern and the engine contract.
- No new dependency: numpy, as bundled with Blender.
