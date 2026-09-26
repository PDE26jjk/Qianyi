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


class NODE_MT_qmyi_corner(Menu):
    """The corner tools: one mode per entry, in a menu of their own.

    The editor's context menu offers this instead of a row of three buttons. A
    row of buttons is what made that menu as wide as the editor, and the three
    modes are one step away here instead of taking a line each.
    """

    bl_label = "Corner"
    bl_idname = "NODE_MT_qmyi_corner"

    def draw(self, context):
        layout = self.layout
        # Named explicitly: these ask for Blender's redo panel once they have run,
        # and only the invoke path does that. A menu's own call context is not
        # something to rely on here.
        layout.operator_context = 'INVOKE_DEFAULT'
        layout.operator(Operators.Corner2D, text="round").mode = "ROUND"
        layout.operator(Operators.Corner2D, text="chamfer").mode = "CHAMFER"
        layout.operator(Operators.Corner2D, text="hollow").mode = "CONCAVE"
