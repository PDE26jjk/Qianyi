from bpy.types import Context

from ... import declarations
from . import NODE_PT_qmyi_base


class QY_PT_qmyi_entities(NODE_PT_qmyi_base):
    bl_category = "Pattern"
    bl_label = "Entities"
    bl_idname = declarations.Panels.Entities
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        # box = layout.box()
        row = layout.row()
        props = row.operator(
            declarations.Operators.GenerateAllMesh,
            text="GenerateAllMesh",
            # emboss=False,
            # icon=("RADIOBUT_ON" if e.selected else "RADIOBUT_OFF"),
        )
