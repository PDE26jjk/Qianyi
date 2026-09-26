import random
import re

from bpy.props import IntProperty, StringProperty, BoolProperty

from ..utilities.console import console_print
from .. import global_data


def extract_last_bracket_number(text):
    match = re.search(r'\[(\d+)\](?!.*\[)', text)
    if match:
        return int(match.group(1))
    return None


class ModelData:
    """Defines temporary data that can be used in the current session and will not be saved in file."""
    name: StringProperty(name="name", )
    global_idx: IntProperty(
        name="global idx", default=-1, options={"HIDDEN"}
    )
    global_uuid: IntProperty(
        name="global uuid", default=-1, options={"HIDDEN"}
    )

    def get_temp_data(self) -> dict:
        temp_data = global_data.temp_data
        if 0 <= self.global_idx < len(temp_data):
            data = temp_data[self.global_idx]
            if "uuid" in data and data["uuid"] == self.global_uuid:
                return data

        temp_data.append({})
        self.global_idx = len(temp_data) - 1
        data = temp_data[self.global_idx]
        if self.global_uuid == -1 or self.global_uuid == 255 or (
                self.global_uuid in global_data.uuid2obj and global_data.uuid2obj[self.global_uuid] != self):
            self.global_uuid = random.randint(-2_147_483_647, 2_147_483_647)
            # console_print("new global uuid ", self.global_uuid)
            while self.global_uuid in global_data.uuid2obj:
                self.global_uuid = random.randint(-2_147_483_647, 2_147_483_647)
        global_data.uuid2obj[self.global_uuid] = self
        data["uuid"] = self.global_uuid
        return data

    def get_temp_data_item(self, name: str, default=None):
        temp_data = self.get_temp_data()
        if name not in temp_data:
            if callable(default):
                default = default()
            temp_data[name] = default
        return temp_data[name]

    def set_temp_data_item(self, name: str, value):
        temp_data = self.get_temp_data()
        temp_data[name] = value

    def clear_temp_data(self):
        pass

    @classmethod
    def refresh_collection_uuid(cls, coll):
        """Put every item of one collection into the identity map.

        An item that has no identity yet is left out: its `global_uuid` is the
        unset value -1, and mapping that would leave `-1` answering with whatever
        object happened to be added last. A lookup of `-1` then reads a wrapper
        whose identity does not match, and the caller sees a warning and None
        instead of some other object.
        """
        for obj in coll:
            if obj.global_uuid == -1:
                continue
            global_data.uuid2obj[obj.global_uuid] = obj

    def try_regain_self(self):
        pass

    def get_index(self):
        return extract_last_bracket_number(self.path_from_id())

    def get_parent(self):
        return self.id_data.path_resolve(self.path_from_id().rsplit('.', 1)[0])


def register_uuid(obj):
    """Map one model object, skipping the ones that never got an identity.

    Returns 1 when the object went into the map, 0 otherwise.
    """
    if obj.global_uuid == -1:
        return 0
    global_data.uuid2obj[obj.global_uuid] = obj
    return 1


def _register_edge(edge):
    """An edge owns its control handles, its spline points and its samples.

    A pattern's own copy of the samples it meshed with lives on the pattern (see
    `Pattern.geo_points`); it is a read-only mirror, so it is deliberately not
    part of the identity map a pick or a lookup walks.
    """
    count = register_uuid(edge)
    for vertex in edge.handles:
        count += register_uuid(vertex)
    for vertex in edge.spline_points:
        count += register_uuid(vertex)
    return count


