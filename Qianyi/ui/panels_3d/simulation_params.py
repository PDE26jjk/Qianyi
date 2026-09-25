"""Solver panel: the solver name, its parameter block and the scene capture.

Each parameter group is a child panel with ``DEFAULT_CLOSED``, so the sidebar
shows one collapsed line per group instead of a wall of sliders. Developer
mode adds the engine debug group and the custom key/value list.
"""

import re

import bpy

from ... import declarations
from ...model.solver_params import parameter_groups
from . import VIEW_3D_PT_qmyi_base

# The declarations are `str` enums: an f-string of the member would print
# "Panels.Solver", so the id is taken from `.value` wherever it is composed.
SOLVER_PANEL_ID = declarations.Panels.Solver.value


class QY_PT_solver(VIEW_3D_PT_qmyi_base):
    bl_category = "Qianyi"
    bl_label = "Solver"
    bl_idname = SOLVER_PANEL_ID

    def draw(self, context):
        layout = self.layout
        solver = context.scene.qmyi.solver

        layout.prop(solver, "solver_name")
        row = layout.row(align=True)
        row.operator("qmyi.solver_apply_parameters", icon='PLAY')
        row.operator("qmyi.solver_load_defaults", icon='LOOP_BACK')
        row.operator("qmyi.solver_import_json", text="", icon='IMPORT')
        layout.prop(solver, "apply_on_start")
        layout.prop(solver, "developer_mode")
        if solver.last_applied:
            layout.label(text=solver.last_applied, icon='CHECKMARK')


def _make_group_panel(group, specs, index):
    """One collapsible sub-panel per parameter group."""

    def draw(self, context):
        solver = context.scene.qmyi.solver
        column = self.layout.column(align=True)
        for spec in specs:
            column.prop(solver, spec.name)

    def poll(cls, context):
        if not developer_only:
            return True
        return bool(context.scene.qmyi.solver.developer_mode)

    developer_only = all(spec.developer for spec in specs)
    name = re.sub(r"[^0-9A-Za-z]", "_", group)
    return type(
        f"QY_PT_solver_group_{name}",
        (VIEW_3D_PT_qmyi_base,),
        {
            "bl_idname": f"{SOLVER_PANEL_ID}_group_{index}",
            "bl_label": group,
            "bl_parent_id": SOLVER_PANEL_ID,
            "bl_category": "Qianyi",
            "bl_options": {'DEFAULT_CLOSED'},
            "draw": draw,
            "poll": classmethod(poll),
        },
    )


GROUP_PANELS = tuple(
    _make_group_panel(group, specs, index)
    for index, (group, specs) in enumerate(parameter_groups())
)


class QY_UL_custom_parameter(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        key_column = layout.split(factor=0.55)
        key_column.prop(item, "key", text="", emboss=False)
        key_column.prop(item, "value", text="", emboss=False)


class QY_PT_solver_custom(VIEW_3D_PT_qmyi_base):
    bl_category = "Qianyi"
    bl_label = "Custom"
    bl_parent_id = SOLVER_PANEL_ID
    bl_idname = f"{SOLVER_PANEL_ID}_custom"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene.qmyi.solver.developer_mode

    def draw(self, context):
        layout = self.layout
        solver = context.scene.qmyi.solver
        layout.template_list("QY_UL_custom_parameter", "", solver, "custom",
                             solver, "custom_index", rows=3)
        row = layout.row(align=True)
        row.operator("qmyi.solver_custom_add", text="Add", icon='ADD')
        row.operator("qmyi.solver_custom_remove", text="Remove", icon='REMOVE')
        layout.label(text="Unknown keys are passed to the engine as-is", icon='INFO')


class QY_PT_solver_debug(VIEW_3D_PT_qmyi_base):
    """Debug switches: the mesh path, and how the editing tools write.

    A Blender panel of its own, next to Solver, and only in developer mode.
    """

    bl_category = "Qianyi"
    bl_label = "Debug"
    bl_idname = "QY_PT_mesh_debug"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene.qmyi.solver.developer_mode

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.qmyi, "triangulator")
        if context.scene.qmyi.triangulator == '1':
            layout.label(text="gCDT is not stable on every input yet", icon='ERROR')
        layout.prop(context.scene.qmyi, "mesh_profile")
        layout.prop(context.scene.qmyi, "spline_no_handles")
        if context.scene.qmyi.spline_no_handles:
            layout.label(text="a new control point leaves the edge with vector "
                              "handles, so it is not smoothed through it",
                         icon='INFO')


class QY_PT_capture(VIEW_3D_PT_qmyi_base):
    bl_category = "Qianyi"
    bl_label = "Capture"
    bl_idname = declarations.Panels.Capture.value

    def draw(self, context):
        layout = self.layout
        capture = context.scene.qmyi.capture

        layout.prop(capture, "directory")
        layout.prop(capture, "per_scene_subfolder")
        row = layout.row(align=True)
        row.operator("qmyi.capture_scene", icon='FILE_TICK')
        row.operator("qmyi.capture_scene", text="Capture to...", icon='FILEBROWSER').use_dialog = True
        if capture.last_capture:
            layout.label(text=capture.last_capture, icon='CHECKMARK')


class ApplySolverParametersOperator(bpy.types.Operator):
    bl_idname = "qmyi.solver_apply_parameters"
    bl_label = "Apply to Engine"
    bl_description = "Send the solver name and this parameter block to the engine module"

    def execute(self, context):
        solver = context.scene.qmyi.solver
        try:
            values = solver.as_dict()
            solver.apply_to_engine()
        except Exception as error:
            self.report({'ERROR'}, f"engine not available: {error}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"applied {solver.solver_name} and {len(values)} parameters")
        return {'FINISHED'}


class LoadSolverDefaultsOperator(bpy.types.Operator):
    bl_idname = "qmyi.solver_load_defaults"
    bl_label = "Load Defaults"
    bl_description = "Reset every parameter to the engine default"

    def execute(self, context):
        context.scene.qmyi.solver.load_defaults()
        return {'FINISHED'}


class ImportSolverParametersOperator(bpy.types.Operator):
    bl_idname = "qmyi.solver_import_json"
    bl_label = "Import Parameter File"
    bl_description = "Read a JSON object of engine parameters; unknown names become custom entries"

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        solver = context.scene.qmyi.solver
        try:
            known, custom = solver.import_file(bpy.path.abspath(self.filepath))
        except Exception as error:
            self.report({'ERROR'}, f"cannot read {self.filepath}: {error}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"imported {known} parameters, {custom} custom entries")
        return {'FINISHED'}


class AddCustomParameterOperator(bpy.types.Operator):
    bl_idname = "qmyi.solver_custom_add"
    bl_label = "Add Custom Parameter"

    def execute(self, context):
        context.scene.qmyi.solver.add_custom()
        return {'FINISHED'}


class RemoveCustomParameterOperator(bpy.types.Operator):
    bl_idname = "qmyi.solver_custom_remove"
    bl_label = "Remove Custom Parameter"

    def execute(self, context):
        if not context.scene.qmyi.solver.remove_custom():
            self.report({'WARNING'}, "no custom parameter to remove")
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (
    QY_PT_solver,
    *GROUP_PANELS,
    QY_PT_solver_custom,
    QY_PT_solver_debug,
    QY_PT_capture,
    QY_UL_custom_parameter,
    ApplySolverParametersOperator,
    LoadSolverDefaultsOperator,
    ImportSolverParametersOperator,
    AddCustomParameterOperator,
    RemoveCustomParameterOperator,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
