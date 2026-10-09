"""Check the pattern editor's and the 3D viewport's selection mirror.

    blender.exe -b --factory-startup --python tools/probe_selection_sync.py

Builds its own project (no scene file) and drives `selection_sync.sync_once`
directly, which is what the module's timer calls. Checks:

1. the module's timer registers with the add-on and unregisters again;
2. turning the toggle on adopts the selection already there without changing
   either side, and turning it off stops applying and forgets the state;
3. selecting a pattern's mesh in 3D selects that pattern, and only that one;
4. selecting a pattern selects its mesh and deselects the other's;
5. clearing either side clears the other;
6. an instance copy is left alone when one member of its chain is selected;
7. a collider keeps its own selection and changes no pattern;
8. a poll that cannot reach a project neither raises nor wedges: the pending
   editor change is applied once a project answers again.

Each check prints PASS or FAIL; the process exits non-zero when anything failed.
"""

import importlib.util
import os
import sys
import traceback

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_PATH = os.path.join(REPO, "Qianyi")
QYIDP_BUILD = os.environ.get("QYDP_PYD_DIR", r"R:\code\cuda\qmyidp\build\Release")
FAILURES = []


def log(message):
    print(f"[sync] {message}", flush=True)


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


def build_square(project, name, size, origin=(0.0, 0.0), granularity=10.0):
    """A pattern with a mesh, so it takes part in the mirror."""
    pattern = project.add_pattern()
    pattern.name = name
    pattern.granularity = granularity
    half = size / 2.0
    for point in ((origin[0] - half, origin[1] - half), (origin[0] + half, origin[1] - half),
                  (origin[0] + half, origin[1] + half), (origin[0] - half, origin[1] + half)):
        pattern.add_vertex(point)
    for index in range(4):
        pattern.add_edge(index, (index + 1) % 4, update=True)
    pattern.mark_geometry_changed()
    pattern.generate_mesh()
    return pattern


