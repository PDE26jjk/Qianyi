## Context

See proposal.md for motivation and the specs for the behaviour contract. Facts
that shape the approach:

- The previous change shipped `qyapi`: published under that name, JSON-safe
  results, names resolved from the scene at the start of every call, one undo
  step per write through `qyapi.transaction`, no dialogs, working in `-b`. This
  change adds submodules under the same rules instead of inventing a second
  surface.
- Pattern space is millimetres; the mesh, object and world spaces are metres
  (`generate_pattern_mesh` divides the outline by 1000). `granularity` is
  millimetres and a ceiling on spacing, and the mesh stage de-duplicates points
  closer than `granularity * 0.02`.
- A crossing outline must never reach the mesh stage: the sampler drops faces and
  leaves an illegal memory access in the 2D BVH that only surfaces on the next
  engine call (measured in this project).
- `Pattern.copy_pattern()` is an empty stub. The real copy, mirror and instance
  logic lives in `Qianyi/operators/_2d_pattern_copy_instance.py`
  (`handle_success` + `_copy_geometry`), including the `instance_next_uuid`
  circular list.
- Instance copies hold the *same local geometry*; mirroring happens at matrix and
  mesh time (`calc_matrix` flips x when `is_mirror`, `generate_pattern_mesh` sets
  `mesh_obj.scale.x = -1`). The interactive tools write an edit to every chain
  member at the same index through `ProxyPoint.apply_proxy_to_instances`, and
  `Qianyi/model/pattern_instance.py` fills `pattern.instances`.
- Internal lines own their own edges, and only a per-edge `add_edge` exists -
  there is no "build a line from a polyline" function.
- `Qianyi/generators.py` already implements create, apply, detach and delete for
  generators, including the in-place rewrite, edge matching by label then
  geometry, and two mesh guards that keep the previous mesh (a crossing outline,
  and vertices closer than the mesh tolerance).
- The mesh stage carries a pattern's previous simulated positions onto the new mesh
  by barycentric interpolation (`geometry.find_map_weight`, then
  `set_simulation_vertices`), and carries the pin vertex group when the vertex
  count is unchanged.
- `Pattern.fabric`'s getter assigns the default fabric when the pattern has none,
  so reading it writes; the existing `state()` already avoids it.
- `project.last_sewing_error` carries the real reason a sewing was refused.
- A client runs one statement per call, holds no state between calls, and gets
  JSON back.

## Goals / Non-Goals

**Goals:**

- Pattern work an agent can do without knowing the add-on's internals, and without
  a call that half-applies or dies on an unrefreshed identity.
- One implementation per operation: what a modal operator already does well gets
  extracted, not reimplemented.
- A read-back shaped like the questions an agent asks: which edges does this
  pattern have, and which seams are on them.
- The environment the next change needs, so an agent can write and debug a
  component without a scene in the way.

**Non-Goals:**

- Writing component code and exposing its parameters to the user: that is the
  next change. This one only builds the surface it will use.
- Semantic edge labels on the shipped GC presets (a deliberate decision).
- New UI, measurement sources, m-to-n sewing, any engine or backend change.
- Making a hand edit survive a generator rebuild.

## Decisions

### D1 - Extend `qyapi` with submodules instead of a second surface

`patterns`, `sewings`, `generators`, `components` become submodules of the
existing package, published the same way, and follow the same law: names not
handles, refresh identities first, one undo step per write, JSON-safe results,
refusals instead of dialogs.

*Alternatives*: a separate top-level module (two surfaces to discover, two import
stories); a second API layer in the engine repository (wrong side of the
boundary).

### D2 - Extract the copy, mirror and instance logic into the model layer

`Pattern.copy_pattern()` is a stub, so the API cannot call it. The logic in the
copy operator becomes a model function, and the operator calls that function, so
both paths share one implementation - the same move this project already made for
the pen operator's pattern creation.

*Alternatives*: reimplement the copy in the API (two implementations to keep in
step, and the `instance_next_uuid` list is easy to corrupt); invoke the operator
through a context override (it is a modal state machine and needs a viewport).

### D3 - Same treatment for internal lines and the curve write path

Building an internal line from a polyline, and writing an edge as a Bezier or a
spline, are sequences that exist inside the pen and copy operators today. They
become model functions the operators use.

*Alternatives*: let the API write the collections directly (it would duplicate
the handle, spline point and refresh bookkeeping, which is where the mistakes
live).

### D4 - An edit reaches the whole instance chain

A geometry edit writes the same index in every chain member with the same local
coordinates, and the result lists the members. Mirroring stays where it is: in
the transform matrix and the mesh scale.

*Alternatives*: edit only the named pattern (copies silently diverge, and the
interactive tools do the opposite); mirror the delta into the copies (a second
rule that does not exist anywhere in the add-on).

### D5 - Read-back is an edge table, a sewing list, and a separate points call

`patterns.get(name)` returns the summary, the edge table and the sewings that
touch the pattern; the point coordinates come from `patterns.points(name)`. A
1000-edge component makes one response large enough that separating them is worth
the extra call.

