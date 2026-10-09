# Qianyi agent API (`qyapi`)

The add-on exposes a small script surface so an agent that can run a Python
statement inside Blender can drive the simulation without knowing the add-on's
internals. This file mirrors what the module itself documents: a client that can
only run Python can read the same text with `print(qyapi.help())` and
`qyapi.help("<topic>")`.

## Loading it

```python
import bpy, importlib             # any session where the add-on is registered
addon = next(key for key in bpy.context.preferences.addons
             if key.endswith(".Qianyi"))
qyapi = importlib.import_module(addon + ".qyapi")
```

The two lines above work with a viewport and in a background (`-b`) session. The
package name carries the repository the add-on was installed from
(`bl_ext.user_default.Qianyi`, `bl_ext.blender_org.Qianyi`, ...), so the key is
looked up in the preferences rather than written out. A session that loaded the
package by path instead, as a study notebook does, reaches the same module under
the name it loaded - `qmyi.qyapi` there.

There is deliberately no top-level `import qyapi`: publishing that name means
writing into `sys.modules` from the add-on, and Blender reports a top-level
module whose file lives inside an extension as a policy violation.

## Discovery

| Call | Returns |
| --- | --- |
| `qyapi.help()` | the entry-point index: name, purpose, arguments and their units |
| `qyapi.help(topic)` | one topic: `objects`, `patterns`, `placement`, `units`, `undo`, `not-offered` |
| `qyapi.state()` | a JSON-safe snapshot of the scene |

`qyapi.state()` returns:

```python
{
  "surface": {"module": ..., "version": 1, "background": False},
  "scene": {"name": ..., "file": ..., "frame": ...},
  "active_project": "md1",
  "projects": [{
      "name": "md1", "pattern_count": 2, "sewing_count": 4,
      "fabric_count": 1, "generator_count": 0,
      "patterns": [{
          "name": "Pattern2D_45210", "index": 0,
          "vertices": 14, "edges": 14, "internal_lines": 0,
          "granularity_mm": 5.0, "collision_layer": 0,
          "fabric": "Default Fabric", "mesh_object": "Pattern2D_45210",
          "outline_validity": "unknown", "generated": False}],
  }],
  "simulation": {...},          # the same dict sim.status() returns
}
```

`outline_validity` is the cached answer, and `unknown` is not `valid`: it means
the outline has not been tested since it was last edited. The mesh and the
simulation always test before they use an outline.

## Projects

| Call | Arguments | Returns |
| --- | --- | --- |
| `qyapi.projects.list()` | - | every project with the name it is addressed by, whether it is active, and its counts |
| `qyapi.projects.active()` | - | the project that calls without a project name work on |
| `qyapi.projects.create(name=None, activate=True)` | name | the new project, ready to use |
| `qyapi.projects.activate(name)` | name | the project, now active |
| `qyapi.projects.rename(name, new_name)` | new name | the project under its new name |
| `qyapi.projects.remove(name)` | name | what was removed, and what went with it |
| `qyapi.projects.fabrics(project=None)` | - | every fabric: weight (g/m²), thickness (mm), friction, stretch, bending, colour, and the patterns that wear it |
| `qyapi.projects.fabric(name, project=None)` | fabric name | one fabric, the same fields |
| `qyapi.projects.set_fabric(name, weight=None, thickness=None, friction=None, stretch=None, bending=None, color=None)` | the properties to change | the fabric, with what changed |

A project is addressed by the add-on's own name, which is also the name the
editor's Project panel draws. Creating one by hand is three steps a caller cannot
see - the node tree, the identities of the project and of its default fabric, and
the name - and the middle one only shows up as an assertion inside the first
pattern call. `projects.create()` does all of it, so this works from a blank file:

```python
import bpy, importlib                          # see "Loading it" above
qyapi = importlib.import_module(
    next(k for k in bpy.context.preferences.addons if k.endswith(".Qianyi"))
    + ".qyapi")

qyapi.projects.create("my project")               # identities, name and active index
pattern = qyapi.patterns.create([[0, 0], [100, 0], [100, 80], [0, 80]],
                              name="front", granularity_mm=10)
qyapi.projects.rename("my project", "skirt")
qyapi.projects.list()                             # [{name, datablock, active, patterns, ...}]
```

