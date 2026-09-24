"""Script surface of the Qianyi add-on (``qyapi``).

Import this module in a Blender session that has the add-on registered::

    import qyapi                     # any session, viewport or -b
    print(qyapi.help())              # the entry-point index
    print(qyapi.state())             # JSON-safe snapshot of the scene

If the add-on is loaded but not registered yet, import it from the add-on
package instead (``from Qianyi import qyapi`` for an installed add-on,
``from qmyi import qyapi`` when a study notebook loaded the package by path).
Both names resolve to the same module once the add-on is registered.

Rules this surface follows
--------------------------

* Every entry point works with no viewport, no operator, no modal handler and
  no menu, and returns plain JSON-safe data (no Blender object, no numpy array).
* Projects and patterns are addressed by name. A call resolves the names from
  the scene data when it starts, so it works after an undo, a redo or a file
  load, which all clear the add-on's in-memory identity map.
* A write call leaves exactly one undo step, labelled with the caller's intent.
  ``qyapi.transaction`` collapses the writes inside it into one step. Read calls
  never touch the undo stack, and a session that has no window simply gets no
  undo step rather than an error.
* A call that cannot do its work raises ``qyapi.QyapiError`` and changes
  nothing; it never reports success silently and never opens a dialog.

Entry points
------------

Discovery: ``help(topic)``, ``state()``.
Undo: ``transaction(message, push=True)``.
Projects: ``qyapi.projects.list()``, ``active()``, ``create()``, ``activate()``,
``rename()``, ``remove()``.
Panels: ``qyapi.patterns.list()``, ``get()``, ``points()``, ``create()``,
``set_point()``, ``add_point()``, ``remove_point()``, ``set_handle()``,
``add_spline_point()``, ``remove_spline_point()``, ``add_internal_line()``,
``remove_internal_line()``, ``transform()``, ``copy()``, ``detach()``,
``remove()``, ``validate()``, ``fabrics()``, ``assign_fabric()``.
Sewings: ``qyapi.sewings.list()``, ``of()``, ``sew()``, ``sew_at()``,
``set_color()``, ``remove()``.
Generators: ``qyapi.generators.list()``, ``get()``, ``create()``,
``set_params()``, ``rebuild()``, ``detach()``, ``remove()``.
Components: ``qyapi.components.list()``, ``info()``, ``build()``, ``reload()``.
Simulation: ``qyapi.sim.status()``, ``prepare()``, ``step(frames)``,
``start()``, ``stop()``, ``read(patterns)``, ``reset()``.

``qyapi.help("objects")`` prints the data model, ``qyapi.help("panels")`` the
rules for naming, copies and generated panels, ``qyapi.help("units")`` the
units, ``qyapi.help("undo")`` the undo rules and ``qyapi.help("not-offered")``
what this surface deliberately does not do. The same text ships as
``docs/agent-api.md`` in the repository; the two are meant to agree.

The data model, and what to do when a call is missing
-----------------------------------------------------

The surface is smaller than the add-on. When something has no entry point here,
reading and writing Blender data directly is permitted but discouraged: it
bypasses the identity map and the derived data below. If you do it, call any
surface entry point afterwards (they all refresh identities first), or
``Qianyi.model.model_data.refresh_all_uuids()`` directly. ``qyapi.help("objects")``
lists the objects and their fields.
"""

from __future__ import annotations

import sys

import bpy
import numpy as np

from . import _address
from . import components
from . import generators
from . import patterns
from . import projects
from . import sewings
from . import sim
from .errors import QyapiError
from .. import global_data
from ..model.model_data import refresh_all_uuids
from ..utilities.node_tree import get_all_node_tree

VERSION = 1

