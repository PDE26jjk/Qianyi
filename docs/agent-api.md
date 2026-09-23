# Qianyi agent API (`qyapi`)

The add-on exposes a small script surface so an agent that can run a Python
statement inside Blender can drive the simulation without knowing the add-on's
internals. This file mirrors what the module itself documents: a client that can
only run Python can read the same text with `print(qyapi.help())` and
`qyapi.help("<topic>")`.

## Loading it

```python
import qyapi                      # any session where the add-on is registered
```

`import qyapi` works with a viewport and in a background (`-b`) session. If the
add-on is loaded but not registered yet, import the module from the add-on
package instead (`from Qianyi import qyapi` when installed, `from qmyi import
qyapi` when a study notebook loaded the package by path). Both names resolve to
the same module once the add-on is registered, submodules included.

## Discovery

| Call | Returns |
| --- | --- |
| `qyapi.help()` | the entry-point index: name, purpose, arguments and their units |
| `qyapi.help(topic)` | one topic: `objects`, `units`, `undo`, `not-offered` |
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

A project is addressed by the add-on's own name, which is also the name the
editor's Project panel draws. Creating one by hand is three steps a caller cannot
see - the node tree, the identities of the project and of its default fabric, and
the name - and the middle one only shows up as an assertion inside the first
panel call. `projects.create()` does all of it, so this works from a blank file:

```python
import qyapi

qyapi.projects.create("my project")               # identities, name and active index
panel = qyapi.patterns.create([[0, 0], [100, 0], [100, 80], [0, 80]],
                              name="front", granularity_mm=10)
qyapi.projects.rename("my project", "skirt")
qyapi.projects.list()                             # [{name, datablock, active, patterns, ...}]
```

`datablock` is the node tree's own key, reported for a caller that has to find
the tree in `bpy.data`; it is not an address.

## Panels

Panel space is millimetres throughout - a vertex, an anchor, a handle.

| Call | Arguments | Returns |
| --- | --- | --- |
| `qyapi.patterns.list(project=None)` | - | every panel: counts, fabric, mesh, validity, chain |
| `qyapi.patterns.get(name)` | panel name | summary + edge table + the sewings on that panel |
| `qyapi.patterns.points(name)` | panel name | the outline vertices, in millimetres |
| `qyapi.patterns.create(points, name=None, granularity_mm=None, fabric=None)` | `[[x, y], ...]` (mm) | the new panel, with the name it got |
| `qyapi.patterns.set_point(name, index, xy)` | vertex index, `[x, y]` | the edited panel |
| `qyapi.patterns.add_point(name, edge, xy)` | edge index or label, `[x, y]` | splits one straight edge |
| `qyapi.patterns.remove_point(name, index)` | vertex index | merges the two edges that met there |
| `qyapi.patterns.set_handle(name, edge, which, xy=None, type=None)` | 1 or 2, `[x, y]`, `VECTOR`/`FREE`/`ALIGNED` | the edited panel |
| `qyapi.patterns.add_spline_point(name, edge, xy)` | edge, `[x, y]` | makes the edge interpolate through it |
| `qyapi.patterns.remove_spline_point(name, edge, index)` | edge, index | |
| `qyapi.patterns.add_internal_line(name, points, is_hole=False, closed=False)` | `[[x, y], ...]` (mm) | adds a cut |
| `qyapi.patterns.remove_internal_line(name, index)` | index | |
| `qyapi.patterns.transform(name, anchor=None, rotation=None, grain_dir=None, collision_layer=None, mirror=None)` | anchor in mm, angles in radians | places the panel |
| `qyapi.patterns.copy(name, mirror=False, anchor=None)` | anchor in mm | the copy, linked into the same instance chain |
| `qyapi.patterns.remove(names)` | one name or a list | what went, and the sewings dropped with it |
| `qyapi.patterns.validate(names=None)` | - | the panels whose outline crosses itself |
| `qyapi.patterns.fabrics()` | - | the project's fabric names |
| `qyapi.patterns.assign_fabric(name, fabric)` | fabric name | the panel |

An outline is always a closed, counter-clockwise loop: `create` closes it, and
there is no open-panel form. A name that is taken gets a suffix
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
so the panel keeps the mesh it had (a panel created crossing has none at all).
A simulation will not start while a participating panel crosses. There is no
setting behind the flag: the next call refuses again, and the scene's own Check
Self-Intersection switch is not read or written by the surface.

A generator rebuild is not gated by the flag at all. A parameter change already
writes what the parameters describe, lets the mesh stage keep the previous mesh
where the outline crosses or is degenerate, and names what it left unusable:

```python
qyapi.generators.set_params("skirt", {"flare": 2.4})
# report: {..., "invalid_panels": 1, "invalid_panel_names": ["skirt_panel"],
#          "stale_meshes": ["skirt_panel"]}
```

## Sewings

| Call | Arguments | Returns |
| --- | --- | --- |
| `qyapi.sewings.list()` | - | every seam, both sides, colour, stitch count |
| `qyapi.sewings.of(pattern)` | panel name | the seams that touch that panel |
| `qyapi.sewings.sew(edge_a, edge_b, flip=False, color=None)` | each edge as `(panel, index)` or `(panel, label)` | the new seam |
| `qyapi.sewings.sew_at(pattern_a, edge_a, position_a, pattern_b, edge_b, position_b, color=None)` | a position 0..1 on each edge | the new seam |
| `qyapi.sewings.set_color(index, color)` | index, `[r, g, b]` | the seam |
| `qyapi.sewings.remove(index)` | index | what was removed |

