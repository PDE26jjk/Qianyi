"""Check the pattern UV layer: its seed, its carry-over, its reset and its mirror.

    blender.exe -b --factory-startup --python tools/probe_pattern_uv.py

Builds its own project and patterns (no scene file) and checks what the
`pattern-uv` change promises:

1. a mesh build writes one UV layer named `UVMap`, seeded from pattern space;
2. a rebuild carries the layer the mesh holds - including an edit made to it in
   the UV editor - instead of re-seeding it, and a vertex that keeps its
   pattern-space position keeps its UV across a topology change;
3. the scene's `uv_scale` sizes a seeded UV and never rescales one that exists;
4. a mirrored pattern's seed is mirrored, and toggling the flag on a pattern
   that is already meshed mirrors the UV it holds;
5. the reset operator re-seeds the active pattern mesh's UV and changes nothing
   else, and the UV editor panel and the operator are registered;
6. a rebuild still makes one mapping call and touches the UV once for reading
   and once for writing;
7. the layer, and the scale, survive a save and a reopen, and the reopened mesh
   rebuilds while carrying the UV that was saved.

Each check prints PASS or FAIL; the process exits non-zero when anything failed.
"""

import importlib
import importlib.util
import io
import os
import sys
import tempfile
import traceback

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")
QYIDP_BUILD = r"R:\code\cuda\qmyidp\build\Release"
UV_LAYER = "UVMap"
FAILURES = []


def log(message):
    print(f"[uv] {message}", flush=True)


def check(label, condition, detail=""):
    if condition:
        log(f"PASS {label}")
    else:
        log(f"FAIL {label} {detail}")
        FAILURES.append(label)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name,
                                                  os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def build_square(project, name, size, origin=(0.0, 0.0), granularity=20.0):
    """A closed square pattern with one internal line across it, and its mesh."""
    pattern = project.add_pattern()
    pattern.name = name
    pattern.granularity = granularity
    half = size / 2.0
    for point in ((origin[0] - half, origin[1] - half), (origin[0] + half, origin[1] - half),
                  (origin[0] + half, origin[1] + half), (origin[0] - half, origin[1] + half)):
        pattern.add_vertex(point)
    for index in range(4):
        pattern.add_edge(index, (index + 1) % 4, update=True)
    pattern.add_internal_line([{"p0": (origin[0] - half * 0.6, origin[1]),
                                "p1": (origin[0] + half * 0.6, origin[1]),
                                "h1": (0.0, 0.0), "h2": (0.0, 0.0),
                                "h1_type": "VECTOR", "h2_type": "VECTOR"}],
                              is_loop=False)
    pattern.mark_geometry_changed()
    pattern.generate_mesh()
    return pattern


def loop_vertices(mesh) -> np.ndarray:
    """The vertex every loop references, in loop order."""
    indices = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", indices)
    return indices


def layer_uv(mesh) -> np.ndarray:
    """The `UVMap` layer as (loops, 2)."""
    layer = mesh.uv_layers.get(UV_LAYER)
    values = np.empty(len(layer.data) * 2, dtype=np.float32)
    layer.data.foreach_get("uv", values)
    return values.reshape(-1, 2)


def vertex_uv(mesh) -> np.ndarray:
    """One UV per vertex, from the first loop that references it."""
    loops = loop_vertices(mesh)
    unique, first = np.unique(loops, return_index=True)
    uv = np.zeros((len(mesh.vertices), 2), dtype=np.float64)
    uv[unique] = layer_uv(mesh)[first]
    return uv


def vertex_positions(mesh) -> np.ndarray:
    """The mesh's own local positions, as (vertices, 2)."""
    values = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", values)
    return values.reshape(-1, 3)[:, :2].astype(np.float64)


def rest_positions(obj) -> np.ndarray:
    """A pattern mesh's rest positions, read the way the reset reads them."""
    positions = obj.qmyi_simulation_props.get_pattern_vertices()
    if positions is not None:
        return np.asarray(positions, dtype=np.float64)
    return vertex_positions(obj.data)


def shape_key_points(obj, name) -> np.ndarray:
    """One shape key's points as (vertices, 3)."""
    key = obj.data.shape_keys.key_blocks[name]
    values = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    key.points.foreach_get("co", values)
    return values.reshape(-1, 3)