_ENTRY_POINTS = (
    ("help(topic=None)", "text index, or one topic: objects, panels, units, undo, not-offered",
     "topic: a topic name (str)"),
    ("state()", "JSON-safe snapshot: projects, patterns, outline validity, simulation state",
     "no arguments"),
    ("transaction(message, push=True)", "context manager; the writes inside it become one undo step",
     "message: undo label (str), push: bool"),
    ("projects.list()", "every project with the name it is addressed by and its counts",
     "no arguments"),
    ("projects.active()", "the project that calls without a project name work on",
     "no arguments"),
    ("projects.create(name=None, activate=True)",
     "make a project that is usable straight away, identities and name included",
     "name: str, activate: bool"),
    ("projects.activate(name)", "make a project the active one", "name: str"),
    ("projects.rename(name, new_name)", "rename a project; the old name stops resolving",
     "new_name: str"),
    ("projects.remove(name)", "remove a project and report what went with it",
     "name: str"),
    ("patterns.list(project=None)", "every panel with its counts, fabric and chain",
     "project: name (str, optional)"),
    ("patterns.get(name)", "one panel: summary, edge table and the sewings on it",
     "name: panel name (str)"),
    ("patterns.points(name)", "the outline vertices, in millimetres",
     "name: panel name (str)"),
    ("patterns.create(points, name=None, granularity_mm=None, fabric=None)",
     "a closed counter-clockwise panel from points in millimetres",
     "points: [[x, y], ...] (mm), granularity_mm: float, fabric: name (str)"),
    ("patterns.set_point(name, index, xy)", "move one vertex",
     "index: vertex index (int), xy: [x, y] (mm)"),
    ("patterns.add_point(name, edge, xy)", "split one straight edge with a new vertex",
     "edge: index (int) or label (str), xy: [x, y] (mm)"),
    ("patterns.remove_point(name, index)", "remove a vertex and merge the edges that met there",
     "index: vertex index (int)"),
    ("patterns.set_handle(name, edge, which, xy=None, type=None)",
     "set one edge handle's position and/or type",
     "which: 1 or 2 (int), xy: [x, y] (mm), type: VECTOR | FREE | ALIGNED"),
    ("patterns.add_spline_point(name, edge, xy)", "add an interpolating control point",
     "edge: index (int) or label (str), xy: [x, y] (mm)"),
    ("patterns.remove_spline_point(name, edge, index)", "remove one control point",
     "index: control point index (int)"),
    ("patterns.add_internal_line(name, points, is_hole=False, closed=False)",
     "add a cut from a polyline inside the outline",
     "points: [[x, y], ...] (mm), is_hole: bool, closed: bool"),
    ("patterns.remove_internal_line(name, index)", "remove a cut and its control points",
     "index: internal line index (int)"),
    ("patterns.transform(name, anchor=None, rotation=None, grain_dir=None, collision_layer=None, mirror=None)",
     "place the panel: anchor, angles, collision layer, mirror",
     "anchor: [x, y] (mm), rotation/grain_dir: radians, mirror: bool"),
    ("patterns.copy(name, mirror=False, anchor=None)",
     "copy the panel as an instance or a mirror",
     "mirror: bool, anchor: [x, y] (mm)"),
    ("patterns.detach(name)",
     "give one panel a Sketch of its own; the other members stay linked",
     "no arguments"),
    ("patterns.remove(names)", "remove panels; a generated panel is refused here",
     "names: one name or a list (str | list)"),
    ("patterns.validate(names=None)", "test the outlines now and report the crossing ones",
     "names: one name or a list (str | list, optional)"),
    ("patterns.fabrics()", "the project's fabrics, by name", "no arguments"),
    ("patterns.assign_fabric(name, fabric)", "give a panel a fabric",
     "fabric: name (str)"),
    ("sewings.list()", "every seam with both sides, colour and stitch count",
     "no arguments"),
    ("sewings.of(pattern)", "the seams that touch one panel",
     "pattern: panel name (str)"),
    ("sewings.sew(edge_a, edge_b, side1_reverse=False, side2_reverse=True, color=None)",
     "stitch two edges with the add-on's own one-to-one sewing",
     "edge: (panel, index) or (panel, label), color: [r, g, b]"),
    ("sewings.sew_at(pattern_a, edge_a, position_a, pattern_b, edge_b, position_b, color=None)",
     "stitch two edges from a position on each, the way a click would",
     "position: 0..1 (float)"),
    ("sewings.set_color(index, color)", "recolour one seam",
     "index: seam index (int), color: [r, g, b]"),
    ("sewings.remove(index)", "remove one seam", "index: seam index (int)"),
    ("generators.list(project=None)", "every generator with its parameters and panels",
     "project: name (str, optional)"),
    ("generators.get(name)", "one generator, its parameter table and its panels",
     "name: generator name (str)"),
    ("generators.create(component_id, params=None, name=None)",
     "add a generator for a component and build its panels",
     "params: name -> value (dict), name: generator name (str)"),
    ("generators.set_params(name, params)", "set several parameters, rebuild once, report",
     "params: name -> value (dict)"),
    ("generators.rebuild(name)", "rebuild with the parameters it already has",
     "no arguments"),
    ("generators.detach(name)", "turn its panels into ordinary panels",
     "no arguments"),
    ("generators.remove(name)", "remove the generator and the panels it owns",
     "no arguments"),
    ("components.list()", "every component the library offers, with its schema",
     "no arguments"),
    ("components.info(component_id)", "one component's entry",
     "component_id: id (str)"),
    ("components.build(component_id, params=None)",
     "build a component and return its outlines; the scene is untouched",
     "params: name -> value (dict)"),
    ("components.reload()", "re-read the user component folders",
     "no arguments"),
    ("sim.status()", "mode, prepared flag, engine binding, substeps, solver and last error",
     "no arguments"),
    ("sim.prepare(solver=None, parameters=None, step_h=None)",
     "validate the outlines, apply solver parameters, build the payload and bind the engine",
     "solver: name (str), parameters: name -> float (dict), step_h: seconds (float)"),
    ("sim.step(frames=1, dt=None)", "advance the engine synchronously and return metrics",
     "frames: engine substeps (int >= 1), dt: seconds per substep (float)"),
    ("sim.start()", "start the timer-driven run a human watches",
     "no arguments"),
    ("sim.stop()", "stop that run", "no arguments"),
    ("sim.read(patterns=None)", "simulated vertex positions, local and world, as plain lists",
     "patterns: one name or a list of names (str | list)"),
    ("sim.reset()", "discard the simulated positions and go back to the rest pose",
     "no arguments"),
)

