from bpy.types import Panel

from ...utilities.node_tree import get_active_node_tree


class VIEW_3D_PT_qmyi_base(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    @classmethod
    def poll(cls, context):
        # return get_active_node_tree(context) is not None
        return True
