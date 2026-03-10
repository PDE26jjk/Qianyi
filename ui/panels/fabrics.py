import bpy
from bpy.types import Context

from ...utilities.node_tree import get_active_node_tree
from ...declarations import Panels, Operators
from . import NODE_PT_qmyi_base


class QY_PT_fabrics(NODE_PT_qmyi_base):
    bl_category = "Fabric"
    bl_label = "Fabrics"
    bl_idname = Panels.Fabrics
    # bl_options = {""}
    bl_order = 0

    def draw(self, context: Context):
        layout = self.layout
        # qmyi = context.scene.qmyi
        row = layout.row(align=False)
        project = get_active_node_tree(context)
        if project is None:
            row.label("No project editing")
            return
        # box = layout.box()
        fabric = None
        if project.active_fabric_index < len(project.fabrics):
            fabric = project.fabrics[project.active_fabric_index]
        col = row.column(align=True)
        col.template_list(QY_UL_FabricList.__name__, "Fabrics", project, "fabrics", project, "active_fabric_index",
                          rows=4)
        col = row.column(align=True)

        # col.operator(Operators.AddProject, text="", icon="ADD")
        # console_print("filter_name="+filter_name[None])
        col.operator(Operators.AddFabric, text="", icon="ADD")
        subrow = col.row(align=True)
        subrow.enabled = fabric is not None and len(project.fabrics) > 1
        subrow.operator(Operators.RemoveFabric, text="", icon="REMOVE")
        col.separator()
        subrow = col.row(align=True)
        subrow.enabled = fabric is not None and filter_name[None] == ""
        subrow.operator(Operators.ChangeFabricOrder, text="", icon="TRIA_UP").move_up = True
        subrow = col.row(align=True)
        subrow.enabled = fabric is not None and filter_name[None] == ""
        subrow.operator(Operators.ChangeFabricOrder, text="", icon="TRIA_DOWN").move_up = False


filter_name = {None: ""}


class QY_UL_FabricList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row()
        row.label(text="", icon="SCRIPT")
        row.prop(item, "name", emboss=False, text="")

    def filter_items(self, context, data, propname):
        global filter_name
        # qmyi = context.scene.qmyi
        fabrics = getattr(data, propname)
        helper_funcs = bpy.types.UI_UL_list

        flt_flags = []

        if self.filter_name:
            flt_flags = helper_funcs.filter_items_by_name(self.filter_name, self.bitflag_filter_item, fabrics, "name",
                                                          reverse=False)
        if not flt_flags:
            flt_flags = [self.bitflag_filter_item] * len(fabrics)

        filter_name[None] = self.filter_name

        return flt_flags, []


class QY_PT_fabricProperty(NODE_PT_qmyi_base):
    bl_parent_id = Panels.Fabrics
    bl_idname = Panels.FabricProperty
    bl_label = "Property"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        project = get_active_node_tree(context)
        row = layout.row(align=False)
        if project is None:
            return
        # box = layout.box()
        fabric = None
        if project.active_fabric_index < len(project.fabrics):
            fabric = project.fabrics[project.active_fabric_index]
        else:
            return

        col = row.column(align=True)

        # col.label(text=f"fabric: {fabric.name}")
        col.prop(fabric, "thickness")
        col.prop(fabric, "friction")
        col.prop(fabric, "weight")
        col.prop(fabric, "stretch")
        col.prop(fabric, "shear")
        col.prop(fabric, "bending")