_PANELS = """\
Names.  A panel is addressed by name. Creating one with a taken name gives it a
suffixed name (collar -> collar.001) and the answer reports both.

Copies.  patterns.copy() links the copy into the same instance list as its
source, and a geometry edit is written to every member of that list at the same
index. A copy holds the same local geometry; a mirror is expressed by the
panel's matrix and its mesh scale, so editing a panel that has a mirror copy
edits both. patterns.get()["chain"] lists the members.

Generated panels.  A panel a generator owns reports "generated": true. Its
geometry can be edited here like any other, but a later set_params or rebuild
rewrites it, and the rebuild carries the previous simulated positions over by
interpolation. Removing it through patterns.remove() is refused, because the
add-on deletes a generated panel's whole group: use generators.detach() to keep
the panels, or generators.remove() to drop the group.

Reading.  patterns.get() answers "which edges does this panel have and which
seams are on them" - edge indexes, labels, kinds, endpoints, handles, lengths,
and both sides of every seam. The coordinates are a separate call,
patterns.points(), because a component with a thousand edges makes one response
large.

Edges.  panel.edges[i] is straight, bezier or spline. A new point can only split
a straight edge: make the edge straight first, or move one of its ends.

Crossing.  Every geometry write takes allow_crossing=False. With it on, that one
call may leave an outline that crosses itself; the answer says so (validity,
crossing point, mesh_stale) and the panel's mesh is then stale, because the mesh
stage never samples a crossing outline and a simulation will not start on one.
There is no setting behind it: the next call refuses again. A generator rebuild
is not gated by it at all - a parameter change already writes what it writes and
names the panels it left invalid or degenerate.
"""

_OBJECT_MODEL = """\
PROJECT   one Blender node tree of type QianyiNodeTree (bpy.data.node_groups)
          .name, .patterns, .sewings, .fabrics, .generators
          reached from qyapi.state(), or by scanning bpy.data.node_groups

SKETCH    the drawn geometry of one instance chain, in the panel's own space
          .vertices, .edges, .internal_lines
          One Sketch serves every member of a chain; patterns.detach() gives one
          panel a Sketch of its own.

PATTERN   one panel: its own identity and settings, and the derived data taken
          from the Sketch it reads
          .name, .sketch, .fabric, .granularity (mm), .collision_layer,
          .mesh_object, .anchor, .rotation, .grain_dir,
          .validity_state (unknown | valid | invalid)
    VERTEX         .co  (x, y)
    EDGE           .vertex_index (two indices), .handle1, .handle2,
                   .handle1_type, .handle2_type (VECTOR is a straight edge)
    INTERNAL LINE  .edges, .sketch, .is_hole (a cut inside the outline)

SEWING    one seam between two pattern edges
          .side1 and .side2, each a (edge, position on that edge in 0..1) pair
          with a reverse flag, plus .color and .get_stitch_data()

FABRIC    .weight (g/m^2), .thickness (mm), .friction, .stretch, .bending

OBJECT    one Blender mesh object; a panel's mesh lives here
          .qmyi_simulation_props: participate_in_simulation, collision_layer,
          is_pattern_mesh, pattern, get_simulation_vertices()
          shape keys: QYBasis (rest pose), QYSim (simulated positions, local space)
"""