`datablock` is the node tree's own key, reported for a caller that has to find
the tree in `bpy.data`; it is not an address.

## patterns

pattern space is millimetres throughout - a vertex, an anchor, a handle.

| Call | Arguments | Returns |
| --- | --- | --- |
| `qyapi.patterns.list(project=None)` | - | every pattern: counts, fabric, mesh, validity, chain |
| `qyapi.patterns.get(name)` | pattern name | summary + edge table + the sewings on that pattern |
| `qyapi.patterns.points(name)` | pattern name | the outline vertices, in millimetres |
| `qyapi.patterns.create(points, name=None, granularity_mm=None, fabric=None, allow_crossing=False)` | `[[x, y], ...]` (mm) | the new pattern, with the name it got |
| `qyapi.patterns.set_point(name, index, xy, allow_crossing=False)` | vertex index, `[x, y]` | the edited pattern |
| `qyapi.patterns.add_point(name, edge, xy, allow_crossing=False)` | edge index or label, `[x, y]` | splits one straight edge |
| `qyapi.patterns.remove_point(name, index, allow_crossing=False)` | vertex index | merges the two edges that met there |
| `qyapi.patterns.set_handle(name, edge, which, xy=None, type=None, allow_crossing=False)` | 1 or 2, `[x, y]`, `VECTOR`/`FREE`/`ALIGNED` | the edited pattern |
| `qyapi.patterns.add_spline_point(name, edge, xy, allow_crossing=False)` | edge, `[x, y]` | makes the edge interpolate through it |
| `qyapi.patterns.remove_spline_point(name, edge, index, allow_crossing=False)` | edge, index | |
| `qyapi.patterns.add_internal_line(name, points, is_hole=False, closed=False)` | `[[x, y], ...]` (mm) | adds a cut |
| `qyapi.patterns.remove_internal_line(name, index)` | index | |
| `qyapi.patterns.transform(name, anchor=None, rotation=None, grain_dir=None, collision_layer=None, mirror=None)` | anchor in mm, angles in radians | places the pattern *in the pattern window*; the mesh does not follow (see Placement) |
| `qyapi.patterns.copy(name, mirror=False, anchor=None)` | anchor in mm | the copy, linked into the same instance chain |
| `qyapi.patterns.remove(names)` | one name or a list | what went, and the sewings dropped with it |
| `qyapi.patterns.validate(names=None)` | - | the patterns whose outline crosses itself |
| `qyapi.patterns.fabrics()` | - | the project's fabric names, the same list as `projects.fabrics()` |
| `qyapi.patterns.assign_fabric(name, fabric)` | fabric name | the pattern |

An outline is always a closed, counter-clockwise loop: `create` closes it, and
there is no open-pattern form. A name that is taken gets a suffix
(`collar` -> `collar.001`) and the answer reports both the requested and the
final name.

`patterns.get()` is the read an agent asks for most:

```python
{"name": "torso_front_half", "vertices": 4, "edges": 4, "generated": True,
 "chain": ["torso_front_half"],
 "edges": [{"index": 0, "label": "edge0", "kind": "straight",
            "v0": 0, "v1": 1, "p0": [0.0, 0.0], "p1": [-222.0, 0.0],
            "handle1": None, "handle2": None, "spline_points": 0,
            "length_mm": 574.3}],
 "sewings": [...]}
```

`kind` is `straight`, `bezier` or `spline`. `patterns.points()` carries the
coordinates, so a caller that only needs the topology does not pay for them.

### Crossing outlines while building

Every geometry write takes `allow_crossing=False`:

```python
qyapi.patterns.set_point("front", 2, [-20, 40])                        # refused: the outline would cross
qyapi.patterns.set_point("front", 2, [-20, 40], allow_crossing=True)   # applied for this call
```

With the flag on, that one call may leave an outline that crosses itself. The
answer says what happened: `outline_validity: "invalid"`, the `crossing` point,
and `mesh_stale: true` - because the mesh stage never samples a crossing outline,
so the pattern keeps the mesh it had (a pattern created crossing has none at all).
A simulation will not start while a participating pattern crosses. There is no
setting behind the flag: the next call refuses again, and the scene's own Check
Self-Intersection switch is not read or written by the surface.

