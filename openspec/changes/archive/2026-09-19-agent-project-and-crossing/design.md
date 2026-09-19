## Context

See proposal.md for motivation. The measurements that shape the approach:

- On a blank file `qyapi.state()` reports no project and `qyapi.patterns.create`
  refuses with "this scene has no project".
- `bpy.data.node_groups.new("NodeTree", "QianyiNodeTree")` does create the tree,
  and `scene.qmyi.active_project_index` does select it, but the next
  `patterns.create` raises an `AssertionError`: the project and its default
  fabric have no identity yet. After `project.get_temp_data()` and
  `fabric.get_temp_data()` (which assigned uuid -1439170049) the same call
  succeeds. `refresh_all_uuids()` does not fill these in - it only registers
  objects that already carry an identity.
- `QianyiProject` inherits `ModelData.name`, a `StringProperty` that shadows the
  node tree's own `name`: `new("Project2", ...)` gives a datablock keyed
  "Project2" while `project.name` reads `''`, and `project.name = "proj1"` sets
  the property without renaming the datablock (`node_groups.get("proj1")` is
  None). `group.bl_rna.properties` lists `name` twice. The editor's project panel
  draws that same property (`QY_UL_ProjectList.draw_item` uses
  `row.prop(item, "name")`, and its filter reads `node_trees[i].name`), so the UI
  and the surface agree on the name - but a project a script creates has an empty
  one and shows up as a blank row until it is set.
- `active_project_index` indexes `bpy.data.node_groups`, which can also hold node
  trees that are not projects.
- The mesh stage already refuses a crossing outline and keeps the panel's
  previous mesh; a crossing outline that reaches the sampler leaves an illegal
  memory access in the 2D BVH that surfaces on the next engine call (measured
  earlier in this project), and `sim.prepare()` already refuses crossing panels.
- The geometry writes refuse in two ways today: a vertex-list crossing is caught
  before anything is written, while a handle or spline change that only crosses
  after sampling is written, tested, and put back on failure (measured: the
  handle reads back at its old value).
- The scene's `interactive_self_intersection_check` switch is read by
  `interactive_edit_allowed`, which only the interactive operators call.

## Goals / Non-Goals

**Goals:**

- A blank file is enough: one call makes a project that every other call can use.
- One addressable name per project, with the editor's own list kept in step.
- Crossing outlines as a per-call choice for a caller that is building a shape.
- Honest reporting: an answer says when it left a crossing outline and when the
  panel's mesh is therefore stale.

**Non-Goals:**

- A session-wide or global switch for crossing outlines (the maintainer's
  decision: per call only).
- Using the scene's Check Self-Intersection switch, which belongs to the
  interactive operators.
- Project templates, duplication, a body or measurement source, m-to-n sewing,
  new UI, or any engine change.

## Decisions

### D1 - A `projects` group addressed by name

Listing, creating, activating, renaming and removing live in `qyapi.projects`,
and every one of them takes a name. `active_project_index` stays an
implementation detail: it indexes all node trees in the scene, not projects, so
it is not an identity a caller should hold.

*Alternatives*: exposing the index (it breaks as soon as the scene holds another
node tree); addressing by the datablock name (it is not what the rest of the
surface reads).

### D2 - `create` performs the four steps a caller cannot see

Creating a project makes the node tree, gives the project and its default fabric
their identities, names them, and selects it. The identity step is the one that
matters: it is invisible until the first panel call raises an assertion, which is
exactly the kind of gap this surface exists to close.

*Alternatives*: leaving the identity work to the caller (the measured
`AssertionError`); making every other call repair a half-built project (silent
action at a distance).

### D3 - The addressable name is the one that matters, and create sets it

`create` and `rename` write the add-on's name property, which is the name the
surface addresses and the one the editor's project list draws. The node tree's
own datablock key is reported as a diagnostic but is not an address: it is set
once by Blender when the tree is made and cannot be renamed through the shadowed
accessor, so treating it as a name would promise something the surface cannot
keep.

*Alternatives*: reporting the property and the datablock key as two names a
caller may use (two rules, one of which cannot be maintained); leaving the
property empty and addressing only by list position (a project with no name in
the panel, and an address that moves when the list is reordered).

### D4 - `allow_crossing` is a per-call argument

The seven geometry writes - `create`, `set_point`, `add_point`, `remove_point`,
`set_handle`, `add_spline_point`, `remove_spline_point` - take
`allow_crossing=False`. With it off nothing changes; with it on the outline test
is skipped for that call, and only for that call. There is no session or scene
setting behind it.

*Alternatives*: a module-level switch (rejected by the maintainer: state that
outlives a call makes the next caller's behaviour depend on the last one); reusing
the scene switch (rejected: it means "the interactive tools check", and the
surface must not change what the UI does).

### D5 - The mesh and simulation gates do not move

Allowing a crossing outline allows the *data* to be crossing. The mesh stage
still refuses to sample it (the panel keeps the mesh it had) and a simulation
still refuses to start on it: that is the difference between an intermediate
shape and a mesh the engine can be handed, and the engine's failure mode there is
a CUDA fault, not an exception.

### D6 - The answers say what state the panel was left in

Every write answer carries the panel's `outline_validity`, the crossing point
when one is known, and `mesh_stale` - true when the mesh was not rebuilt because
the outline is invalid. A read answers the same way, computed from the cached
validity, so a caller that picks up a scene can see it without asking for an
edit.

### D7 - With the flag on, the post-write test reports instead of restoring

The handle and spline writes test the sampled outline after writing and put the
value back when it fails. With `allow_crossing=True` that path reports the
crossing in the answer instead of restoring, which is the whole point of the
flag; with it off the restore stays exactly as it is.

### D8 - The generator rebuild keeps its own policy, and only reports better

`apply_generator` already writes the geometry, lets the mesh stage keep the
previous mesh when the outline crosses or is degenerate, and counts those panels
(`invalid_panels`, `degenerate_panels`). That is the same policy as this change,
reached from the other side, so the rebuild gains no `allow_crossing` argument
and no refusal: adding either would make a parameter change stricter than it is
today and break rebuilds that currently work. What it does gain is the reporting
the pattern answers get - which panels were left invalid, and that their meshes
were not rebuilt - so a caller reading the report can see the same thing.

## Risks / Trade-offs

- A crossing panel is a trap for the next call: its mesh is stale, it cannot be
  simulated, and a build that forgets to fix it looks finished -> the answer says
  so every time, `validate()` reports it, and `sim.prepare()` refuses by name.
- The two names can still diverge if a user renames the datablock in the outliner
  -> both are reported, and addressing stays on the property.
- `allow_crossing=True` on the two topology edits (`add_point`, `remove_point`)
  can leave a shape the mesh stage will not touch for a long time -> documented,
  and the worked example fixes the outline in the next call.
- Removing a project takes its panels and sewings with it -> the answer reports
  the counts and does not ask (the earlier decision for removals).
- The flag makes it easy to build a scene that cannot simulate -> `validate()` is
  documented as the step before `sim.prepare()`.

## Migration Plan

- Additive: one new submodule, one new argument, extra keys in existing answers.
  Nothing persisted changes, and an older `.blend` opens unchanged.
- Rollback: remove the submodule and the argument; the extra answer keys are
  harmless to leave or drop.

## Open Questions

- Whether `projects.remove` should refuse while the simulation surface is bound
  to a panel of that project; deferrable, because the simulation refuses a scene
  whose panels are gone anyway.
- Whether `create` should accept an initial component (a project that starts with
  a generator) - a convenience, not a requirement.