def main():
    qmyi = sys.modules["qmyi"]
    qmyi.register()
    from qmyi import global_data

    global_data.renderers_enabled = False
    from qmyi import selection_sync
    from qmyi.model.model_data import refresh_all_uuids

    # A node group that is not a project, so the active index can be pointed at
    # something the poll has to refuse (check 8). `bpy.data.node_groups` sorts
    # by name, so this one has to sort before the project for index 0 to be it.
    bpy.data.node_groups.new("ASyncProbeShader", "ShaderNodeTree")
    project = bpy.data.node_groups.new("SyncProbe", "QianyiNodeTree")
    project.use_fake_user = True
    project.get_default_fabric()
    refresh_all_uuids()
    first = build_square(project, "first", 40.0, origin=(120.0, 60.0))
    second = build_square(project, "second", 40.0, origin=(0.0, 0.0))
    copy = first.copy_pattern(as_instance=True, anchor=(60.0, 0.0))
    collider_mesh = bpy.data.meshes.new("SyncProbeColliderMesh")
    collider = bpy.data.objects.new("SyncProbeCollider", collider_mesh)
    bpy.context.collection.objects.link(collider)
    refresh_all_uuids()

    scene = bpy.context.scene
    project_index = [index for index, group in enumerate(bpy.data.node_groups)
                     if group == project][0]
    scene.qmyi.active_project_index = project_index
    scene.qmyi.sync_selection = False
    selection_sync.sync_once(bpy.context)          # clear the remembered state

    def deselect_all():
        for obj in bpy.context.view_layer.objects:
            obj.select_set(False)

    def settle():
        """Poll until nothing is pending, so one side can then change alone."""
        for _ in range(4):
            selection_sync.sync_once(bpy.context)

    def pattern_flags():
        return [pattern.is_selected for pattern in project.patterns]

    def selected_meshes():
        return sorted(obj.name for obj in bpy.context.selected_objects
                      if obj.type == 'MESH' and obj.qmyi_simulation_props.is_pattern_mesh)

    # 1. registration
    registered = bpy.app.timers.is_registered(selection_sync._timer)
    selection_sync.unregister()
    unregistered = not bpy.app.timers.is_registered(selection_sync._timer)
    selection_sync.register()
    check("the timer registers with the add-on and unregisters again",
          registered and unregistered
          and bpy.app.timers.is_registered(selection_sync._timer),
          f"registered={registered} unregistered={unregistered}")

    # 2. the toggle adopts, then stops
    deselect_all()
    first.is_selected = True
    second.is_selected = False
    first.mesh_object.select_set(True)
    scene.qmyi.sync_selection = True
    selection_sync.sync_once(bpy.context)
    check("turning the toggle on adopts both sides without changing them",
          pattern_flags() == [True, False, False] and selected_meshes() == ["first"],
          f"patterns={pattern_flags()} meshes={selected_meshes()}")
    scene.qmyi.sync_selection = False
    selection_sync.sync_once(bpy.context)
    second.is_selected = True
    applied = selection_sync.sync_once(bpy.context)
    check("turning the toggle off stops applying",
          not applied and selected_meshes() == ["first"],
          f"applied={applied} meshes={selected_meshes()}")

    # 3. 3D -> editor
    deselect_all()
    first.is_selected = False
    second.is_selected = False
    scene.qmyi.sync_selection = True
    settle()
    second.mesh_object.select_set(True)
    applied = selection_sync.sync_once(bpy.context)
    check("a selected mesh selects exactly its pattern",
          applied and pattern_flags() == [False, True, False],
          f"applied={applied} patterns={pattern_flags()}")

    # 4. editor -> 3D
    first.is_selected = True
    second.is_selected = False
    applied = selection_sync.sync_once(bpy.context)
    check("a selected pattern selects exactly its mesh",
          applied and selected_meshes() == ["first"],
          f"applied={applied} meshes={selected_meshes()}")

    # 5. clearing
    deselect_all()
    applied = selection_sync.sync_once(bpy.context)
    check("clearing the viewport clears the editor",
          applied and pattern_flags() == [False, False, False],
          f"applied={applied} patterns={pattern_flags()}")
    first.is_selected = True
    selection_sync.sync_once(bpy.context)
    first.is_selected = False
    applied = selection_sync.sync_once(bpy.context)
    check("clearing the editor clears the viewport",
          applied and selected_meshes() == [],
          f"applied={applied} meshes={selected_meshes()}")

    # 6. an instance copy is not dragged along
    deselect_all()
    settle()
    first.mesh_object.select_set(True)
    selection_sync.sync_once(bpy.context)
    check("an instance copy is left alone",
          pattern_flags() == [True, False, False],
          f"patterns={pattern_flags()} copy={copy.name}")

    # 7. a collider is not a pattern
    deselect_all()
    settle()
    collider.select_set(True)
    applied = selection_sync.sync_once(bpy.context)
    check("a collider keeps its own selection and moves no pattern",
          not applied and collider.select_get() and pattern_flags() == [False, False, False],
          f"applied={applied} collider={collider.select_get()} "
          f"patterns={pattern_flags()}")

    # 8. a stale active_project_index must not stop the mirror. The index is a
    # position in the name-sorted node groups, so adding, removing or renaming a
    # group ahead of the project leaves it naming another tree or nothing; the
    # poll has no editor to ask, so it has to find the project anyway.
    deselect_all()
    settle()
    scene.qmyi.active_project_index = len(bpy.data.node_groups)   # out of range
    first.mesh_object.select_set(True)
    applied = selection_sync.sync_once(bpy.context)
    check("a stale project index still finds the scene's project",
          applied and pattern_flags() == [True, False, False],
          f"applied={applied} patterns={pattern_flags()}")
    deselect_all()
    selection_sync.sync_once(bpy.context)
    second.is_selected = True
    applied = selection_sync.sync_once(bpy.context)
    check("a stale project index mirrors in both directions",
          applied and selected_meshes() == [second.mesh_object.name],
          f"applied={applied} meshes={selected_meshes()}")
    scene.qmyi.active_project_index = project_index

    # 9. With no project to reach at all the poll must neither raise nor wedge:
    # the change stays pending and lands once a project answers again.
    deselect_all()
    settle()
    first.is_selected = True
    selection_sync.sync_once(bpy.context)        # the editor's choice reached 3D
    original_active_project = selection_sync.active_project
    selection_sync.active_project = lambda *args, **kwargs: None
    try:
        first.is_selected = False
        second.is_selected = True
        applied = selection_sync.sync_once(bpy.context)
        raised = None
    except Exception as error:                    # noqa: BLE001 - reported below
        applied, raised = None, f"{type(error).__name__}: {error}"
    finally:
        selection_sync.active_project = original_active_project
    check("a poll that can reach no project neither raises nor applies",
          raised is None and not applied and selected_meshes() == ["first"],
          f"raised={raised} applied={applied} meshes={selected_meshes()}")
    applied = selection_sync.sync_once(bpy.context)
    check("the pending editor change applies once a project answers again",
          applied and selected_meshes() == [second.mesh_object.name],
          f"applied={applied} meshes={selected_meshes()}")

    log(f"done: {len(FAILURES)} failed check(s)")
    return 1 if FAILURES else 0


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

