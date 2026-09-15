"""Measure what the pattern editor costs per redraw, without a GPU context.

    blender.exe -b --factory-startup <scene.blend> --python tools/probe_panel_draw_cost.py

The node editor draw callback (draw_editor.node_draw_callback ->
TempDrawManager.draw) runs on every redraw, i.e. on every mouse move. This
probe stubs the GPU entry points (shader creation, batches, offscreen, state)
and counts what the real code path asks for, per edit mode, plus the Python
time it spends. No solver, no engine call, no GPU work.
"""

import contextlib
import cProfile
import importlib.util
import os
import pstats
import sys
import time
import traceback

import bpy
import gpu
import gpu_extras.batch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")

COUNTS = {"shader_create": 0, "shader_builtin": 0, "batch": 0, "draw": 0,
          "offscreen": 0, "framebuffer_clear": 0}
SITES = {}
MISSING = set()


def note_site(kind, depth=3):
    stack = traceback.extract_stack()
    frame = stack[-(depth + 1)]
    key = f"{kind} @ {os.path.basename(frame.filename)}:{frame.lineno} {frame.name}"
    SITES[key] = SITES.get(key, 0) + 1


class FakeBatch:
    def draw(self, *args, **kwargs):
        COUNTS["draw"] += 1


class FakeShader:
    def bind(self):
        pass

    def uniform_float(self, *args, **kwargs):
        pass

    def uniform_block(self, *args, **kwargs):
        pass

    def uniform_sampler(self, *args, **kwargs):
        pass


class FakeUniformBuf:
    def __init__(self, *args, **kwargs):
        pass

    def update(self, *args, **kwargs):
        pass


class FakeFrameBuffer:
    def clear(self, *args, **kwargs):
        COUNTS["framebuffer_clear"] += 1

    def read_color(self, *args, **kwargs):
        COUNTS["readback"] = COUNTS.get("readback", 0) + 1
        return [[(0.0, 0.0, 0.0, 0.0)]]


class FakeOffScreen:
    def __init__(self, *args, **kwargs):
        COUNTS["offscreen"] += 1
        self.texture_color = None

    def bind(self):
        return contextlib.nullcontext()


class FakeGpuState:
    def __getattr__(self, name):
        if name == "active_framebuffer_get":
            return lambda *args, **kwargs: FakeFrameBuffer()
        return lambda *args, **kwargs: None


class FakeGpuMatrix:
    def push(self):
        COUNTS["push"] = COUNTS.get("push", 0) + 1

    def pop(self):
        COUNTS["pop"] = COUNTS.get("pop", 0) + 1

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def install_gpu_stubs():
    def fake_batch_for_shader(*args, **kwargs):
        COUNTS["batch"] += 1
        note_site("batch")
        return FakeBatch()

    def fake_create_from_info(info):
        COUNTS["shader_create"] += 1
        note_site("shader")
        return FakeShader()

    def fake_from_builtin(name):
        COUNTS["shader_builtin"] += 1
        note_site("builtin")
        return FakeShader()

    # Patched before the addon imports these names, so every `from ... import`
    # in the addon picks the stub up.
    gpu_extras.batch.batch_for_shader = fake_batch_for_shader
    gpu.shader.create_from_info = fake_create_from_info
    gpu.shader.from_builtin = fake_from_builtin
    gpu.types.GPUUniformBuf = FakeUniformBuf
    gpu.types.GPUOffScreen = FakeOffScreen
    gpu.state = FakeGpuState()
    gpu.matrix = FakeGpuMatrix()


class FakeRegion:
    width = 1280
    height = 720


class FakeSpace:
    def __init__(self, node_tree):
        self.node_tree = node_tree


class FakeContext:
    def __init__(self, scene, node_tree):
        self.scene = scene
        self.region = FakeRegion()
        self.space_data = FakeSpace(node_tree)
        self.area = None


