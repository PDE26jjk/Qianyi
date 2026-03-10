import bpy
from bpy.types import Context

from ...declarations import Panels, Operators
from . import NODE_PT_qmyi_base


def get_selected_graph():
    active_project_index = bpy.context.scene.qmyi.active_project_index
    if active_project_index < len(bpy.data.node_groups):
        ntree = bpy.data.node_groups[active_project_index]
        if ntree.bl_idname == Panels.QianyiNodeTree:
            return ntree
    return None


class QY_PT_qmyi_projects(NODE_PT_qmyi_base):
    bl_category = "Project"
    bl_label = "Projects"
    bl_idname = Panels.Projects
    # bl_options = {}
    bl_order = 0

    def draw(self, context: Context):
        layout = self.layout
        qmyi = context.scene.qmyi
        # box = layout.box()
        row = layout.row()

        tree = get_selected_graph()

        row = layout.row(align=False)
        col = row.column(align=True)

        col.template_list(QY_UL_ProjectList.__name__, "Projects", bpy.data, "node_groups", qmyi, "active_project_index",
                          rows=4)
        col = row.column(align=True)
        # console_print("filter_name="+filter_name[None])
        col.operator(Operators.AddProject, text="", icon="ADD")
        subrow = col.row(align=True)
        subrow.enabled = tree is not None
        subrow.operator(Operators.RemoveProject, text="", icon="REMOVE")
        col.separator()
        subrow = col.row(align=True)
        subrow.enabled = tree is not None and filter_name[None] == ""
        subrow.operator(Operators.ChangeProjectOrder, text="", icon="TRIA_UP").move_up = True
        subrow = col.row(align=True)
        subrow.enabled = tree is not None and filter_name[None] == ""
        subrow.operator(Operators.ChangeProjectOrder, text="", icon="TRIA_DOWN").move_up = False


filter_name = {None:""}


class QY_UL_ProjectList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row()
        row.label(text="", icon="SCRIPT")
        row.prop(item, "name", emboss=False, text="")

    def filter_items(self, context, data, propname):
        global filter_name
        # qmyi = context.scene.qmyi
        node_trees = getattr(data, propname)
        helper_funcs = bpy.types.UI_UL_list

        _sort = [(idx, frame)
                 for idx, frame in enumerate(bpy.data.node_groups)]
        flt_neworder = helper_funcs.sort_items_helper(
            _sort, lambda e: getattr(e[1], "index", 0), False)
        flt_flags = helper_funcs.filter_items_by_name(
            Panels.QianyiNodeTree, self.bitflag_filter_item, node_trees, "bl_idname", reverse=False)

        if self.filter_name:
            for i in range(len(node_trees)):
                if not self.filter_name.lower() in node_trees[i].name.lower():
                    flt_flags[i] = 0

        filter_name[None] = self.filter_name
        return flt_flags, flt_neworder