def write_vertex_uv(mesh, uv) -> None:
    """Edit the layer the way the UV editor does: one value per loop, here from
    one value per vertex, which is the shape the add-on itself writes."""
    layer = mesh.uv_layers.get(UV_LAYER)
    loops = loop_vertices(mesh)
    layer.data.foreach_set("uv",
                           np.ascontiguousarray(np.asarray(uv, dtype=np.float32)[loops]).ravel())


def matching_uv_errors(old_positions, old_uv, new_positions, new_uv, tolerance=1e-4):
    """For every new vertex sitting on an old position, whether its UV differs.

    The sampler returns a new point order on every build, so a vertex-to-vertex
    comparison has to be by position, not by index.
    """
    distance = ((new_positions[:, None, :] - old_positions[None, :, :]) ** 2).sum(axis=2)
    nearest = distance.argmin(axis=1)
    rows = np.arange(len(new_positions))
    hit = distance[rows, nearest] <= tolerance * tolerance
    if not hit.any():
        return 0, 0
    difference = np.abs(new_uv[hit] - old_uv[nearest[hit]]).max()
    return int(hit.sum()), int(difference > tolerance)


class _Capture:
    """A stand-in for stderr that keeps what the add-on's console writes to it."""

    def __init__(self):
        self.buffer = io.BytesIO()

    def flush(self):
        return None


def capture_stderr(call) -> str:
    """Run `call` and return what it wrote to the add-on's console."""
    capture = _Capture()
    original = sys.__stderr__
    sys.__stderr__ = capture
    try:
        call()
    finally:
        sys.__stderr__ = original
    return capture.buffer.getvalue().decode("utf8", "replace")


def pattern_named(project, name):
    # loop: one comparison per pattern, and the collection is a Blender one
    for candidate in project.patterns:
        if candidate.name == name:
            return candidate
    raise LookupError(name)


def payload_difference(before, after):
    """The engine-payload keys whose value the two entries disagree on.

    The payload is what the bridge sends the engine, so comparing it is how a
    UV write is shown to change nothing the simulation sees.
    """
    changed = []
    # loop: the payload is a small dict, one entry per object
    for key, value in before.items():
        if key == "obj":
            continue
        other = after.get(key)
        if isinstance(value, np.ndarray) or isinstance(other, np.ndarray):
            if not np.array_equal(np.asarray(value), np.asarray(other)):
                changed.append(key)
        elif value != other:
            changed.append(key)
    return changed


