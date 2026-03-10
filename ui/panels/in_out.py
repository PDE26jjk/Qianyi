from bpy.types import Context

from ... import declarations
from . import NODE_PT_qmyi_base


class NODE_PT_qmyi_in_out(NODE_PT_qmyi_base):
    bl_category = "Project"
    bl_label = "in_out"
    bl_idname = declarations.Panels.InOut
    bl_order = 1

    # bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        # box = layout.box()
        row = layout.row()
        props = row.operator(
            declarations.Operators.Import,
            text="Import")
