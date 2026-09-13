from bpy.types import Menu

from ..declarations import Operators

# TODO 完善各种右键菜单、快捷键等
class NODE_MT_CustomMenu(Menu):
    """自定义节点工具菜单"""
    bl_label = "自定义工具"
    bl_idname = "NODE_MT_custom_menu"

    def draw(self, context):
        layout = self.layout

        # 添加菜单项
        layout.operator(Operators.ConvertCurve, icon='PLUGIN')

        # 添加分隔线
        layout.separator()
        #
        # # 添加更多工具
        # layout.operator("node.select_all", text="全选节点").action = 'SELECT'
        # layout.operator("node.select_all", text="取消全选").action = 'DESELECT'