Both create calls go through the add-on's own click-based sewing: `sew` hands
over each edge's first point, or the second edge's second point when the flag is
on, and `sew_at` hands over the positions given. The direction is whatever that
sewing decides, so a seam here is the seam the editor makes for the same points.
A colour is used as given, otherwise a random saturated one.

## Generators

| Call | Arguments | Returns |
| --- | --- | --- |
| `qyapi.generators.list(project=None)` | - | every generator with parameters and panels |
| `qyapi.generators.get(name)` | generator name | the parameter table, the slots and the panels |
| `qyapi.generators.create(component_id, params=None, name=None)` | parameter map | the generator and the panels it built |
| `qyapi.generators.set_params(name, params)` | parameter map | the rebuild report |
| `qyapi.generators.rebuild(name)` | - | the rebuild report |
| `qyapi.generators.detach(name)` | - | the panels, now ordinary |
| `qyapi.generators.remove(name)` | - | the generator and its panels |

`set_params` writes every parameter and rebuilds **once**, then reports what the
rebuild did: `in_place`, `rebuilt`, `created`, `removed`, `remapped`,
`dropped_sewings`, `invalid_panels`. A parameter the component does not declare
is refused; a value outside its range is pulled back to the nearest bound.

The report also carries `simulation_before` and `simulation_carried`: the mesh
stage interpolates a panel's previous simulated positions onto the new mesh, so
after changing parameters of panels that have been simulated, the positions come
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
panel value cannot silently override them, including when `start()` is called
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
number the panels call a frame). `engine_statistics` carries what the engine
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

PATTERN   one 2D outline in its own space, in metres
          .name, .vertices, .edges, .internal_lines, .fabric, .granularity (mm),
          .collision_layer, .mesh_object, .anchor, .rotation, .grain_dir,
          .validity_state (unknown | valid | invalid)
    VERTEX         .co  (x, y)
    EDGE           .vertex_index (two indices), .handle1, .handle2,
                   .handle1_type, .handle2_type (VECTOR is a straight edge)
    INTERNAL LINE  .edges, .pattern (a cut inside the outline)

SEWING    one seam between two pattern edges
          .side1 and .side2, each a (edge, position on that edge in 0..1) pair
          with a reverse flag, plus .color and .get_stitch_data()

FABRIC    .weight (g/m^2), .thickness (mm), .friction, .stretch, .bending

OBJECT    one Blender mesh object; a panel's mesh lives here
          .qmyi_simulation_props: participate_in_simulation, collision_layer,
          is_pattern_mesh, pattern, get_simulation_vertices()
          shape keys: QYBasis (rest pose), QYSim (simulated positions, local space)
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
* **Derived data.** A pattern's sections, mesh and sewing stitches are derived;
  editing vertices, edges or handles directly leaves them stale until the next
  `forced_update()` / `generate_mesh()`, which `prepare()` runs for you.

Deleting an element makes the wrappers of the following elements shift, so a
uuid read before a delete cannot be used after it - resolve again.

## Units

* A pattern's own 2D space is **millimetres**: a vertex coordinate, the
  granularity, and the tolerance the mesh stage uses are all in millimetres.
* Mesh objects, object space and world space are **metres**: the pattern's mesh
  is built with its points divided by 1000, so 1000 pattern units are 1 m. A
  550 mm panel becomes a 0.55 m mesh.
* `pattern.granularity` is a ceiling on vertex spacing, not the resulting edge
  length: 5 mm gives a mesh of roughly 3.6 mm edges.
* Fabric thickness is millimetres; fabric weight is g/m².
* `pattern.rotation` and `pattern.grain_dir` are radians.
* `prepare(step_h=...)` and `step(dt=...)` are seconds per engine substep.

## Undo granularity

One write call leaves one undo step, labelled `Qianyi: <message>`. A read call
never touches the undo stack.

```python
with qyapi.transaction("build the front panel"):
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
* No m-to-n sewing: a seam joins one edge of one panel to one edge of another.
* No measurement source: every parameter is a number the caller supplies.
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
import qyapi

qyapi.projects.create("collar demo")                  # a blank file is enough

torso = qyapi.generators.create("gc_tee_torso", {"bust": 92.0, "shirt_length": 1.3})
front = torso["slots"][0]["panel"]

collar = qyapi.patterns.create([[0, 0], [250, 0], [260, 45], [-50, 45]],
                               name="collar", granularity_mm=10)

# Building a shape may pass through an outline that crosses; say so per call,
# then fix it before anything is meshed or simulated.
qyapi.patterns.set_point("collar", 0, [-10, -10], allow_crossing=True)
qyapi.patterns.set_point("collar", 0, [0, 0])
qyapi.patterns.validate()                             # nothing crossing before a run

qyapi.sewings.sew(("collar", 2), (front, 0))          # and flip=True for the other pairing
qyapi.sewings.of("collar")                            # what is on it now

qyapi.generators.set_params(torso["name"], {"bust": 108.0})
# -> report says in_place / dropped_sewings, and simulation_carried

qyapi.sim.prepare()                                   # optional: settle the new shape
qyapi.sim.step(60)
qyapi.sim.read("collar")                              # the positions afterwards
```
