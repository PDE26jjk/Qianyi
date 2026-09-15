"""Operator that writes the scene's simulation inputs into a capture package."""

import os

import bpy

from ..simulation import scene_capture


def default_capture_directory(context=None):
    """``<directory of the .blend>/captures``, or the user directory."""
    blend = bpy.data.filepath
    root = os.path.dirname(blend) if blend else bpy.utils.resource_path('USER')
    return os.path.join(root, "captures")


class CaptureSceneOperator(bpy.types.Operator):
    """Capture the scene for the test system

    Writes the mesh, fabric, sewing and parameter state of the current scene
    into a directory (scene.json plus scene.npz) that the test harness can load
    without Blender. The .blend itself is not saved and no vertex is moved.
    """

    bl_idname = "qmyi.capture_scene"
    bl_label = "Capture Scene"
    bl_options = {'REGISTER'}

    directory: bpy.props.StringProperty(
        name="Directory",
        description="Directory that receives scene.json and scene.npz",
        subtype='DIR_PATH',
    )
    use_dialog: bpy.props.BoolProperty(
        name="Ask for the directory",
        description="Open the file browser instead of using the stored directory",
        default=False,
    )
    use_scene_name: bpy.props.BoolProperty(
        name="Subfolder per scene",
        description="Write into <directory>/<scene name>",
        default=True,
    )

    def invoke(self, context, event):
        props = context.scene.qmyi.capture
        self.use_scene_name = props.per_scene_subfolder
        if not self.directory:
            self.directory = props.directory or default_capture_directory(context)
        if not self.use_dialog:
            return self.execute(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        target = bpy.path.abspath(self.directory) if self.directory else default_capture_directory(context)
        if self.use_scene_name:
            target = os.path.join(target, context.scene.name)
        solver = context.scene.qmyi.solver
        package, json_path, array_path = scene_capture.capture(
            target, solver=solver.solver_name, parameters=solver.as_dict())
        summary = package["json"]["summary"]
        context.scene.qmyi.capture.last_capture = json_path
        self.report(
            {'INFO'},
            f"captured {summary['object_count']} objects "
            f"({summary['vertex_count']} vertices, {summary['stitch_count']} stitches) to {json_path}")
        return {'FINISHED'}


classes = (
    CaptureSceneOperator,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
