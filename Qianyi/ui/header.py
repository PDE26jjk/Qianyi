import bpy
import platform

from ..utilities.node_tree import get_active_node_tree


class SN_PT_HeaderSettings(bpy.types.Panel):
    bl_idname = "SN_PT_HeaderSettings"
    bl_label = "Settings"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "HEADER"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.sn, "insert_sockets")
        layout.prop(
            context.preferences.view,
            "show_tooltips_python",
            text="Show Python Tooltips",
        )


def header_prepend(self, context):
    if get_active_node_tree(context) is not None:
        layout = self.layout
        layout.menu("NODE_MT_custom_menu")




def header_append(self, context):
    if get_active_node_tree(context) is not None:
        layout = self.layout

        row = layout.row()
        qmyi = context.scene.qmyi


        sub_row = row.row(align=True)
        sub_row.prop_enum(qmyi, "edit_mode", 'PATTERN', text="")
        sub_row.prop_enum(qmyi, "edit_mode", 'EDGE', text="")
        sub_row.prop_enum(qmyi, "edit_mode", 'SEWING', text="")
        # col = sub_row.column(align=True)
        # col.label(text="header_append...")



# def node_info_append(self, context):
#     layout = self.layout
#     node = context.space_data.node_tree.nodes.active
#     if getattr(node, "is_sn", False):
#         layout.operator(
#             "wm.url_open", text="Node Documentation", icon="QUESTION"
#         ).url = ""
