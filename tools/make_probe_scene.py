"""Build a scene for the probes, in the two-layer format.

    blender.exe -b --factory-startup --python tools/make_probe_scene.py -- \
        --out extracted_files/test/layers.blend

The scene-file probes (the agent api, the model api, the section invariants and
the delete regression) open a scene and work on the panels it holds. A scene
saved before the Sketch layer carries no Sketch and is not converted, so this
builds the fixture they need: two sewn panels and a third with a copy, the same
shape the probes were written against.

``build_fixture()`` is the shared entry point: a probe imports it and builds the
fixture in its own session instead of opening a maintainer ``.blend``.
"""

import argparse
import importlib
import importlib.util
import os
import sys
import traceback

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")
QYIDP_BUILD = r"R:\code\cuda\qmyidp\build\Release"


def log(message):
    print(f"[fixture] {message}", flush=True)


def import_addon(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name,
                                                  os.path.join(path, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def build_square(project, name, size, origin=(0.0, 0.0), granularity=20.0):
    """A closed square panel with one internal line across it."""
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


def register_core():
    """Register the add-on modules the fixture needs, with the renderers off."""
    from qmyi import global_data

    global_data.renderers_enabled = False
    from qmyi.registration import core_modules

    for name in core_modules:
        importlib.import_module(f"qmyi.{name}")
    for name in core_modules:
        module = sys.modules.get(f"qmyi.{name}")
        if module is not None and hasattr(module, "register"):
            module.register()


def build_fixture():
    """Build the fixture in the current session and return the project.

    Two sewn panels plus a copy, in the two-layer format the probes were written
    against. No file is opened and nothing is saved; the caller owns the session.
    """
    from qmyi.model.model_data import refresh_all_uuids

    project = bpy.data.node_groups.new("QianyiProject", "QianyiNodeTree")
    # A node tree with no user is dropped when the file is saved, and a
    # background session has no node editor to hold it: the fake user is what
    # keeps the project in the fixture.
    project.use_fake_user = True
    project.get_default_fabric()
    first = build_square(project, "front", 40.0, (0.0, 0.0))
    second = build_square(project, "front_mirror", 40.0, (0.0, 0.0))
    second.is_mirror = True
    third = build_square(project, "back", 40.0, (120.0, 0.0))
    copy = first.copy_pattern(as_instance=True, anchor=(60.0, 0.0))
    refresh_all_uuids()
    # The internal line's seam is written first, the outline's second: the
    # probes' scenarios rewrite `sewings[1]`, and an outline seam is the case
    # they were written against (a reversed side cannot start at the far end of
    # an open line's last edge).
    project.add_sewing(first.internal_lines[0].edges[0], 0.0,
                       first.internal_lines[0].edges[0], 1.0, False,
                       third.edges[2], 0.0, third.edges[2], 1.0, False)
    project.add_sewing(first.edges[0], 0.0, first.edges[0], 1.0, False,
                       third.edges[0], 0.0, third.edges[0], 1.0, False)
    refresh_all_uuids()
    log(f"patterns={len(project.patterns)} sketches={len(project.sketches)} "
        f"sewings={len(project.sewings)} copy={copy.name}")
    return project


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:]
                             if "--" in sys.argv else [])

    log(f"blender {bpy.app.version_string}")
    register_core()
    build_fixture()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))
    log(f"saved {args.out}")
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