def log(message):
    print(f"[draw] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def measure(manager, context, label, repeats=3):
    from qmyi import global_data as _global_data
    from qmyi.model.pattern import Pattern

    original_lookup = _global_data.get_obj_by_uuid
    original_calc = Pattern.calc_matrix
    stats = {}

    def new_bucket():
        return {"lookups": {}, "sections": {}, "calc_calls": 0, "calc_ms": 0.0}

    def counting_lookup(uuid, check_uuid=True, check_valid=False):
        started = time.perf_counter()
        result = original_lookup(uuid, check_uuid, check_valid)
        elapsed = (time.perf_counter() - started) * 1000.0
        if result is None:
            MISSING.add(uuid)
        bucket = stats["current"]
        name = type(result).__name__ if result is not None else "None"
        entry = bucket["lookups"].setdefault(name, [0, 0.0])
        entry[0] += 1
        entry[1] += elapsed
        bucket.setdefault("slowest", []).append((elapsed, uuid, name))
        return result

    def counting_calc(self):
        started = time.perf_counter()
        result = original_calc(self)
        bucket = stats["current"]
        bucket["calc_calls"] += 1
        bucket["calc_ms"] += (time.perf_counter() - started) * 1000.0
        return result

    _global_data.get_obj_by_uuid = counting_lookup
    Pattern.calc_matrix = counting_calc

    def timed(name, function):
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            result = function(*args, **kwargs)
            stats["current"]["sections"][name] = (time.perf_counter() - started) * 1000.0
            return result
        return wrapper

    manager.draw_id = timed("draw_id", manager.draw_id)
    manager.draw_hover = timed("draw_hover", manager.draw_hover)

    def run_once():
        stats["current"] = new_bucket()
        for key in COUNTS:
            COUNTS[key] = 0
        SITES.clear()
        started = time.perf_counter()
        try:
            manager.draw(context)
        except Exception as error:
            log(f"{label}: draw raised {error!r} (measurement kept)")
        return (time.perf_counter() - started) * 1000.0

    def report(kind, elapsed_ms, bucket):
        log(f"{label} [{kind}] {elapsed_ms:.2f} ms; "
            f"calc_matrix={bucket['calc_calls']}x/{bucket['calc_ms']:.2f}ms; "
            f"shader={COUNTS['shader_create']} builtin={COUNTS['shader_builtin']} "
            f"batch={COUNTS['batch']} draw={COUNTS['draw']} "
            f"sections={' '.join(f'{n}={v:.2f}' for n, v in sorted(bucket['sections'].items()))}")
        lookups = " ".join(f"{name}={count}x/{total:.2f}ms"
                           for name, (count, total) in sorted(bucket["lookups"].items(),
                                                              key=lambda item: -item[1][1]))
        if lookups:
            log(f"{label} [{kind}] lookups {lookups}")
        slowest = sorted(bucket.get("slowest", []), reverse=True)[:5]
        if slowest:
            log(f"{label} [{kind}] slowest lookups "
                + " ".join(f"{ms:.3f}ms/{uuid}/{name}" for ms, uuid, name in slowest))

    report("first", run_once(), stats["current"])
    samples = [run_once() for _ in range(repeats)]
    ordered = sorted(samples)
    log(f"{label} [steady] median={ordered[len(ordered) // 2]:.2f} ms "
        f"all={[round(value, 2) for value in samples]}")
    total = new_bucket()
    for bucket in [stats["current"]]:
        for name, (count, ms) in bucket["lookups"].items():
            entry = total["lookups"].setdefault(name, [0, 0.0])
            entry[0] += count
            entry[1] += ms
        total["calc_calls"] += bucket["calc_calls"]
        total["calc_ms"] += bucket["calc_ms"]
    report("steady last", samples[-1], total)

    _global_data.get_obj_by_uuid = original_lookup
    Pattern.calc_matrix = original_calc


def main():
    install_gpu_stubs()
    import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data
    from qmyi import model
    from qmyi.model import model_data
    from qmyi.utilities.node_tree import get_all_node_tree

    model.register()
    from qmyi.gizmos.temp_draw_manager import TempDrawManager

    manager = TempDrawManager()
    global_data.temp_draw_manager = manager
    log(f"registered {model_data.refresh_all_uuids()} model objects")

    projects = get_all_node_tree()
    if not projects:
        log("no Qianyi project in this scene")
        return 2
    project = projects[0]
    context = FakeContext(bpy.context.scene, project)
    scene_qmyi = bpy.context.scene.qmyi

    counts = []
    for pattern in project.patterns:
        spline_points = sum(len(edge.spline_points) for edge in pattern.edges)
        geo_points = sum(len(edge.geo_points) for edge in pattern.edges)
        counts.append(len(pattern.edges))
        log(f"pattern {pattern.name}: edges={len(pattern.edges)} vertices={len(pattern.vertices)} "
            f"internal_lines={len(pattern.internal_lines)} spline_points={spline_points} "
            f"geo_points={geo_points}")
    log(f"patterns={len(project.patterns)} sewings={len(project.sewings)} "
        f"edges per pattern={counts}")

    def find_uuid(uuid):
        """Where in the model tree the uuid lives, if anywhere."""
        hits = []

        def add(label, item):
            if getattr(item, "global_uuid", None) == uuid:
                hits.append(label)

        add("project", project)
        for fabric_index, fabric in enumerate(project.fabrics):
            add(f"fabrics[{fabric_index}]", fabric)
        for pattern_index, pattern in enumerate(project.patterns):
            add(f"patterns[{pattern_index}]", pattern)
            for vertex_index, vertex in enumerate(pattern.vertices):
                add(f"patterns[{pattern_index}].vertices[{vertex_index}]", vertex)
            for edge_index, edge in enumerate(pattern.edges):
                add(f"patterns[{pattern_index}].edges[{edge_index}]", edge)
                for handle_index, handle in enumerate(edge.handles):
                    add(f"patterns[{pattern_index}].edges[{edge_index}].handles[{handle_index}]", handle)
                for point_index, point in enumerate(edge.geo_points):
                    add(f"patterns[{pattern_index}].edges[{edge_index}].geo_points[{point_index}]", point)
                for point_index, point in enumerate(edge.spline_points):
                    add(f"patterns[{pattern_index}].edges[{edge_index}].spline_points[{point_index}]", point)
            for line_index, line in enumerate(pattern.internal_lines):
                add(f"patterns[{pattern_index}].internal_lines[{line_index}]", line)
                for edge_index, edge in enumerate(line.edges):
                    add(f"patterns[{pattern_index}].internal_lines[{line_index}].edges[{edge_index}]", edge)
        for sewing_index, sewing in enumerate(project.sewings):
            add(f"sewings[{sewing_index}]", sewing)
            for side_index, side in enumerate(sewing.sides):
                add(f"sewings[{sewing_index}].sides[{side_index}]", side)
        return hits


    # The lookup the draw path performs per edge / vertex / sewing side.
    pattern = project.patterns[0]
    repeats = 200
    samples = [("Pattern", pattern), ("Edge2D", pattern.edges[0]),
               ("Vertex2D", pattern.vertices[0])]
    if len(project.sewings) > 0:
        sewing = project.sewings[0]
        samples.append(("Sewing", sewing))
        if len(sewing.sides) > 0:
            samples.append(("SewingOneSide", sewing.sides[0]))
    for label, item in samples:
        started = time.perf_counter()
        for _ in range(repeats):
            item.path_from_id()
        path_ms = (time.perf_counter() - started) * 1000.0 / repeats
        started = time.perf_counter()
        for _ in range(repeats):
            global_data.get_obj_by_uuid(item.global_uuid)
        lookup_ms = (time.perf_counter() - started) * 1000.0 / repeats
        log(f"{label}: path_from_id={path_ms:.4f} ms  get_obj_by_uuid={lookup_ms:.4f} ms")
    started = time.perf_counter()
    for _ in range(repeats):
        global_data.uuid2obj[pattern.global_uuid]
    log(f"raw dict hit={((time.perf_counter() - started) * 1000.0 / repeats):.6f} ms")

    # Per object, because the cost clearly depends on the object.
    for pattern_index, item_pattern in enumerate(project.patterns):
        costs = []
        for edge in item_pattern.edges:
            started = time.perf_counter()
            for _ in range(50):
                global_data.get_obj_by_uuid(edge.global_uuid)
            costs.append((time.perf_counter() - started) * 1000.0 / 50)
        log(f"pattern[{pattern_index}] edge lookups ms: "
            + " ".join(f"{value:.3f}" for value in costs))
    sewing_costs = []
    for sewing in project.sewings:
        started = time.perf_counter()
        for _ in range(50):
            global_data.get_obj_by_uuid(sewing.global_uuid)
        sewing_costs.append((time.perf_counter() - started) * 1000.0 / 50)
    if sewing_costs:
        log("sewing lookups ms: " + " ".join(f"{value:.3f}" for value in sewing_costs))

    probes = [("pattern0", project.patterns[0]), ("pattern1", project.patterns[1])]
    probes.append(("pattern0.edge0", project.patterns[0].edges[0]))
    probes.append(("pattern1.edge0", project.patterns[1].edges[0]))
    probes.append(("pattern1.vertex0", project.patterns[1].vertices[0]))
    probes.append(("pattern1.edge0.handle1", project.patterns[1].edges[0].handle1))
    probes.append(("pattern1.edge0.geo0", project.patterns[1].edges[0].geo_points[0]))
    probes.append(("sewing0", project.sewings[0]))
    probes.append(("sewing0.side1", project.sewings[0].sides[0]))
    for label, item in probes:
        try:
            item.path_from_id()
            status = ""
        except Exception as error:
            status = f" raised={error!r}"
        started = time.perf_counter()
        for _ in range(100):
            try:
                item.path_from_id()
            except Exception:
                pass
        cost = (time.perf_counter() - started) * 1000.0 / 100
        resolved = global_data.get_obj_by_uuid(item.global_uuid)
        cached = global_data.uuid2obj.get(item.global_uuid)
        cached_path = cached.path_from_id() if cached is not None else None
        log(f"path_from_id {label} (uuid={item.global_uuid}): {cost:.4f} ms{status} "
            f"map_has_entry={cached is not None} map_path={cached_path} probe_path={item.path_from_id()} "
            f"same_path={cached_path == item.path_from_id()}")

    for mode, sub_mode in (("PATTERN", "EDGE_VERTEX"), ("EDGE", "EDGE_VERTEX"),
                           ("SEWING", "EDGE_VERTEX"), ("SEWING", "ADD_SEWING1")):
        scene_qmyi.edit_mode = mode
        scene_qmyi.edit_sub_mode = sub_mode
        try:
            measure(manager, context, f"mode={mode}/{sub_mode}")
        except Exception:
            log(f"mode={mode}/{sub_mode}: FAIL")
            traceback.print_exc()

    # Attribute the cost of the two slow modes.
    import io

    for mode, sub_mode in (("EDGE", "EDGE_VERTEX"), ("SEWING", "EDGE_VERTEX")):
        scene_qmyi.edit_mode = mode
        scene_qmyi.edit_sub_mode = sub_mode
        profile = cProfile.Profile()
        profile.enable()
        try:
            manager.draw(context)
        except Exception:
            pass
        profile.disable()
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).sort_stats("tottime").print_stats(12)
        log(f"profile {mode}/{sub_mode}:")
        for line in stream.getvalue().splitlines()[4:24]:
            log(f"  {line.strip()}")

    for uuid in sorted(MISSING):
        hits = find_uuid(uuid)
        log(f"missing uuid {uuid} -> {hits if hits else 'not in the model tree'}")

    check_hover_matrix_balance(project)
    return 0


