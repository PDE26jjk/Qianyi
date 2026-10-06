"""Measure what the pattern UV layer costs a mesh rebuild.

    blender.exe -b --factory-startup --python tools/probe_pattern_uv_cost.py

Builds three patterns of the same size at three granularities and, for each:

* times `generate_mesh(force=True)` with the UV work in place and with it
  stubbed out, interleaved so the machine's drift lands on both;
* reads the rebuild's own profile marks for the UV phases - the read of the
  layer, the mix onto the new points and the write - which is the added work a
  rebuild can be charged for;
* reports the UV total against the whole rebuild.

The last line checks the fact the design rests on: clearing a mesh's geometry
takes its UV layer with it, which is why the layer is read before the rebuild.
"""

import importlib.util
import io
import os
import statistics
import sys
import time
import traceback

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")
QYIDP_BUILD = r"R:\code\cuda\qmyidp\build\Release"
RUNS = 30


def log(message):
    print(f"[cost] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name,
                                                  os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def build_square(project, name, size, granularity):
    pattern = project.add_pattern()
    pattern.name = name
    pattern.granularity = granularity
    half = size / 2.0
    for point in ((-half, -half), (half, -half), (half, half), (-half, half)):
        pattern.add_vertex(point)
    for index in range(4):
        pattern.add_edge(index, (index + 1) % 4, update=True)
    pattern.mark_geometry_changed()
    pattern.generate_mesh()
    return pattern


class _Capture:
    def __init__(self):
        self.buffer = io.BytesIO()

    def flush(self):
        return None


def capture_stderr(call) -> str:
    capture = _Capture()
    original = sys.__stderr__
    sys.__stderr__ = capture
    try:
        call()
    finally:
        sys.__stderr__ = original
    return capture.buffer.getvalue().decode("utf8", "replace")


def phase_times(text):
    """The profile marks one rebuild printed, as name -> seconds."""
    marks = {}
    for line in text.splitlines():
        if "[mesh]" not in line or ":" not in line:
            continue
        name, _, value = line.partition("[mesh]")[2].partition(":")
        try:
            marks[name.strip()] = float(value.strip())
        except ValueError:
            continue
    return marks


def main():
    qmyi = sys.modules["qmyi"]
    qmyi.register()
    from qmyi import global_data

    global_data.renderers_enabled = False
    from qmyi.model import pattern_mesh
    from qmyi.model.model_data import refresh_all_uuids

    project = bpy.data.node_groups.new("UVCost", "QianyiNodeTree")
    project.use_fake_user = True
    project.get_default_fabric()
    refresh_all_uuids()
    log(f"blender {bpy.app.version_string}")

    for granularity in (3.0, 6.0, 10.0):
        pattern = build_square(project, f"perf_{granularity:g}", 300.0, granularity)
        mesh = pattern.mesh_object.data
        for _ in range(3):
            pattern.generate_mesh(force=True)

        # The two variants are interleaved: the machine's load drifts over a
        # run, and measuring one group after the other put that drift into the
        # difference (a coarse mesh once came out "faster" with the UV work in).
        def rebuild(stubbed):
            if stubbed:
                pattern_mesh.read_vertex_uv = lambda mesh, loop_vertex=None: None
                pattern_mesh.write_vertex_uv = lambda mesh, uv, loop_vertex=None: None
            elif mesh.uv_layers.get("UVMap") is None:
                # A stubbed rebuild leaves the mesh without a layer (the mesh
                # clear takes it), and a rebuild with no layer reads nothing:
                # put it back outside the timer, the way the editor keeps it.
                pattern.generate_mesh(force=True)
            start = time.perf_counter()
            pattern.generate_mesh(force=True)
            elapsed = (time.perf_counter() - start) * 1e3
            if stubbed:
                pattern_mesh.read_vertex_uv, pattern_mesh.write_vertex_uv = original
            return elapsed

        original = (pattern_mesh.read_vertex_uv, pattern_mesh.write_vertex_uv)
        with_uv, without_uv = [], []
        for index in range(RUNS):
            if index % 2:
                without_uv.append(rebuild(True))
                with_uv.append(rebuild(False))
            else:
                with_uv.append(rebuild(False))
                without_uv.append(rebuild(True))

        # The phases of the rebuild itself: the UV work measured in place, which
        # is the number that can be attributed to the feature.
        if mesh.uv_layers.get("UVMap") is None:
            pattern.generate_mesh(force=True)
        per_phase = {}
        total = []
        bpy.context.scene.qmyi.mesh_profile = True
        try:
            for _ in range(5):
                start = time.perf_counter()
                marks = phase_times(capture_stderr(lambda: pattern.generate_mesh(force=True)))
                total.append((time.perf_counter() - start) * 1e3)
                for name, value in marks.items():
                    per_phase.setdefault(name, []).append(value)
        finally:
            bpy.context.scene.qmyi.mesh_profile = False

        delta = statistics.median(with_uv) - statistics.median(without_uv)
        log(f"granularity {granularity:g} mm: {len(mesh.vertices)} vertices, "
            f"{len(mesh.polygons)} triangles, {len(mesh.loops)} loops")
        log(f"  with UV    median {statistics.median(with_uv):7.2f} ms "
            f"(min {min(with_uv):.2f})")
        log(f"  without UV median {statistics.median(without_uv):7.2f} ms "
            f"(min {min(without_uv):.2f})")
        log(f"  delta {delta:+.2f} ms "
            f"({delta / statistics.median(without_uv) * 100:+.2f}%)")
        uv_phases = ("read the current UVMap", "mix UVs onto the new points", "write UVMap")
        log("  UV phases: " + ", ".join(
            f"{name}={statistics.median(per_phase.get(name, [0.0])) * 1e3:.2f} ms"
            for name in uv_phases))
        uv_total = sum(statistics.median(per_phase.get(name, [0.0])) for name in uv_phases)
        log(f"  UV total {uv_total * 1e3:.2f} ms of a "
            f"{statistics.median(total):.2f} ms rebuild "
            f"({uv_total * 1e3 / statistics.median(total) * 100:.2f}%)")

    # Whether clearing the geometry takes the layer with it, which is why the
    # read has to happen before the rebuild. Last, because it destroys the mesh.
    mesh.clear_geometry()
    log(f"layers after clear_geometry: {[layer.name for layer in mesh.uv_layers]}")
    return 0


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
