from bpy.types import Panel

from ...utilities.node_tree import get_active_node_tree


class NODE_PT_qmyi_base(Panel):
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"

    @classmethod
    def poll(cls, context):
        return get_active_node_tree(context) is not None