*Alternatives*: one call with everything (large responses for topology-only
questions); topology only (then an agent cannot tell a straight edge from a
curve).

### D6 - The per-pattern sewing list shares one index

Both `sewings.list()` and the per-pattern list are built from the same edge to
sewing index, built once per call - the shape `Qianyi/generators.py` already uses
for its remap - so the two answers cannot disagree and the cost is proportional
to the seams, not to patterns times seams.

### D7 - Validate the inputs first, then test the derived outline and restore on failure

Blender's RNA writes have no transaction, so the rule is: every input check that
can fail runs before the first write, and each edit is a small, known change, so
a failure of the derived outline can put the previous value back exactly. That
covers the two cases that need different treatment: the checks that are
computable from the arguments (a crossing outline for a point list, a degenerate
pair, a non-positive granularity, an unknown name) and the checks that only the
derived geometry can answer (a handle change that pulls an edge across another
one). A create rolls back by removing the pattern it just made.

*Alternatives*: snapshot the whole pattern and restore it on failure (a full copy
per attempt, and it would push its own undo step); a real transaction through
`bpy.ops.ed.undo` (refused without a window, and it would fight the undo
granularity rule); never restoring (a refused edit would leave the scene in the
state it was refused for).

### D8 - The seam goes through the add-on's own sewing, with one flag and no derived direction

`sew(edge_a, edge_b, flip=False, color=None)` hands two edge points to the
add-on's click-based sewing: the two edges' first points when the flag is off,
and the first edge's first point with the second edge's second when it is on.
That sewing then decides the direction, exactly as it does for a click. `sew_at`
hands over the positions the caller gave instead.

The seam goes through `add_sewing1to1`, which the maintainer rewrote as the
single-`reverse` form while this change was being implemented (it used to take
two span flags, was orphaned when the operators moved to the click-based sewing,
and refused with `'Section' object has no attribute 'section'`). Both directions
were measured after the rewrite - 11 and 9 stitches on a pair of test patterns -
so the surface forwards to it and derives nothing. Re-deriving a direction was
never an option: it is the thing that went wrong before.

*Alternatives*: the two-flag form (broken and unused); a direction derived from
the edges' geometry (the earlier wrong seams); no direction flag at all (then a
caller cannot express the mirrored case).

### D9 - Generated patterns stay editable, and say so

The maintainer's decision: a geometry edit is equivalent to editing the mesh, the
simulation runs on the shape key, and a rebuild carries the previous result over,
so the surface allows the edit. The pattern record carries whether the pattern comes
from a generator, and the documentation states that a rebuild can rewrite what
was edited. Removing such a pattern through `patterns.remove` is refused instead,
because the add-on's own rule deletes a generated pattern's whole group: a group
goes away only through the generator's detach or remove.

*Alternatives*: refuse and point at the parameter block or `detach` (safe, but it
blocks the case the maintainer described); refuse only when a run is live (a
state-dependent refusal that is harder to explain than a warning).

### D10 - Fabric is addressed by name and read without the writing getter

Create and assign take a fabric name; no name means the project's default fabric.
Read paths never touch `Pattern.fabric`, because its getter assigns the default
and would turn a read into a write.

### D11 - Millimetres, stated and never converted

Every pattern-space input and output is millimetres, including the anchor. No
automatic metre conversion: a silent unit conversion is the failure this project
has already paid for once.

### D12 - The rebuild report says whether the simulation result was carried over

The surface compares each pattern's simulated key with its rest key before the
rebuild and asks the mesh stage after it, so the report can say that positions
were carried over - which is the caller's cue to settle the patterns with a few
`sim.step()` frames from the previous change.

## Risks / Trade-offs

- RNA writes are not transactional -> validate-first (D7), and report the objects
  already changed when a late failure happens anyway.
- Extracting the copy and curve logic can change what the operators do -> the
  operators are re-pointed at the extracted functions, and the existing probes
  must stay green before the change is considered done.
- The instance chain is a linked list that a half-built copy can break -> the
  surface uses the tolerant `instance_chain` helper instead of walking links
  itself.
- A generated pattern edit is rewritten by a later rebuild -> the pattern record and
  the documentation say so.
- Large responses for big components -> the points call is separate and the
  documentation says to read one pattern at a time.
- The shipped GC presets label their edges positionally, so label-addressed
  sewing only works for components that write labels -> documented; index
  addressing always works.

## Migration Plan

- Additive: new submodules, extracted model functions, re-pointed operators.
  Every existing entry point keeps working, and the `.blend` format does not
  change.
- Rollback: remove the submodules; the extracted functions stay because the
  operators use them.

## Open Questions

- Whether the points call should take a stride so a caller can sample a very
  large pattern instead of reading every vertex.
- Whether a create should eventually accept a curve description directly instead
  of build-then-`set_handle`; deferred, because one creation path is what keeps
  the validation in one place.
