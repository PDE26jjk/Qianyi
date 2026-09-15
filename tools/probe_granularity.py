"""Measure what ``granularity`` actually does to the pattern mesh.

    blender.exe -b --factory-startup <scene.blend> --python tools/probe_granularity.py

Regenerates the first pattern's mesh at several granularity values in this
throwaway session (the .blend is never saved) and reports the resulting vertex
spacing, so the sampler radius -> mesh spacing relation is measured instead of
guessed.

Measured on the reported garment scene (first pattern, granularity in mm):

    granularity  vertices   nn p50   nn max  edge p50  edge max
         2.0 mm     79368    1.375    2.577     1.516     4.999
         3.0 mm     35375    2.133    4.106     2.209     5.679
         4.0 mm     19947    2.827    4.970     2.916     6.597
         5.0 mm     12844    3.519    4.995     3.630     7.472
         6.0 mm      8991    4.214    4.998     4.345     8.600
         7.0 mm      6666    4.910    5.854     5.054    19.977
        10.0 mm      3402    6.989    8.094     7.209    14.111

Read: the setting acts as a sampling radius ceiling - the largest
nearest-neighbour distance tracks it up to ~6 mm (4.995 mm at a 5 mm request)
while the median spacing is ~0.70x of it, and the mesh includes the boundary
resampling, which does not follow the setting. A median edge of 5 mm needs a
request of about 7 mm.
"""

import importlib.util
import os
import sys
import traceback

import bpy
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")


def log(message):
    print(f"[granularity] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def mesh_stats(mesh_object):
    mesh = mesh_object.data
    vertices = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", vertices)
    vertices = vertices.reshape(-1, 3)
    edges = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", edges)
    edges = edges.reshape(-1, 2)
    lengths = np.linalg.norm(vertices[edges[:, 0]] - vertices[edges[:, 1]], axis=1)
    # Blender ships no scipy; mathutils has its own KD-tree.
    from mathutils.kdtree import KDTree

    tree = KDTree(len(vertices))
    for index, vertex in enumerate(vertices):
        tree.insert((float(vertex[0]), float(vertex[1]), 0.0), index)
    tree.balance()
    nearest = np.empty(len(vertices), dtype=np.float64)
    for index, vertex in enumerate(vertices):
        # find_n is sorted by distance: the first hit is the vertex itself.
        found = tree.find_n((float(vertex[0]), float(vertex[1]), 0.0), 2)
        nearest[index] = found[-1][2]
    return (len(vertices),
            float(np.median(nearest) * 1000),
            float(nearest.max() * 1000),
            float(np.median(lengths) * 1000),
            float(lengths.max() * 1000))


def main():
    import_addon(ADDON_PATH, "qmyi")
    from qmyi import global_data
    from qmyi.model import model_data
    from qmyi.model.pattern_mesh import generate_pattern_mesh

    global_data.renderers_enabled = False
    from qmyi import model

    model.register()

    from qmyi.utilities.node_tree import get_all_node_tree

    projects = get_all_node_tree()
    if not projects:
        log("no Qianyi project in the scene")
        return 2
    model_data.refresh_all_uuids()
    pattern = projects[0].patterns[0]
    pattern.need_geo_update = True
    pattern.calc_mesh_edge_points()
    log(f"pattern={pattern.name} granularity={pattern.granularity} mm "
        f"mesh={pattern.mesh_object.name}")

    log(f"{'granularity':>12} {'vertices':>9} {'nn p50':>8} {'nn max':>8} "
        f"{'edge p50':>9} {'edge max':>9}")
    for granularity_mm in (2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 10.0):
        generate_pattern_mesh(pattern, granularity_mm / 1000.0, pattern.mesh_object)
        count, nn50, nn_max, edge50, edge_max = mesh_stats(pattern.mesh_object)
        log(f"{granularity_mm:>9.1f} mm {count:>9} {nn50:>7.3f} {nn_max:>7.3f} "
            f"{edge50:>8.3f} {edge_max:>8.3f}")
    return 0


if __name__ == "__main__":
    status = 1
    try:
        status = main()
    except Exception:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