A generator rebuild is not gated by the flag at all. A parameter change already
writes what the parameters describe, lets the mesh stage keep the previous mesh
where the outline crosses or is degenerate, and names what it left unusable:

```python
qyapi.generators.set_params("skirt", {"flare": 2.4})
# report: {..., "invalid_patterns": 1, "invalid_pattern_names": ["skirt_panel"],
#          "stale_meshes": ["skirt_panel"]}
```

## Placement

`qyapi.help("placement")` is this section.

The pattern window is a view onto the pattern's own 2D space, placed there by the
pattern's own transform: `pattern.anchor` (millimetres) and `pattern.rotation`.
That transform moves what the window draws - the outline, the points, the seam
preview - and nothing else.

The mesh is built from the pattern's own coordinates (its Sketch), so the mesh a
pattern gets when it is first generated sits where the pattern's own 2D position
puts it, with no view offset: at that moment the window and the scene agree. From
then on they are independent - `patterns.transform()` moves the window, and only
the mesh object's own transform moves the mesh.

The simulation runs a pattern's mesh object, so arranging a garment is arranging
those objects:

- the object's own transform is the placement - location, `rotation_euler` and
  `scale`. A mirror copy carries `scale.x = -1`. `object.matrix_world` is what
  the engine is handed, and what a viewer has to read to know where a panel is;
- the shape keys `QYBasis` (the rest pose) and `QYSim` (the simulated positions)
  are in that object's local space, and `sim.prepare()` hands the engine
  `QYSim`. Writing `QYSim` is therefore how a caller starts a run from a form the
  physics did not produce: put the panels where they belong, then let the solver
  begin there;
- give the seams room. The two panels a seam joins should start near each other
  but not on top of each other: the sewing pulls its sides together, and a
  garment that starts folded through itself stays folded;
- cloth that has to end up *on* a body has to start on it. The engine looks for
  contacts within a few millimetres, so a panel left in its own plane falls
  through the avatar instead of draping over it.

There is no measurement source and no automatic placement: a caller places the
panels from the pattern's own coordinates (the edges report their endpoints) or
from what the scene shows, and the judgement calls - which panel is the front,
which way a sleeve faces - are made by looking, or by asking the user.

What has to end up inside something has to start inside it. A sleeve's two
halves belong on tangent planes of the arm - one in front of it, one behind,
each clear of its surface by a fraction of the cloth's own thickness - so that
closing the sleeve's own two long seams wraps the tube around the arm. Laid in
the torso's own front and back planes instead, the tube closes beside the arm
and the sleeve is left hanging off the armhole.

A flat panel cannot be both "next to the other panel's edge" and "lying on the
body", and a sleeve is where the two pull apart: placed tangent to the arm, its
armhole edge starts several centimetres from the bodice's armhole edge, and
closing that seam moves the sleeve; placed beside that edge, the sleeve never
contains the arm. Decide which fit is being judged, place for it, and check by
looking before the seams are made.

Two of the arrangement's own traps:

- a half placed with a 180 degree turn about the vertical lands on the other
  side of the centre line, so the panel that sits on the left is that half's
  *mirror* copy. What each name is on is read from the pattern names, not from
  the side it appears on, and the seams have to be made on those same members;
- a seam is made once. Sewing the same pair of edges a second time is refused
  ("that seam was refused: Sewing overlap!!!"), so a script that re-runs a build
  reads the seams it already has instead of making them again.

Fabric thickness is the shell the cloth is given, and the shipped 0.1 mm leaves
contact no room: a sleeve or a bodice then reads as the body poking through it.
1 mm to 2 mm is what keeps a garment out of the body, and raising a contact
stiffness on its own does not replace it.

Two switches are worth the time before a seam is trusted:

- the 3D viewport panel's "Seams" switch (`scene.qmyi.view3d_seams`) draws a line
  between every paired stitch vertex of every seam, in the seam's own colour,
  from the evaluated pattern meshes - a mispaired side shows as a long line. It
  is rebuilt when the meshes or the objects move, so it follows a rebuild;
- Blender's own Face Orientation overlay tints back faces red, which says whether
  a panel ended up inside out. It is `space.overlay.show_face_orientation` on the
  viewport, and it is the one overlay worth turning *on* while a panel is judged
  - a screenshot carries it, so the picture itself can be the evidence;
