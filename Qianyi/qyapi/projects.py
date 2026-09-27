"""Projects: make one, list them, choose the active one.

A project is a node tree of the add-on's own type. Creating one by hand is three
steps a caller cannot see - the tree, the identities of the project and of its
default fabric, and the name - and the second one only shows up as an assertion
inside the first pattern call. They live behind one call here.
"""

from __future__ import annotations

import bpy

from . import _address as address
from .errors import QyapiError
from ..declarations import Panels


def list():  # noqa: A001 - the surface's name for this call
    """Every project, with the name it is addressed by and its counts."""
    address.refresh()
    active = address.active_project()
    from ..utilities.node_tree import get_all_node_tree

    entries = [_entry(project) for project in get_all_node_tree()]  # loop: one dict each
    for entry in entries:  # loop: one comparison per project
        entry["active"] = active is not None and entry["name"] == active.name
    return address.jsonify({"projects": entries,
                            "active": None if active is None else active.name})


def active():
    """The project that calls without a project name work on."""
    address.refresh()
    project = address.active_project()
    if project is None:
        raise QyapiError("this scene has no project",
                         ("qyapi.projects.create() makes one",))
    return address.jsonify(_entry(project, active=True))


def create(name=None, activate=True):
    """Make a project that every other call can use straight away."""
    address.refresh()
    requested = str(name) if name else "Project"
    project = bpy.data.node_groups.new(requested, Panels.QianyiNodeTree)
    datablock = _datablock_key(project)
    # The identity of the project and of its default fabric: without both, the
    # first pattern call raises an assertion inside the fabric link.
    project.get_temp_data()
    project.get_default_fabric().get_temp_data()
    address.refresh()
    # The name the surface addresses and the project panel draws is the add-on's
    # own property; it starts empty on a tree a script made.
    project.name = datablock or requested
    if activate:
        _set_active(project)
    address.write_done(f"create project {project.name}")
    entry = _entry(project, active=activate)
    entry["requested_name"] = requested
    return address.jsonify(entry)


def activate(name):
    """Make a project the one that calls without a name work on."""
    project = address.project_or_refuse(name)
    _set_active(project)
    address.write_done(f"activate project {project.name}")
    return address.jsonify(_entry(project, active=True))


def rename(name, new_name):
    """Rename a project; the old name stops resolving."""
    project = address.project_or_refuse(name)
    new_name = str(new_name)
    if not new_name:
        raise QyapiError("a project needs a name")
    if new_name != name and _by_name(new_name) is not None:
        raise QyapiError(f"a project named {new_name!r} already exists",
                         ("names address projects, so they have to be unique",))
    previous = project.name
    project.name = new_name
    address.write_done(f"rename project {previous} to {new_name}")
    return address.jsonify(_entry(project, active=address.active_project() is project))


def remove(name):
    """Remove a project and report what went with it."""
    from ..utilities.node_tree import get_all_node_tree
    from ..model.model_data import refresh_all_uuids

    project = address.project_or_refuse(name)
    removed = _entry(project)
    was_active = address.active_project() is project
    # A pattern's mesh object is a scene object, not part of the node tree, so
    # removing the tree alone would leave objects whose pattern is gone - and
    # every walk over the simulated objects then fails on that dangling link.
    # Taking the patterns out through the model layer deletes their meshes.
    if len(project.patterns) > 0:
        project.remove_patterns([pattern for pattern in project.patterns],
                                expand_groups=False)
    bpy.data.node_groups.remove(project)
    refresh_all_uuids()
    if was_active:
        remaining = get_all_node_tree()
        if remaining:
            _set_active(remaining[0])
    address.write_done(f"remove project {removed['name']}")
    removed["removed"] = True
    removed["projects_left"] = len(get_all_node_tree())
    return address.jsonify(removed)


def fabrics(project=None):
    """Every fabric of the project, with the properties the solver reads.

    ``patterns.fabrics()`` answers with the same list as names; this one carries
    what the engine is handed: weight (g/m^2), thickness (mm), friction, and the
    planar stretch and bending triples.
    """
    project = address.project_or_refuse(project)
    return address.jsonify({"project": project.name,
                            "fabrics": [_fabric_entry(project, fabric)
                                        for fabric in project.fabrics]})


def fabric(name, project=None):
    """One fabric by name: its properties and the patterns that wear it."""
    project = address.project_or_refuse(project)
    fabric = address.fabric_or_refuse(project, name)
    return address.jsonify(_fabric_entry(project, fabric))