_UNITS = """\
A pattern's own 2D space is millimetres (a vertex coordinate is a millimetre),
including pattern.granularity and the geometric tolerance the mesh stage uses.
Mesh objects, object space and world space are metres: the pattern's mesh is
built with its points divided by 1000, so 1 pattern unit is 1 mm and 1000 units
are 1 m. Fabric thickness is millimetres; fabric weight is g/m^2.
pattern.rotation and pattern.grain_dir are radians.
sim.prepare(step_h=...) and sim.step(dt=...) are seconds per engine substep.
"""

_UNDO = """\
One write call leaves one undo step, labelled "Qianyi: <message>".
A read call never touches the undo stack.
with qyapi.transaction("build the skirt"):   # every write inside is one step
    ...
Inside a transaction, do not call an operator that carries the UNDO option
(every editing operator of this add-on does): it pushes its own step and splits
the batch in two.
A session with no window cannot undo at all; a write still applies, and a
transaction is not an error there.
Simulated positions are not an edit: sim.step() and sim.reset() push no step.
"""

_NOT_OFFERED = """\
No entry point opens a menu, a popup or a file browser.
No entry point writes component code or exposes a parameter as a UI control:
that is the next change. components.build() is what to use meanwhile - it turns
a parameter block into outlines without touching the scene.
No m-to-n sewing: a seam joins one edge of one panel to one edge of another.
No measurement source: every parameter is a number the caller supplies.
No MCP protocol layer: this surface is plain Python, written for a client that
already knows how to run a statement inside Blender.
"""

_TOPIC_TEXT = {
    "objects": _OBJECT_MODEL,
    "panels": _PANELS,
    "units": _UNITS,
    "undo": _UNDO,
    "not-offered": _NOT_OFFERED,
}


def help(topic=None):  # noqa: A001 - the name is the point: qyapi.help()
    """The entry-point index, or one topic of text.

    A client that can only run Python finds the whole surface from here, so the
    index carries the arguments and their units and the topics carry the parts
    of the contract that are not a call (the data model, the units, the undo
    rules).
    """
    if topic is None:
        lines = ["qyapi - script surface of the Qianyi add-on", "",
                 "Every call is JSON-safe and works with or without a viewport.", ""]
        for name, purpose, arguments in _ENTRY_POINTS:
            lines.append(f"  qyapi.{name}")
            lines.append(f"      {purpose}")
            lines.append(f"      arguments: {arguments}")
        lines += ["", "topics: " + ", ".join(sorted(_TOPIC_TEXT)),
                  "  qyapi.help(\"<topic>\")"]
        return "\n".join(lines)
    key = str(topic).strip().lower()
    if key in _TOPIC_TEXT:
        return _TOPIC_TEXT[key]
    raise QyapiError(f"no help topic named {topic!r}",
                     (f"known topics: {', '.join(sorted(_TOPIC_TEXT))}",
                      "call qyapi.help() for the entry-point index"))