- a screenshot taken through the viewport carries Blender's own overlays - the
  wireframe and the face-orientation colours - and not the add-on's, so the seam
  preview cannot be read off one. Turn the wireframe overlay off to judge the
  cloth's shape, and judge a seam in the window itself, where it is drawn.

## Sewings

| Call | Arguments | Returns |
| --- | --- | --- |
| `qyapi.sewings.list()` | - | every seam, both sides, colour, stitch count |
| `qyapi.sewings.of(pattern)` | pattern name | the seams that touch that pattern |
| `qyapi.sewings.sew(edge_a, edge_b, flip=False, color=None)` | each edge as `(pattern, index)` or `(pattern, label)` | the new seam |
| `qyapi.sewings.sew_at(pattern_a, edge_a, position_a, pattern_b, edge_b, position_b, color=None)` | a position 0..1 on each edge | the new seam |
| `qyapi.sewings.set_color(index, color)` | index, `[r, g, b]` | the seam |
| `qyapi.sewings.remove(index)` | index | what was removed |
| `qyapi.sewings.add_span(index, side, pattern, edge, end_edge=None, pos1=0.0, pos2=1.0, reverse=False)` | seam index, side 1 or 2, the pattern, both ends as an index or a label | the new mapping report |
| `qyapi.sewings.remove_span(index, side, span)` | seam index, side, run index | the new mapping report |
| `qyapi.sewings.move_span(index, side, span, offset)` | seam index, side, run index, how far to move it | the new mapping report |

Every seam read reports each side as its list of drawn runs, and carries
`stitch_count` and `stitch_error`. The two sides of a seam are not compared in
length: a seam whose sides differ still stitches, by progress along each side,
because that difference is the material the longer side gathers - a puff sleeve
into its armhole, a band onto an edge with ease. `stitch_error` is set only when
the two sides cannot be paired at all.

Both create calls go through the add-on's own click-based sewing: `sew` hands
over each edge's first point, or the second edge's second point when the flag is
on, and `sew_at` hands over the positions given. The direction is whatever that
sewing decides, so a seam here is the seam the editor makes for the same points.
A colour is used as given, otherwise a random saturated one.

## Generators

| Call | Arguments | Returns |
| --- | --- | --- |
| `qyapi.generators.list(project=None)` | - | every generator with parameters and patterns |
| `qyapi.generators.get(name)` | generator name | the parameter table, the slots and the patterns |
| `qyapi.generators.create(component_id, params=None, name=None)` | parameter map | the generator and the patterns it built |
| `qyapi.generators.set_params(name, params)` | parameter map | the rebuild report |
| `qyapi.generators.rebuild(name)` | - | the rebuild report |
| `qyapi.generators.detach(name)` | - | the patterns, now ordinary |
| `qyapi.generators.remove(name)` | - | the generator and its patterns |

`set_params` writes every parameter and rebuilds **once**, then reports what the
rebuild did: `in_place`, `rebuilt`, `created`, `removed`, `remapped`,
`dropped_spans`, `dropped_sewings`, `invalid_patterns`. `dropped_spans` counts
the drawn runs of a seam whose edge the rebuild could not match (the run goes,
the seam keeps the rest), and `dropped_sewings` counts the seams left with a side
holding no run, which the guard reports as incomplete. A parameter the component
does not declare is refused; a value outside its range is pulled back to the
nearest bound.

The report also carries `simulation_before` and `simulation_carried`: the mesh
stage interpolates a pattern's previous simulated positions onto the new mesh, so
after changing parameters of patterns that have been simulated, the positions come
with it and the result is usually off its rest pose. That is the case to settle
with a few simulation frames (`qyapi.sim.prepare()` then `qyapi.sim.step(n)`).

## Components

| Call | Arguments | Returns |
| --- | --- | --- |
| `qyapi.components.list()` | - | every component with its parameter schema |
| `qyapi.components.info(component_id)` | id | one component's entry |
| `qyapi.components.build(component_id, params=None)` | parameter map | the outlines, the edge labels and the outline check |
| `qyapi.components.reload()` | - | re-reads the user component folders |