def set_fabric(name, weight=None, thickness=None, friction=None, stretch=None,
               bending=None, color=None, project=None):
    """Change a fabric's properties; the ones left out keep their value.

    A fabric is what the engine reads per pattern. ``thickness`` is the shell
    the cloth is given, in millimetres, and ``friction`` its contact
    coefficient: those two are what a garment that slides down or pokes through
    the body is tuned with. ``weight`` is g/m^2, ``stretch`` and ``bending`` are
    the (u, v, shear) triples the solver scales its stiffnesses by, and
    ``color`` is the pattern editor's fill - it never reaches the engine.
    """
    project = address.project_or_refuse(project)
    fabric = address.fabric_or_refuse(project, name)
    changed = {}
    if weight is not None:
        changed["weight"] = _positive(weight, "weight")
    if thickness is not None:
        changed["thickness"] = _not_negative(thickness, "thickness")
    if friction is not None:
        changed["friction"] = _not_negative(friction, "friction")
    if stretch is not None:
        changed["stretch"] = _triple(stretch, "stretch")
    if bending is not None:
        changed["bending"] = _triple(bending, "bending")
    if color is not None:
        changed["color"] = _color(color)
    if not changed:
        raise QyapiError("no property to set",
                         ("give at least one of weight, thickness, friction, "
                          "stretch, bending, color",
                          "projects.fabric(name) reads the values it has now"))
    for key, value in changed.items():  # loop: one assignment per property given
        setattr(fabric, key, value)
    address.write_done(f"change fabric {fabric.name}")
    entry = _fabric_entry(project, fabric)
    entry["action"] = "set_fabric"
    entry["changed"] = changed
    return address.jsonify(entry)


# --- internals -------------------------------------------------------------

def _number(value, what):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise QyapiError(f"{what} must be a number, got {value!r}")


def _positive(value, what):
    number = _number(value, what)
    if not number > 0:
        raise QyapiError(f"{what} must be positive, got {number}")
    return number


def _not_negative(value, what):
    number = _number(value, what)
    if number < 0:
        raise QyapiError(f"{what} must not be negative, got {number}")
    return number


def _triple(value, what):
    try:
        values = [float(item) for item in value]
    except (TypeError, ValueError):
        raise QyapiError(f"{what} must be three numbers, got {value!r}")
    if len(values) != 3:
        raise QyapiError(f"{what} must be three numbers, got {len(values)}")
    if any(item < 0 for item in values):
        raise QyapiError(f"{what} must not be negative")
    return values


def _color(value):
    values = _triple(value, "color")
    if any(item > 1 for item in values):
        raise QyapiError("color components run 0..1")
    return values


def _fabric_entry(project, fabric):
    """One fabric's properties, plus the patterns that name it.

    The link is the pattern's own ``fabric_uuid``; ``pattern.fabric`` assigns
    the default fabric when a pattern has none, so a read must not go through it.
    """
    from .. import global_data

    patterns = []
    for pattern in project.patterns:  # loop: one identity lookup per pattern
        uuid = int(pattern.fabric_uuid)
        if uuid == -1:
            continue
        try:
            linked = global_data.get_obj_by_uuid(uuid)
        except Exception:
            continue
        if linked is fabric:
            patterns.append(pattern.name)
    return {
        "name": fabric.name,
        "weight": float(fabric.weight),
        "thickness": float(fabric.thickness),
        "friction": float(fabric.friction),
        "stretch": [float(value) for value in fabric.stretch],
        "bending": [float(value) for value in fabric.bending],
        "color": [float(value) for value in fabric.color],
        "patterns": patterns,
    }


def _entry(project, active=None):
    if active is None:
        current = address.active_project()
        active = current is not None and current == project
    return {
        "name": project.name,
        "datablock": _datablock_key(project),
        "active": bool(active),
        "patterns": len(project.patterns),
        "sewings": len(project.sewings),
        "fabrics": len(project.fabrics),
        "generators": len(project.generators),
    }


def _datablock_key(project):
    """The node tree's own key, for a caller that has to find it in bpy.data.

    Not an address: the add-on's name property shadows the datablock name, so
    this is the only way to say what the tree is filed under.
    """
    for key, value in bpy.data.node_groups.items():  # loop: one key per tree
        if value == project:
            return key
    return None


def _by_name(name):
    from ..utilities.node_tree import get_all_node_tree

    for project in get_all_node_tree():  # loop: one comparison per project
        if project.name == name:
            return project
    return None


def _set_active(project):
    scene = getattr(bpy.context, "scene", None)
    if scene is None or getattr(scene, "qmyi", None) is None:
        raise QyapiError("this session has no scene to activate a project in")
    index = [position for position, group in enumerate(bpy.data.node_groups)
             if group == project]
    if not index:
        raise QyapiError("that project is not in this file any more")
    scene.qmyi.active_project_index = index[0]