def _jsonify(value):
    """Plain data out: no Blender object and no numpy array leaves the surface."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonify(item) for item in value]
    to_list = getattr(value, "to_list", None)
    if callable(to_list):
        return _jsonify(to_list())
    try:
        return [_jsonify(item) for item in value]
    except TypeError:
        # Last resort for a type this surface does not produce. Returning a
        # string keeps the result serialisable; it is not a usable handle.
        return str(value)


def _scene():
    return getattr(bpy.context, "scene", None)


def _active_project_name():
    scene = _scene()
    qmyi = getattr(scene, "qmyi", None)
    if qmyi is None:
        return None
    index = int(qmyi.active_project_index)
    groups = bpy.data.node_groups
    if 0 <= index < len(groups):
        return groups[index].name
    return None


def _fabric_name(pattern):
    """The fabric's name, read without triggering the property that writes.

    ``Pattern.fabric`` assigns the default fabric when the pattern has none, so
    a snapshot must not call it: a read is not allowed to change the scene.
    """
    return _address.fabric_name(pattern)


def _pattern_state(pattern, position):
    mesh = pattern.mesh_object
    return {
        "name": pattern.name,
        "index": position,
        "vertices": len(pattern.vertices),
        "edges": len(pattern.edges),
        "internal_lines": len(pattern.internal_lines),
        "granularity_mm": float(pattern.granularity),
        "collision_layer": int(pattern.collision_layer),
        "fabric": _fabric_name(pattern),
        "mesh_object": mesh.name if mesh is not None else None,
        # The cached answer only: a snapshot never runs the outline test.
        "outline_validity": str(pattern.validity_state).lower(),
        "generated": int(pattern.generator_uuid) != -1,
    }


def _project_state(project):
    patterns = []
    # Loop over the collection: one summary dict per pattern is per-object work
    # on Blender data, which numpy cannot do.
    for position, pattern in enumerate(project.patterns):
        patterns.append(_pattern_state(pattern, position))
    return {
        "name": project.name,
        "pattern_count": len(project.patterns),
        "sewing_count": len(project.sewings),
        "fabric_count": len(project.fabrics),
        "generator_count": len(project.generators),
        "patterns": patterns,
    }


def state():
    """A JSON-safe snapshot of the scene, for a caller that starts cold.

    Reading this changes no data. ``outline_validity`` is the cached answer:
    ``unknown`` means the outline has not been tested since it was last edited,
    which is not the same as valid - the mesh and the simulation always test
    before they use an outline.
    """
    refresh_all_uuids()
    scene = _scene()
    projects = []
    # Loop over the node groups: one summary dict per project, per-object work.
    for project in get_all_node_tree():
        projects.append(_project_state(project))
    return _jsonify({
        "surface": {
            "module": __name__,
            "version": VERSION,
            "background": bool(bpy.app.background),
        },
        "scene": {
            "name": getattr(scene, "name", None),
            "file": bpy.data.filepath or None,
            "frame": getattr(scene, "frame_current", None),
        },
        "active_project": _active_project_name(),
        "projects": projects,
        "simulation": sim.status(),
    })


def push_undo(message):
    """Record one undo step labelled ``Qianyi: <message>``.

    Returns False when the session has no undo stack to push onto (a background
    session, or global undo switched off) - that is not an error, a script keeps
    working there.
    """
    if bpy.app.background:
        # Measured in a background session: undo itself is refused there
        # ("Operator bpy.ops.ed.undo.poll() failed, context is incorrect"), so
        # claiming a step was recorded would be a lie. The write still applies.
        return False
    preferences = getattr(bpy.context, "preferences", None)
    edit = getattr(preferences, "edit", None)
    if edit is not None and not edit.use_global_undo:
        return False
    try:
        bpy.ops.ed.undo_push(message=f"Qianyi: {message}")
        return True
    except Exception:
        return False


class transaction:
    """Group the writes inside the block into a single undo step.

        with qyapi.transaction("build the front panel"):
            ...

    Nesting collapses: only the outermost block pushes, under its own message.
    ``push=False`` leaves the undo stack alone entirely. Nothing here changes
    how a write behaves in a session that cannot undo.
    """

    _depth = 0

    def __init__(self, message, push=True):
        self.message = message
        self.push = push

    def __enter__(self):
        transaction._depth += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        transaction._depth -= 1
        if transaction._depth == 0 and self.push and exc_type is None:
            push_undo(self.message)
        return False


def end_write(message):
    """Close one write call: one undo step, unless a transaction owns the batch."""
    if transaction._depth > 0:
        return False
    return push_undo(message)


def register():
    """Publish this package under the name ``qyapi``.

    The add-on package is called ``Qianyi`` when installed and something else
    when a study notebook loaded it by path, so a client cannot be asked to
    guess the import path. Registering the module under this name makes
    ``import qyapi`` work in every session that registered the add-on.
    """
    sys.modules["qyapi"] = sys.modules[__name__]
    # The submodules are published under the same name too: without this,
    # ``from qyapi.errors import QyapiError`` would load a second copy of the
    # module, with its own exception class, and ``except QyapiError`` would miss
    # the error the surface raised.
    for name in ("errors", "_address", "sim", "patterns", "sewings", "generators",
                 "components", "projects"):
        submodule = sys.modules.get(f"{__name__}.{name}")
        if submodule is not None:
            sys.modules[f"qyapi.{name}"] = submodule


def unregister():
    if sys.modules.get("qyapi") is not sys.modules.get(__name__):
        return
    for name in ("qyapi.errors", "qyapi._address", "qyapi.sim", "qyapi.patterns",
                 "qyapi.sewings", "qyapi.generators", "qyapi.components",
                 "qyapi.projects"):
        submodule = sys.modules.get(name)
        if submodule is not None and getattr(submodule, "__name__", "").startswith(__name__):
            del sys.modules[name]
    del sys.modules["qyapi"]
