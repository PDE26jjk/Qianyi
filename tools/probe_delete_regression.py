"""Reproduce "delete a point or an edge" failing with a uuid mismatch.

    blender.exe -b --factory-startup <scene.blend> --python tools/probe_delete_regression.py [-- --neutralize]

The failure under test:

    Exception: obj.global_uuid != uuid, -1062000418 != -945774949
    raised from  _2d_elements_delete.execute -> Pattern.forced_update
                -> update_connected_pattern_sewing_state
                -> get_connected_patterns_and_sewings -> Sewing.pattern1
                -> global_data.get_obj_by_uuid

`--neutralize` turns the outline-validity hooks added for the self-intersection
work into no-ops (the behaviour before that change). A failure that happens in
both runs is not caused by those hooks.
"""

import contextlib
import importlib.util
import os
import sys
import traceback

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")
NEUTRALIZE = "--neutralize" in sys.argv
CASE = "sewn"
for argument in sys.argv:
    if argument.startswith("--case="):
        CASE = argument.split("=", 1)[1]


def log(message):
    print(f"[delete] {message}", flush=True)


# --- the viewport is not there in a background session ----------------------


class FakeBatch:
    def draw(self, *args, **kwargs):
        pass


class FakeShader:
    def bind(self):
        pass

    def uniform_float(self, *args, **kwargs):
        pass

    def uniform_block(self, *args, **kwargs):
        pass


class FakeUniformBuf:
    def __init__(self, *args, **kwargs):
        pass

    def update(self, *args, **kwargs):
        pass


class FakeGpuState:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class FakeGpuMatrix:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def install_gpu_stubs():
    import gpu
    import gpu_extras.batch

    gpu_extras.batch.batch_for_shader = lambda *args, **kwargs: FakeBatch()
    gpu.shader.create_from_info = lambda *args, **kwargs: FakeShader()
    gpu.shader.from_builtin = lambda *args, **kwargs: FakeShader()
    gpu.types.GPUUniformBuf = FakeUniformBuf
    gpu.state = FakeGpuState()
    gpu.matrix = FakeGpuMatrix()


class FakeArea:
    def tag_redraw(self):
        pass


class FakeWindowManager:
    def popup_menu(self, *args, **kwargs):
        pass


class FakeSpace:
    def __init__(self, node_tree):
        self.node_tree = node_tree


class FakeContext:
    def __init__(self, node_tree):
        self.scene = bpy.context.scene
        self.area = FakeArea()
        self.window_manager = FakeWindowManager()
        self.space_data = FakeSpace(node_tree)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def report_uuid_state(project, label):
    from qmyi import global_data
    from qmyi.model.pattern_instance import collect_unique_instances

    lines = []
    for index, sewing in enumerate(project.sewings):
        side = sewing.side1
        uuid = side.line1_uuid
        target = global_data.uuid2obj.get(uuid)
        current = None
        if target is not None:
            with contextlib.suppress(Exception):
                current = target.global_uuid
        lines.append(f"sewing[{index}].side1.line1 uuid={uuid} mapped_to={current}")
    log(f"{label}: {len(lines)} sewing(s)")
    for line in lines:
        log("    " + line)


def sewn_line_uuids(project):
    uuids = set()
    for sewing in project.sewings:
        for side in (sewing.side1, sewing.side2):
            uuids.add(side.line1_uuid)
            uuids.add(side.line2_uuid)
    return uuids


def pick_target(project, want_sewn=True):
    """A vertex whose edges are (or are not) referenced by a sewing."""
    sewn = sewn_line_uuids(project)
    for pattern_index, pattern in enumerate(project.patterns):
        for edge in pattern.edges:
            is_sewn = edge.global_uuid in sewn
            if is_sewn != want_sewn:
                continue
            log(f"    target: pattern[{pattern_index}] edge {edge.global_uuid} "
                f"vertex0 {edge.vertex0.global_uuid} "
                f"({'sewn' if is_sewn else 'free'})")
            return pattern, edge.vertex0
    return None, None


def remove_sewings_on(project, pattern, vertex):
    """Drop the sewings that reference an edge of `vertex`, before the delete."""
    uuids = set()
    for edge in pattern.edges:
        if vertex.global_uuid in (edge.vertex0.global_uuid, edge.vertex1.global_uuid):
            uuids.add(edge.global_uuid)
    indexes = []
    for sewing in project.sewings:
        sides = (sewing.side1, sewing.side2)
        if any(side.line1_uuid in uuids or side.line2_uuid in uuids for side in sides):
            indexes.append(sewing.get_index())
    for index in sorted(indexes, reverse=True):
        project.sewings.remove(index)
    project.refresh_collection_uuid(project.sewings)
    log(f"    removed {len(indexes)} sewing(s) before deleting")
    return len(indexes)


def pick_both_sides(project):
    """One vertex on each side of the first sewing, to delete in one go."""
    from qmyi import global_data

    sewing = project.sewings[0]
    targets = []
    for side in (sewing.side1, sewing.side2):
        line = global_data.get_obj_by_uuid(side.line1_uuid)
        log(f"    target: {line.pattern.name} edge {line.global_uuid} "
            f"vertex0 {line.vertex0.global_uuid}")
        targets.append((line.pattern, line.vertex0))
    return targets


def main():
    install_gpu_stubs()
    import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data, model
    from qmyi.model import model_data
    from qmyi.model.pattern import Pattern
    from qmyi.operators._2d_elements_delete import NODE_OT_elements_delete
    from qmyi.gizmos.temp_draw_manager import TempDrawManager
    from qmyi.utilities.node_tree import get_all_node_tree

    model.register()
    model_data.refresh_all_uuids()
    # The draw handler owns this in a UI session; the operator only uses it as a
    # scratch pad for the preview curves.
    global_data.temp_draw_manager = TempDrawManager()
    if NEUTRALIZE:
        # What the code did before the self-intersection work.
        Pattern.mark_shape_changed = lambda self: None
        Pattern.validate = lambda self, force=False: "VALID"
        Pattern.is_invalid = property(lambda self: False)
        log("outline-validity hooks are neutralized")

    project = get_all_node_tree()[0]
    log(f"scene={bpy.context.scene.name} patterns={len(project.patterns)} "
        f"sewings={len(project.sewings)}")
    report_uuid_state(project, "before")

    if CASE == "both":
        targets = pick_both_sides(project)
    else:
        pattern, vertex = pick_target(project, want_sewn=CASE != "free")
        if pattern is None:
            log(f"no {'sewn' if CASE != 'free' else 'free'} edge to delete")
            return 1
        if CASE == "nosewing":
            remove_sewings_on(project, pattern, vertex)
        targets = [(pattern, vertex)]

    context = FakeContext(project)
    context.scene.qmyi.edit_mode = "EDGE"
    context.scene.qmyi.edit_sub_mode = "EDGE_VERTEX"
    project.selected_edges.clear()
    project.selected_vertices.clear()
    for pattern, vertex in targets:
        pattern.impacted = True
        selection = project.selected_vertices.add()
        selection.uuid = vertex.global_uuid
    log(f"selected {len(targets)} vertex/vertices")

    try:
        # The operator's own instance is made by Blender, which a background
        # session has no way to do; the body only uses `context`, so a dummy
        # self runs exactly the same code.
        result = NODE_OT_elements_delete.execute(object(), context)
        log(f"execute returned {result}")
    except Exception as error:
        log(f"execute raised: {type(error).__name__}: {error}")
        traceback.print_exc()
        report_uuid_state(project, "after the failure")
        return 1
    log(f"deleted, patterns={len(project.patterns)} sewings={len(project.sewings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