`components.build()` changes nothing in the scene: it is the loop to use while
writing a component - build it, look at the outlines and the check, then put a
generator into the project with `generators.create()`.

## Simulation

| Call | Arguments | Returns |
| --- | --- | --- |
| `qyapi.sim.status()` | - | mode, prepared flag, engine binding, substeps, solver and last error |
| `qyapi.sim.prepare(solver=None, parameters=None, step_h=None)` | solver name (str), `{name: float}`, seconds per substep | summary: solver, its source, objects, vertices, triangles, sewings, stitches, `undo_step` |
| `qyapi.sim.step(frames=1, dt=None)` | engine substeps (int >= 1), seconds per substep | metrics for the call |
| `qyapi.sim.start()` | - | status after the timer-driven run starts |
| `qyapi.sim.stop()` | - | status after it stops |
| `qyapi.sim.read(patterns=None)` | one pattern name or a list | `{"objects": [{name, object, vertex_count, local, world, non_finite}]}` |
| `qyapi.sim.reset()` | - | how many objects went back to the rest pose |

The intended sequence is `prepare()` once, then `step()` as often as needed,
then `read()`. `prepare()` owns the order the engine needs: refresh identities,
test every outline, apply the solver parameters, build the payload (regenerating
a mesh whose granularity changed) and hand it to the engine. It is repeatable.

`solver` and `parameters` are the caller's values when given; otherwise the
scene's solver panel supplies them and the summary says so through
`solver_source` / `parameters_source`. Parameters passed by the caller win: a
pattern value cannot silently override them, including when `start()` is called
afterwards.

`step()` advances the engine on the calling thread and applies the result to the
pattern meshes before returning, so the number of engine substeps depends on the
argument and not on machine load. A live run and stepping exclude each other,
and whichever one is refused says which mode is active.

Metrics for a step call:

```python
{"substeps": 10, "frames": 20, "wall_time_s": 0.25,
 "total_wall_time_s": 0.46, "substeps_per_second": 40.6,
 "step_h_s": 0.0045, "mode": "prepared",
 "engine_statistics": {"residuals": {...}}}
```

`substeps` is what this call advanced, `frames` is the total since the session
was prepared (one engine update is one simulated frame of `step_h` seconds, the
number the patterns call a frame). `engine_statistics` carries what the engine
reports, unchanged; a statistic the engine does not offer is absent rather than
reported as zero.

Modes: `idle`, `prepared`, `stepping`, `live`, `failed`. A step that fails
leaves the session `failed` and needs a new `prepare()`: after an engine
exception its own state is not knowable from outside. `engine_bound` reports
that the manager holds an engine object, not that a run is ready - readiness is
`prepared`.

## The data model

`qyapi.help("objects")` prints this; the surface is smaller than the add-on, so
this is the part that covers what the calls do not.

```
PROJECT   one Blender node tree of type QianyiNodeTree (bpy.data.node_groups)
          .name, .patterns, .sewings, .fabrics, .generators

SKETCH    the drawn geometry of one instance chain, in the pattern's own space
          .vertices, .edges, .internal_lines
          One Sketch serves every member of a chain; patterns.detach() gives one
          pattern a Sketch of its own.

PATTERN   one pattern: its own identity and settings, and the derived data taken
          from the Sketch it reads
          .name, .sketch, .fabric, .granularity (mm), .collision_layer,
          .mesh_object, .anchor, .rotation, .grain_dir,
          .validity_state (unknown | valid | invalid)
          .anchor and .rotation place the pattern *in the pattern window*; the
          mesh does not follow them (see Placement)
    VERTEX         .co  (x, y)
    EDGE           .vertex_index (two indices), .handle1, .handle2,
                   .handle1_type, .handle2_type (VECTOR is a straight edge)
    INTERNAL LINE  .edges, .sketch, .is_hole (a cut inside the outline)

SEWING    one seam between two patterns
          .side1 and .side2, each a list of drawn runs on one pattern, in the
          order they were drawn: a run is a start edge and position, an end edge
          and position, and a reverse flag. The side's own record names the
          pattern it was made on: an edge serves its whole instance chain, so
          the record is what says which member a seam joins. Plus .color.

FABRIC    .weight (g/m^2), .thickness (mm), .friction, .stretch, .bending

OBJECT    one Blender mesh object; a pattern's mesh lives here
          .qmyi_simulation_props: participate_in_simulation, collision_layer,
          is_pattern_mesh, pattern, get_simulation_vertices()
          shape keys: QYBasis (rest pose), QYSim (simulated positions, local space)
          .matrix_world is where the simulation runs it, so a pattern's mesh
          object is the pattern's placement in the scene (see Placement)
```