def check_hover_matrix_balance(project):
    """Every draw_hover path must leave the GPU matrix stack balanced.

    An unbalanced push is what crashed Blender in gizmo_axis_draw: the stack
    stays one entry deep and the next consumer reads a null matrix.
    """
    from qmyi.gizmos.temp_draw_manager import TempDrawManager

    manager = TempDrawManager()
    manager.uniform_color_shader = FakeShader()
    scene_qmyi = bpy.context.scene.qmyi
    pattern = project.patterns[0]
    edge = pattern.edges[0]

    cases = [
        ("none", None),
        ("pattern", pattern),
        ("vertex", pattern.vertices[0]),
        ("edge", edge),
    ]
    if len(project.sewings) > 0:
        cases.append(("sewing", project.sewings[0]))

    saved_points = getattr(edge, "render_points", None)
    cases.append(("edge_without_render_points", edge))
    for label, item in cases:
        edge.render_points = None if label == "edge_without_render_points" else saved_points
        COUNTS["push"] = 0
        COUNTS["pop"] = 0
        scene_qmyi.set_hover_object(item)
        raised = None
        try:
            manager.draw_hover(scene_qmyi)
        except Exception as error:
            raised = repr(error)
        balanced = COUNTS["push"] == COUNTS["pop"]
        log(f"hover={label}: push={COUNTS['push']} pop={COUNTS['pop']} "
            f"balanced={balanced} raised={raised}")
    edge.render_points = saved_points
    scene_qmyi.set_hover_object(None)


if __name__ == "__main__":
    status = 1
    try:
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
