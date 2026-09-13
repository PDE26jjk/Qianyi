from bpy.types import WorkSpaceTool

# from ...keymaps import tool_select
from ...declarations import GizmoGroups, Operators, WorkSpaceTools


class VIEW3D_T_qmyi_pick_mesh(WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = 'OBJECT'
    bl_idname = WorkSpaceTools.Select
    bl_label = ""
    bl_description = "Select Entities"
    bl_operator = Operators.Pick3D
    bl_icon = "ops.gpencil.primitive_arc"
    bl_widget = GizmoGroups.Preselection
    bl_keymap = ((
        Operators.Pick3D,
        {"type": "LEFTMOUSE", "value": "PRESS"},
        None,
    ),
    )

    @classmethod
    def draw_settings(cls, context, layout, tool):
        layout.label(text="Pick3D")
        # props = tool.operator_properties(Operators.Select)
        # layout.prop(props, "mode", text="", expand=True, icon_only=True)