### Reaching into Blender data directly

Permitted, but discouraged. It is the answer when a call is missing, and the
add-on cannot stop a script from doing it - but it bypasses two things:

* **The identity map.** `global_data.uuid2obj` is in memory only. Undo, redo and
  loading a file clear it, and it is what resolves a mesh back to its pattern
  and a sewing back to its edges. After a direct write - or after any undo -
  call a surface entry point (they all refresh it first) or
  `Qianyi.model.model_data.refresh_all_uuids()`. Skipping it gives
  `obj.global_uuid != uuid, -1062000418 != -945774949` and similar, and in this
  add-on that path ends in a crash rather than an exception.
  An identity that names nothing is reported, loudly, with the call stack that
  asked for it (`can not find uuid ...!`) - and the fix is always that whatever
  removed the element dropped it from the selection that named it
  (`QianyiProject.forget_selected`), never to silence the lookup.
* **Derived data.** A pattern's sections, mesh and sewing stitches are derived;
  editing vertices, edges or handles directly leaves them stale until the next
  `mark_geometry_changed()` / `generate_mesh()`, which `prepare()` runs for you.

### The two layers of a pattern's data

A pattern's data is in two layers, and a script that reads or writes geometry
should know which one it is touching:

* the **Sketch** holds what a pattern maker drew - vertices, edges with their
  handles and spline points, internal lines - and the first section stage built
  from them: one section per edge, cut where the curves cross. An instance chain
  shares **one** Sketch, so a copy and its source read the same geometry and
  cannot drift apart. `patterns.list()` / `patterns.get()` report the Sketch a
  pattern reads, and `patterns.detach(name)` gives one pattern a Sketch of its own;
* the **Pattern** holds the pattern's own identity and settings - name, placement,
  granularity, fabric, collision layer, simulation state, its mesh - and the
  derived data taken from the Sketch for *that* pattern: its own copy of the
  section stage, its samples, its mesh, and the walk its seams make.

A chain is what shares a Sketch, and nothing else: there is no list of members
to keep in step, `patterns.copy()` joins a chain by pointing the copy at the
source's Sketch, and `patterns.detach()` leaves it by giving that pattern a Sketch
of its own. A geometry edit therefore reaches the whole chain by itself.

Three rules follow from that:

* a write goes through the Sketch, and the **Sketch marks the patterns that read
  it**: one write reaches every member of the chain, and each member's outline
  state, its copy of the stage, its samples and its render line are marked with
  it (`Pattern.mark_geometry_changed`). Placement, granularity, fabric and
  collision layer are a pattern's own fields and mark nothing;
* a marked pattern rebuilds when the next reader needs it - the mesh path, the
  simulation prepare - and a topology edit meshes before it returns, for every
  pattern that reads the Sketch it wrote (`Sketch.rebuild_meshes`): the meshes
  are not shared, so a member left marked would draw the shape that used to be
  there. A seam edit only marks: the patterns it reaches resample and remesh when
  they are next needed. An outline that crosses itself is refused instead: the
  pattern keeps the mesh it had and records why in `mesh_error`;
* a reload or an undo leaves no session data behind, so the first reader of a
  reopened pattern builds its copy of the stage and its samples again. Nothing
  has to be trusted across a file.

An older file is **not converted** when it is opened: a pattern that names no
Sketch reports no geometry, a seam side that names no pattern has no side, and the
file has to be converted by hand.

What the editor draws follows the model: a topology edit marks the patterns that
read the Sketch, and the next draw rebuilds their lines, points and control
points. A tool that writes into a Sketch's collections itself sends the same
write signal, so a script that goes through the surface never has to ask for a
redraw of its own.

Deleting an element makes the wrappers of the following elements shift, so a
uuid read before a delete cannot be used after it - resolve again.

## Units

* A pattern's own 2D space is **millimetres**: a vertex coordinate, the
  granularity, and the tolerance the mesh stage uses are all in millimetres.