def refresh_all_uuids():
    """Rebuild the whole uuid -> model object map.

    `global_data.uuid2obj` is an in-memory map that is empty in a session that
    just opened a file (and after undo/redo, which clears it). Everything that
    resolves a uuid - a mesh looking up its pattern, a pattern looking up its
    fabric, a sewing side looking up its edge - fails until the map is filled,
    and it used to be filled only as a side effect of the UI drawing a pattern.
    Walking the projects explicitly makes the data path independent of that.

    Returns the number of objects registered.
    """
    from ..utilities.node_tree import get_all_node_tree

    count = 0
    for project in get_all_node_tree():
        count += register_uuid(project)
        for fabric in project.fabrics:
            count += register_uuid(fabric)
        for sewing in project.sewings:
            count += register_uuid(sewing)
        # The geometry is the Sketches': a pattern reads it through the Sketch it
        # names, so registering the patterns' elements here would register the
        # same objects twice - and would ask a pattern for a Sketch before the
        # Sketch has an identity.
        for sketch in project.sketches:
            count += register_uuid(sketch)
            for vertex in sketch.vertices:
                count += register_uuid(vertex)
            for edge in sketch.edges:
                count += _register_edge(edge)
            for line in sketch.internal_lines:
                count += register_uuid(line)
                for edge in line.edges:
                    count += _register_edge(edge)
        for pattern in project.patterns:
            count += register_uuid(pattern)
    return count


def define_temp_prop(cls, name, default=None):
    @property
    def func(self):
        return self.get_temp_data_item(name, default)

    setattr(cls, name, func)

    @func.setter
    def setter(self, value):
        self.set_temp_data_item(name, value)

    setattr(cls, name, setter)


def resolve_sketch(element):
    """The Sketch a geometry element is stored in, or None.

    A point, an edge, a control point and an internal line all live in a Sketch,
    and never anywhere else: an edge is shared by every member of its instance
    chain, so the pattern is not what holds it. The element's own path says which
    Sketch - its first segment is "sketches[3]" for a point, for an edge of the
    outline, for a control point and for an edge of an internal line alike - so
    the answer is that one collection entry.

    The answer is kept on the element because a redraw asks for it dozens of
    times, and it is checked against the uuid it was resolved from: a wrapper a
    removal left behind reads back as a default (uuid -1) or as whatever item
    shifted onto it, and neither may pass for the Sketch the element lives in.
    """
    cached = element.sketch_temp
    if cached is not None:
        try:
            if cached.global_uuid == element.sketch_uuid:
                return cached
        except Exception:
            pass
        element.sketch_temp = None
        element.sketch_uuid = -1
    try:
        path = element.path_from_id()
    except Exception:
        # A wrapper the collection retired when another item was added: it can
        # no longer read its own path, and the map holds the wrapper that is in
        # the collection now. A wrapper of something that was removed answers
        # None - there is no Sketch left to name.
        live = global_data.get_obj_by_uuid(int(element.global_uuid), check_uuid=False)
        if live is not None and live != element:
            return live.sketch
        return None
    segments = re.findall(r'(\w+)\[(-?\d+)\]', path)
    if not segments or segments[0][0] != "sketches":
        return None
    sketches = getattr(element.id_data, "sketches", None)
    index = int(segments[0][1])
    if sketches is None or not 0 <= index < len(sketches):
        return None
    sketch = sketches[index]
    element.sketch_temp = sketch
    element.sketch_uuid = sketch.global_uuid
    return sketch


def owner_pattern(element):
    """The pattern that owns the Sketch an element lives in, or None.

    A geometry element - a point, an edge, a control point, an internal line -
    is stored in a Sketch, and a Sketch belongs to the pattern that made it, which
    is the first member of the instance chain. The element has no pattern of its
    own: an edge is shared by every member of its chain. A caller that holds
    only the element and needs the pattern asks here, and this answers the one
    thing it can answer - the owner of the Sketch - rather than letting the
    element pretend to be a pattern.

    `Sketch.owner` resolves the pattern through the uuid map, which already
    answers None for a pattern that is no longer there, so nothing here has to
    re-check the wrapper.
    """
    sketch = getattr(element, "sketch", None)
    if sketch is None:
        return None
    return sketch.owner


class Selectable:
    is_selected: BoolProperty(
        name="isSelected", default=False,
    )