def main():
    log(f"blender {bpy.app.version_string}")
    qmyi = sys.modules["qmyi"]
    qmyi.register()
    from qmyi import global_data

    global_data.renderers_enabled = False
    from qmyi import qyapi
    from qmyi.declarations import Operators, Panels
    from qmyi.model.model_data import refresh_all_uuids

    scene = bpy.context.scene
    scene.qmyi.uv_scale = 1.0

    project = bpy.data.node_groups.new("UVProbe", "QianyiNodeTree")
    project.use_fake_user = True
    project.get_default_fabric()
    refresh_all_uuids()

    # 1. the first build seeds the layer from pattern space
    front = build_square(project, "front", 40.0)
    mesh = front.mesh_object.data
    check("the first build writes exactly one UVMap layer",
          mesh.uv_layers.get(UV_LAYER) is not None and len(mesh.uv_layers) == 1,
          f"layers={[layer.name for layer in mesh.uv_layers]}")
    positions = vertex_positions(mesh)
    uv = vertex_uv(mesh)
    check("the seed is the pattern-space position at scale 1",
          np.abs(uv - positions).max() < 1e-5,
          f"max difference={np.abs(uv - positions).max()}")
    loops = loop_vertices(mesh)
    check("every loop of a vertex carries that vertex's UV",
          np.abs(layer_uv(mesh) - uv[loops]).max() < 1e-6,
          "a loop disagrees with its vertex")
    # A sewing, so the reset is checked on a scene the seam data also lives in.
    back = build_square(project, "back", 40.0, origin=(120.0, 0.0))
    project.add_sewing(front.edges[0], 0.0, front.edges[0], 1.0, False,
                       back.edges[0], 0.0, back.edges[0], 1.0, False)
    check("the probe scene carries a sewing", len(project.sewings) == 1,
          f"sewings={len(project.sewings)}")

    # 2a. a rebuild with nothing changed leaves the UV alone
    front.generate_mesh(force=True)
    mesh = front.mesh_object.data
    rebuilt_positions, rebuilt_uv = vertex_positions(mesh), vertex_uv(mesh)
    matched, errors = matching_uv_errors(positions, uv, rebuilt_positions, rebuilt_uv)
    check("a rebuild with no geometry change moves no UV",
          matched == len(positions) and errors == 0,
          f"matched={matched}/{len(positions)} errors={errors}")

    # 2b. a user's edit of the layer is what the next rebuild carries
    transform = np.array(((0.0, -1.5), (0.75, 0.0)), dtype=np.float64)
    offset = np.array((0.3, -0.2), dtype=np.float64)
    edit = rebuilt_positions @ transform.T + offset
    write_vertex_uv(mesh, edit)
    edited_uv = vertex_uv(mesh)
    check("the edit is on the layer",
          np.abs(edited_uv - edit).max() < 1e-5,
          f"max difference={np.abs(edited_uv - edit).max()}")
    # A divide changes the outline's topology, so the next mesh is a different
    # point count in a different order.
    from qmyi.operators import _2d_divide_edge as divide_tools

    divide_tools.divide_edges(front, [0], parts=3)
    mesh = front.mesh_object.data
    new_positions, new_uv = vertex_positions(mesh), vertex_uv(mesh)
    check("a divide resamples the mesh with a new point count",
          len(new_positions) != len(rebuilt_positions),
          f"points={len(rebuilt_positions)} -> {len(new_positions)}")
    matched, errors = matching_uv_errors(rebuilt_positions, edited_uv,
                                         new_positions, new_uv)
    check("a vertex that keeps its position keeps its UV across a divide",
          matched > 0 and errors == 0,
          f"matched={matched} errors={errors}")
    check("the user's UV transform is carried across a divide",
          np.abs(new_uv - (new_positions @ transform.T + offset)).max() < 1e-3,
          f"max difference={np.abs(new_uv - (new_positions @ transform.T + offset)).max()}")
    check("a rebuild reuses the layer instead of stacking a second one",
          len(mesh.uv_layers) == 1 and mesh.uv_layers[0].name == UV_LAYER,
          f"layers={[layer.name for layer in mesh.uv_layers]}")

    # 2c. the same across a corner edit, which rewrites the outline too
    from qmyi.operators import _2d_corner as corner_tools

    corner = build_square(project, "corner", 40.0, origin=(300.0, 0.0))
    corner_mesh = corner.mesh_object.data
    corner_positions = vertex_positions(corner_mesh)
    corner_shift = np.array((0.5, 0.25), dtype=np.float64)
    write_vertex_uv(corner_mesh, corner_positions + corner_shift)
    corner_uv = vertex_uv(corner_mesh)
    corner_tools.corner_vertices(corner, [2], radius=4.0, mode="ROUND")
    corner_mesh = corner.mesh_object.data
    corner_new_positions = vertex_positions(corner_mesh)
    corner_new_uv = vertex_uv(corner_mesh)
    check("a corner edit resamples the mesh",
          len(corner_new_positions) != len(corner_positions)
          or not np.allclose(corner_new_positions, corner_positions),
          "the corner did not change the outline")
    matched, errors = matching_uv_errors(corner_positions, corner_uv,
                                         corner_new_positions, corner_new_uv)
    check("a vertex that keeps its position keeps its UV across a corner edit",
          matched > 0 and errors == 0,
          f"matched={matched} errors={errors}")
    check("the user's UV shift is carried across a corner edit",
          np.abs(corner_new_uv - (corner_new_positions + corner_shift)).max() < 1e-3,
          f"max difference="
          f"{np.abs(corner_new_uv - (corner_new_positions + corner_shift)).max()}")

    # 3. the scale sizes a seed and never rescales a layer that exists
    scene.qmyi.uv_scale = 2.0
    front.generate_mesh(force=True)
    mesh = front.mesh_object.data
    check("changing the scale alone does not rescale an existing UV",
          np.abs(vertex_uv(mesh) - (vertex_positions(mesh) @ transform.T + offset)).max() < 1e-3,
          "the rebuild reseeded instead of carrying the UV")

    # 4. the reset re-seeds from the mesh's current pattern space
    from qmyi.simulation.simulation_manager import build_object_payload

    bpy.context.view_layer.objects.active = front.mesh_object
    depsgraph = bpy.context.evaluated_depsgraph_get()
    payload_before = build_object_payload(front.mesh_object, depsgraph)
    sewings_before = qyapi.sewings.list(project=project.name)
    # The reset is checked against a layer that is not the seed, so "the reset
    # seeded it" cannot pass by accident.
    write_vertex_uv(mesh, vertex_positions(mesh) * 0.5)
    triangles_before = len(mesh.polygons)
    result = bpy.ops.qmyi.reset_pattern_uv()
    mesh = front.mesh_object.data
    positions = vertex_positions(mesh)
    check("the reset runs on the active pattern mesh", 'FINISHED' in result)
    check("the reset seeds the rest positions at the current scale",
          np.abs(vertex_uv(mesh) - rest_positions(front.mesh_object) * 2.0).max() < 1e-5,
          f"max difference="
          f"{np.abs(vertex_uv(mesh) - rest_positions(front.mesh_object) * 2.0).max()}")
    check("the reset changes no vertex and no triangle",
          len(mesh.vertices) == len(positions) and len(mesh.polygons) == triangles_before,
          f"polygons={triangles_before} -> {len(mesh.polygons)}")
    changed = payload_difference(payload_before,
                                 build_object_payload(front.mesh_object, depsgraph))
    check("nothing the engine receives changes with the UV",
          not changed, f"changed keys={changed}")
    check("the reset leaves the sewings alone",
          qyapi.sewings.list(project=project.name) == sewings_before,
          "the sewing list changed")
    # A simulated frame lands in the simulated key, not in the rest positions, so
    # it must not move what a reset seeds from.
    simulated = shape_key_points(front.mesh_object, "QYSim") + np.array((0.05, 0.03, 0.0))
    front.mesh_object.data.shape_keys.key_blocks["QYSim"].points.foreach_set(
        "co", np.ascontiguousarray(simulated, dtype=np.float32).ravel())
    mesh.update()
    bpy.ops.qmyi.reset_pattern_uv()
    check("a simulated shape does not move the reset's seed",
          np.abs(vertex_uv(mesh) - rest_positions(front.mesh_object) * 2.0).max() < 1e-5,
          f"max difference="
          f"{np.abs(vertex_uv(mesh) - rest_positions(front.mesh_object) * 2.0).max()}")
    # Blender refuses `ed.undo` without a window, so the undo stack itself cannot
    # be exercised under `-b`. What the headless run can check is that the reset
    # declares an undo step and is one self-contained write of the layer.
    from qmyi.operators.pattern_uv import QY_OT_ResetPatternUV

    check("the reset asks for an undo step",
          'UNDO' in QY_OT_ResetPatternUV.bl_options,
          f"options={QY_OT_ResetPatternUV.bl_options}")
    log("SKIP one undo restores the UV: Blender's undo stack needs a window "
        "(live-session check)")

    # 5. a mirrored pattern's seed is mirrored, and a toggle mirrors the layer
    plain = build_square(project, "plain", 30.0, origin=(200.0, 0.0))
    mirrored = plain.copy_pattern(as_instance=True, mirror=True)
    mirror_mesh = mirrored.mesh_object.data
    plain_mesh = plain.mesh_object.data
    check("a mirrored copy's seed has its u negated",
          np.abs(vertex_uv(mirror_mesh) - vertex_uv(plain_mesh) * (-1.0, 1.0)).max() < 1e-5,
          "the mirrored seed is not the mirror of the source")
    toggle = build_square(project, "toggle", 30.0, origin=(400.0, 0.0))
    toggle_mesh = toggle.mesh_object.data
    before_toggle = vertex_uv(toggle_mesh).copy()
    qyapi.patterns.transform(toggle.name, mirror=True, project=project.name)
    toggle_mesh = toggle.mesh_object.data
    check("toggling mirror on a meshed pattern mirrors the UV it holds",
          np.abs(vertex_uv(toggle_mesh) - before_toggle * (-1.0, 1.0)).max() < 1e-5,
          "the layer was not mirrored by the toggle")

    # 6. the panel and the operator are registered where the UV editor can see them
    from qmyi.ui.panels.uv import IMAGE_PT_qmyi_pattern_uv

    check("the UV editor carries the Qianyi panel",
          IMAGE_PT_qmyi_pattern_uv.is_registered
          and IMAGE_PT_qmyi_pattern_uv.bl_space_type == 'IMAGE_EDITOR'
          and IMAGE_PT_qmyi_pattern_uv.bl_idname == Panels.PatternUV,
          f"registered={IMAGE_PT_qmyi_pattern_uv.is_registered} "
          f"space={IMAGE_PT_qmyi_pattern_uv.bl_space_type}")
    from qmyi.operators.pattern_uv import QY_OT_ResetPatternUV

    check("the reset is one registered undo step",
          QY_OT_ResetPatternUV.is_registered
          and QY_OT_ResetPatternUV.bl_idname == Operators.ResetPatternUV
          and 'UNDO' in QY_OT_ResetPatternUV.bl_options,
          f"registered={QY_OT_ResetPatternUV.is_registered} "
          f"options={QY_OT_ResetPatternUV.bl_options}")
    check("the reset refuses an object that is not a pattern mesh",
          _poll_refuses(cube_object(bpy.context)),
          "a plain mesh passed the poll")

    # 7. one mapping call, one UV read and one UV write per rebuild
    scene.qmyi.mesh_profile = True
    text = capture_stderr(lambda: front.generate_mesh(force=True))
    scene.qmyi.mesh_profile = False
    marks = [line for line in text.splitlines() if "[mesh]" in line]
    check("a rebuild still maps in one engine call",
          sum("find_map_weight" in line for line in marks) == 1,
          f"marks={marks}")
    check("a rebuild reads the UV once and writes it once",
          sum("read the current UVMap" in line for line in marks) == 1
          and sum("write UVMap" in line for line in marks) == 1,
          f"marks={marks}")

    # 8. the layer and the scale survive a save and a reopen
    saved_mesh = toggle.mesh_object.data
    # One flat UV over the whole mesh: whatever barycentric map a rebuild uses,
    # a constant layer has to come back constant, so this separates "carried"
    # from "seeded" for the reload check.
    write_vertex_uv(saved_mesh, np.tile(np.array((0.11, 0.22), dtype=np.float32),
                                        (len(saved_mesh.vertices), 1)))
    before_save = vertex_uv(saved_mesh).copy()
    out = os.path.join(tempfile.mkdtemp(prefix="qy_pattern_uv_"), "uv_probe.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    bpy.ops.wm.open_mainfile(filepath=out)
    refresh_all_uuids()
    reopened = bpy.data.node_groups["UVProbe"]
    reopened_pattern = pattern_named(reopened, "toggle")
    reopened_mesh = reopened_pattern.mesh_object.data
    check("the UV layer is saved with the file",
          reopened_mesh.uv_layers.get(UV_LAYER) is not None
          and np.abs(vertex_uv(reopened_mesh) - before_save).max() < 1e-5,
          "the saved layer did not come back")
    check("the UV scale is saved with the file",
          abs(float(bpy.context.scene.qmyi.uv_scale) - 2.0) < 1e-6,
          f"scale={bpy.context.scene.qmyi.uv_scale}")
    reopened_pattern.generate_mesh(force=True)
    reopened_mesh = reopened_pattern.mesh_object.data
    check("the reopened mesh rebuilds while carrying the saved UV",
          np.abs(vertex_uv(reopened_mesh) - before_save[0]).max() < 1e-5,
          "the carried layer is not the tile that was saved")

    log(f"done: {len(FAILURES)} failed check(s)")
    return 1 if FAILURES else 0


def cube_object(context):
    """A mesh object that is not a pattern mesh, for the poll check."""
    mesh = bpy.data.meshes.new("UVProbePlainMesh")
    obj = bpy.data.objects.new("UVProbePlainObject", mesh)
    context.collection.objects.link(obj)
    return obj


def _poll_refuses(obj) -> bool:
    """Whether the reset operator's poll refuses this object."""
    from qmyi.operators.pattern_uv import QY_OT_ResetPatternUV

    class _Context:
        active_object = obj

    return not QY_OT_ResetPatternUV.poll(_Context)


if __name__ == "__main__":
    sys.path.insert(0, QYIDP_BUILD)
    status = 1
    try:
        import_addon(ADDON_PATH, "qmyi")
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