* Mesh objects, object space and world space are **metres**: the pattern's mesh
  is built with its points divided by 1000, so 1000 pattern units are 1 m. A
  550 mm pattern becomes a 0.55 m mesh.
* `pattern.granularity` is a ceiling on vertex spacing, not the resulting edge
  length: 5 mm gives a mesh of roughly 3.6 mm edges.
* Fabric thickness is millimetres; fabric weight is g/m².
* `pattern.rotation` and `pattern.grain_dir` are radians.
* `prepare(step_h=...)` and `step(dt=...)` are seconds per engine substep.

## Undo granularity

One write call leaves one undo step, labelled `Qianyi: <message>`. A read call
never touches the undo stack.

```python
with qyapi.transaction("build the front pattern"):
    ...                      # every write inside is one undo step
```

Nesting collapses; only the outermost block pushes, under its own message.
`push=False` leaves the undo stack alone entirely.

Inside a transaction, do not call an operator that carries the `UNDO` option -
every editing operator in this add-on does - because it pushes its own step and
splits the batch. That is why the surface calls the model layer, not operators.

A session with no window cannot undo at all: a write still applies and a
transaction is not an error there; `prepare()` simply reports `undo_step:
False`. Simulated positions are not an edit: `step()` and `reset()` push no
step.

## Deliberately not offered

* No entry point opens a menu, a popup or a file browser.
* No entry point writes component code or turns a parameter into a UI control;
  that is the next change. `components.build()` is what to use meanwhile.
* No m-to-n sewing: a seam joins one edge of one pattern to one edge of another.
* No measurement source: every parameter is a number the caller supplies.
* No automatic arrangement: nothing puts a garment on a body or lines two panels
  up for a seam. Placing the panels is the caller's job - see Placement for the
  two things that make it work (the mesh object's transform, and the shape key
  the run starts from) and for the switches that show whether it went wrong.
* No gesture tool: the pattern pen, the internal-line pen, the sewing tool, box
  select and the 3D pick are drawn interactions rather than calls with
  parameters, so nothing here opens one. That is also why the editor documents
  them as the exception to Blender's adjust-last-operation panel - a gesture has
  no number to adjust, while a geometry command (a division, a corner, a fan)
  shows its numbers there and can be re-run from them.
* No MCP protocol layer: this surface is plain Python for a client that already
  knows how to run a statement inside Blender.

## Worked example

A collar on a generated torso, starting from an empty file and settled after the
parameters change:

```python
import bpy, importlib                          # see "Loading it" above
qyapi = importlib.import_module(
    next(k for k in bpy.context.preferences.addons if k.endswith(".Qianyi"))
    + ".qyapi")

qyapi.projects.create("collar demo")                  # a blank file is enough

torso = qyapi.generators.create("gc_tee_torso", {"bust": 92.0, "shirt_length": 1.3})
front = torso["slots"][0]["pattern"]

collar = qyapi.patterns.create([[0, 0], [250, 0], [260, 45], [-50, 45]],
                               name="collar", granularity_mm=10)

# Building a shape may pass through an outline that crosses; say so per call,
# then fix it before anything is meshed or simulated.
qyapi.patterns.set_point("collar", 0, [-10, -10], allow_crossing=True)
qyapi.patterns.set_point("collar", 0, [0, 0])
qyapi.patterns.validate()                             # nothing crossing before a run

qyapi.sewings.sew(("collar", 2), (front, 0))          # and flip=True for the other pairing
qyapi.sewings.of("collar")                            # what is on it now

qyapi.sewings.add_span(0, 2, "collar", "hem")          # one edge to two short ones
qyapi.sewings.add_span(0, 2, "collar", "hem2")         #   -> one seam, two runs
qyapi.sewings.move_span(0, 2, 1, -1)                   # stitch them the other way round
qyapi.sewings.remove_span(0, 2, 0)                     # take the first run back off

qyapi.generators.set_params(torso["name"], {"bust": 108.0})
# -> report says in_place / dropped_sewings, and simulation_carried

qyapi.sim.prepare()                                   # optional: settle the new shape
qyapi.sim.step(60)
qyapi.sim.read("collar")                              # the positions afterwards
```
